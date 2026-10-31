"""Fetch NOAA SCUD daily surface currents (ERDDAP griddap) into bronze + local cache (ADR-0002).

History: HISTORY_BOX from the first of the month HISTORY_MONTHS before the dataset's last day,
one NetCDF per calendar month. Closed months never change, so a cached one is reused; the open
month is re-fetched every run. With ERDDAP down, the newest cached months are used (source=cache).
The mission window is a slice of this history, cut by the ETL.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fetch_common import (
    FETCH_ERRORS,
    Fetched,
    cached,
    fetch_or_cache,
    http_get,
    put_object,
    record_source,
    write_atomic,
)
from oceanclean_common.lake import minio_client
from oceanclean_common.regions import (
    BRONZE_CURRENTS,
    CURRENTS_MANIFEST,
    HISTORY_BOX,
    Box,
    to_lon360,
)
from oceanclean_common.settings import pg_dsn

log = logging.getLogger("fetch_currents")

ERDDAP = "https://upwell.pfeg.noaa.gov/erddap/griddap"
DATASET = "scud_pac"
HISTORY_MONTHS = 24
LAST_DAY_FILE = "last_day.txt"
OPEN_MARKER = ".open"  # next to a month file cached before the month was complete
NETCDF_MAGIC = (b"CDF\x01", b"CDF\x02", b"CDF\x05", b"\x89HDF\r\n\x1a\n")


@dataclass(frozen=True)
class Chunk:
    start: date
    end: date
    closed: bool  # False for the month holding the dataset's last day: it still grows

    @property
    def name(self) -> str:
        return self.start.strftime("%Y-%m")

    @property
    def filename(self) -> str:
        return f"{DATASET}_{self.name}.nc"


def griddap_url(start: date, end: date, box: Box) -> str:
    """ERDDAP .nc subset of u and v over [start, end] and the box (SCUD longitudes are 0..360)."""
    sel = (
        f"[({start.isoformat()}):({end.isoformat()})]"
        f"[({box.lat_min}):({box.lat_max})]"
        f"[({to_lon360(box.lon_min)}):({to_lon360(box.lon_max)})]"
    )
    query = ",".join(f"{var}{sel}" for var in ("u", "v"))
    return f"{ERDDAP}/{DATASET}.nc?{quote(query, safe='(),:')}"


def parse_last_time(doc: dict) -> date:
    """Date of the newest time step from ERDDAP's `time[(last)]` .json answer."""
    return datetime.fromisoformat(doc["table"]["rows"][0][0].replace("Z", "+00:00")).date()


def first_of_month(d: date, months_back: int = 0) -> date:
    index = d.year * 12 + d.month - 1 - months_back
    return date(index // 12, index % 12 + 1, 1)


def history_start(last: date, months: int) -> date:
    return first_of_month(last, months)


def month_chunks(start: date, last: date) -> list[Chunk]:
    chunks = []
    month = first_of_month(start)
    while month <= last:
        next_month = first_of_month(month + timedelta(days=31))
        end = min(next_month - timedelta(days=1), last)
        chunks.append(Chunk(max(month, start), end, closed=end < last))
        month = next_month
    return chunks


def offline_chunks(cache_dir: Path, n: int) -> list[Chunk]:
    """The newest n cached months, for when ERDDAP can't be reached."""
    files = sorted(cache_dir.glob(f"{DATASET}_????-??.nc"))[-n:]
    if not files:
        raise SystemExit(f"ERDDAP unreachable and no cached currents in {cache_dir}")
    starts = [date.fromisoformat(p.stem.removeprefix(f"{DATASET}_") + "-01") for p in files]
    return [Chunk(s, first_of_month(s + timedelta(days=31)) - timedelta(1), True) for s in starts]


def reusable(chunk: Chunk, cache_dir: Path) -> bool:
    """A cached month can stand in for the API only if it was complete when cached."""
    path = cache_dir / chunk.filename
    return (
        chunk.closed and path.exists() and not (cache_dir / (chunk.filename + OPEN_MARKER)).exists()
    )


def record_completeness(chunk: Chunk, cache_dir: Path) -> None:
    """After a fetch: mark an open month's file as partial, or clear the mark once complete."""
    marker = cache_dir / (chunk.filename + OPEN_MARKER)
    if chunk.closed:
        marker.unlink(missing_ok=True)
    else:
        marker.touch()


def is_netcdf(data: bytes) -> bool:
    return data.startswith(NETCDF_MAGIC)


def download(url: str) -> bytes:
    data = http_get(url)
    if not is_netcdf(data):
        raise ValueError(f"not a NetCDF file ({len(data)} bytes): {data[:80]!r}")
    return data


def latest_date() -> date:
    return parse_last_time(json.loads(http_get(f"{ERDDAP}/{DATASET}.json?time%5B(last)%5D")))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cache_dir = Path(os.environ["CACHE_DIR"]) / "currents"
    bucket = os.environ["LAKE_BUCKET"]

    try:
        last = latest_date()
        chunks = month_chunks(history_start(last, HISTORY_MONTHS), last)
        log.info("ERDDAP %s ends %s; %d monthly chunks", DATASET, last, len(chunks))
    except FETCH_ERRORS as e:
        last = None
        chunks = offline_chunks(cache_dir, HISTORY_MONTHS + 1)
        log.warning("ERDDAP unreachable (%s); source=cache, %d cached months", e, len(chunks))
    online = last is not None
    # Month files can't say where the data ends offline; the last online run records it here.
    last_day_file = cache_dir / LAST_DAY_FILE
    if online:
        write_atomic(last_day_file, last.isoformat().encode())
    elif last_day_file.exists():
        last = date.fromisoformat(last_day_file.read_text())
    end = last or chunks[-1].end

    got: list[Fetched] = []
    fell_back = False  # an attempted download failed and the cache stood in
    for c in chunks:
        path = cache_dir / c.filename
        if not online or reusable(c, cache_dir):
            got.append(cached(path))
        else:
            got.append(
                fetch_or_cache(lambda c=c: download(griddap_url(c.start, c.end, HISTORY_BOX)), path)
            )
            if got[-1].source == "api":
                record_completeness(c, cache_dir)
            else:
                fell_back = True
        log.info("%s %s %.1f MB", c.name, got[-1].source, len(got[-1].data) / 1e6)

    source = "api" if online and not fell_back else "cache"
    client = minio_client(os.environ)
    keys = []
    for c, f in zip(chunks, got, strict=True):
        keys.append(f"{BRONZE_CURRENTS}/{c.filename}")
        put_object(client, bucket, keys[-1], f.data, "application/x-netcdf")
    fetched_at = got[-1].fetched_at  # the newest month decides how fresh the data is
    manifest = {
        "dataset": DATASET,
        "start": chunks[0].start.isoformat(),
        "end": end.isoformat(),
        "files": keys,
        "source": source,
        "fetched_at": fetched_at.isoformat(),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    put_object(client, bucket, CURRENTS_MANIFEST, json.dumps(manifest).encode(), "application/json")
    detail = {k: manifest[k] for k in ("dataset", "start", "end")}
    detail |= {
        "chunks": len(keys),
        "bytes": sum(len(f.data) for f in got),
        "box": HISTORY_BOX.__dict__,
    }
    record_source(pg_dsn(os.environ), "currents", source, fetched_at, detail)
    log.info(
        "bronze: %d files, %.1f MB, %s..%s",
        len(keys),
        detail["bytes"] / 1e6,
        manifest["start"],
        manifest["end"],
    )


if __name__ == "__main__":
    main()
