import os
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from fetch_common import fetch_or_cache
from fetch_currents import (
    Chunk,
    griddap_url,
    history_start,
    is_netcdf,
    month_chunks,
    offline_chunks,
    parse_last_time,
    record_completeness,
    reusable,
)
from oceanclean_common.regions import HISTORY_BOX, Box, to_lon360

NC = b"CDF\x01" + b"\x00" * 16


def test_to_lon360_keeps_the_box_contiguous_across_the_dateline() -> None:
    assert to_lon360(-180.0) == 180.0
    assert to_lon360(-130.0) == 230.0
    assert to_lon360(10.0) == 10.0


def test_griddap_url_selects_u_and_v_over_the_box_in_0_360() -> None:
    url = griddap_url(date(2026, 8, 1), date(2026, 8, 31), HISTORY_BOX)
    sel = "%5B(2026-08-01):(2026-08-31)%5D%5B(20.0):(45.0)%5D%5B(180.0):(230.0)%5D"
    assert url == (f"https://upwell.pfeg.noaa.gov/erddap/griddap/scud_pac.nc?u{sel},v{sel}")


def test_parse_last_time_reads_erddap_json_table() -> None:
    doc = {"table": {"columnNames": ["time"], "rows": [["2026-09-18T00:00:00Z"]]}}
    assert parse_last_time(doc) == date(2026, 9, 18)


def test_history_starts_on_the_first_of_the_month_n_months_back() -> None:
    assert history_start(date(2026, 9, 18), 24) == date(2024, 9, 1)
    assert history_start(date(2026, 1, 31), 1) == date(2025, 12, 1)


def test_month_chunks_are_calendar_months_clipped_to_the_range() -> None:
    chunks = month_chunks(date(2026, 7, 1), date(2026, 9, 18))
    assert [(c.start, c.end) for c in chunks] == [
        (date(2026, 7, 1), date(2026, 7, 31)),
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 18)),
    ]
    assert [c.name for c in chunks] == ["2026-07", "2026-08", "2026-09"]
    # Only the month holding the dataset's last day can still change.
    assert [c.closed for c in chunks] == [True, True, False]


def test_month_chunks_across_a_year_boundary() -> None:
    names = [c.name for c in month_chunks(date(2025, 11, 1), date(2026, 2, 3))]
    assert names == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_offline_chunks_are_the_newest_cached_months(tmp_path: Path) -> None:
    for name in ["2026-06", "2026-07", "2026-08", "2026-09"]:
        (tmp_path / f"scud_pac_{name}.nc").write_bytes(NC)
    (tmp_path / "scud_pac_2026-09.nc.part").write_bytes(b"half")
    assert [c.name for c in offline_chunks(tmp_path, 3)] == ["2026-07", "2026-08", "2026-09"]


def test_offline_chunks_without_cache_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        offline_chunks(tmp_path, 3)


def test_is_netcdf_accepts_classic_and_hdf5_rejects_html() -> None:
    assert is_netcdf(NC)
    assert is_netcdf(b"\x89HDF\r\n\x1a\n" + b"\x00" * 8)
    assert not is_netcdf(b"<html>Error</html>")


def test_fetch_or_cache_writes_cache_on_success(tmp_path: Path) -> None:
    cache = tmp_path / "sub" / "x.nc"
    got = fetch_or_cache(lambda: NC, cache)
    assert (got.data, got.source) == (NC, "api")
    assert cache.read_bytes() == NC


def test_fetch_or_cache_falls_back_to_cache_with_its_fetch_time(tmp_path: Path) -> None:
    cache = tmp_path / "x.nc"
    cache.write_bytes(NC)
    then = datetime(2026, 10, 1, tzinfo=timezone.utc)
    os.utime(cache, (then.timestamp(), then.timestamp()))

    def down() -> bytes:
        raise httpx.ConnectError("network off")

    got = fetch_or_cache(down, cache)
    assert (got.data, got.source, got.fetched_at) == (NC, "cache", then)


def test_fetch_or_cache_without_cache_reraises(tmp_path: Path) -> None:
    def down() -> bytes:
        raise httpx.ConnectError("network off")

    with pytest.raises(httpx.ConnectError):
        fetch_or_cache(down, tmp_path / "missing.nc")


def test_box_contains_is_inclusive() -> None:
    box = Box(30, 40, -150, -135)
    assert box.contains(30, -150) and box.contains(40, -135)
    assert not box.contains(29.9, -140)


def test_chunk_cache_name() -> None:
    c = Chunk(start=date(2026, 8, 1), end=date(2026, 8, 31), closed=True)
    assert c.filename == "scud_pac_2026-08.nc"


AUG = Chunk(start=date(2026, 8, 1), end=date(2026, 8, 31), closed=True)
SEP_OPEN = Chunk(start=date(2026, 9, 1), end=date(2026, 9, 18), closed=False)


def test_only_complete_closed_months_are_reused_from_cache(tmp_path: Path) -> None:
    assert not reusable(AUG, tmp_path)  # not cached yet
    (tmp_path / AUG.filename).write_bytes(NC)
    assert reusable(AUG, tmp_path)
    (tmp_path / SEP_OPEN.filename).write_bytes(NC)
    assert not reusable(SEP_OPEN, tmp_path)  # the open month always re-fetches


def test_a_month_cached_while_open_is_refetched_after_it_closes(tmp_path: Path) -> None:
    (tmp_path / SEP_OPEN.filename).write_bytes(NC)
    record_completeness(SEP_OPEN, tmp_path)
    sep_closed = Chunk(start=date(2026, 9, 1), end=date(2026, 9, 30), closed=True)
    assert not reusable(sep_closed, tmp_path)  # cached file stops at 09-18
    record_completeness(sep_closed, tmp_path)  # after a successful full-month fetch
    assert reusable(sep_closed, tmp_path)
    assert [c.name for c in offline_chunks(tmp_path, 3)] == ["2026-09"]
