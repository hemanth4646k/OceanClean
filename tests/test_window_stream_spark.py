"""Spark fixture tests for the watermarked 5-minute window query (M5, ADR-0005)."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

import window_stream as ws  # noqa: E402
from energy import COLLECT_KN, CRUISE_KN  # noqa: E402
from geo import KN_TO_MS  # noqa: E402
from oceanclean_common.settings import to_utc  # noqa: E402
from oceanclean_common.telemetry import Telemetry  # noqa: E402
from pyspark.sql import DataFrame, SparkSession  # noqa: E402
from telemetry_stream import parse_telemetry  # noqa: E402

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    s = (
        SparkSession.builder.master("local[1]")
        .appName("oceanclean-window-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.ivy", "/tmp/.ivy2")
        .getOrCreate()
    )
    yield s
    s.stop()


def tel(seq: int, minutes: int, speed_kn: float = CRUISE_KN, vessel_id: str = "OC-01") -> Telemetry:
    """One tick; fuel, battery and hold change with seq so the window's last tick is visible."""
    return Telemetry(
        vessel_id=vessel_id,
        event_ts=T0 + timedelta(minutes=minutes),
        seq=seq,
        lat=35.0,
        lon=-142.0,
        heading_deg=90.0,
        speed_kn=speed_kn,
        battery_pct=100.0 - seq,
        fuel_l=1000.0 - 2 * seq,
        debris_density=0.1,
        hold_fill_pct=float(seq),
        buffered=False,
    )


def as_df(spark: SparkSession, events: list[Telemetry]) -> DataFrame:
    raw = spark.createDataFrame(
        [(bytearray(e.to_json(), "utf-8"),) for e in events], "value BINARY"
    )
    return parse_telemetry(raw)


def rows(df: DataFrame) -> list[dict[str, object]]:
    out = []
    for r in df.orderBy("vessel_id", "window_end").collect():
        d = r.asDict()
        d["window_end"], d["last_ts"] = to_utc(d["window_end"]), to_utc(d["last_ts"])
        out.append(d)
    return out


def test_window_aggregates_give_last_tick_state_and_power_model_sums(spark: SparkSession) -> None:
    # OC-01: ticks at minutes 1..6 (the last one opens the second window), out of arrival order.
    # Minutes 3 and 4 are at collection speed. OC-02 has one tick in the first window.
    events = [tel(4, 4, COLLECT_KN), tel(1, 1), tel(3, 3, COLLECT_KN), tel(2, 2), tel(5, 6)]
    events.append(tel(9, 2, vessel_id="OC-02"))
    got = rows(ws.window_aggregates(as_df(spark, events)))
    v3 = (CRUISE_KN * KN_TO_MS) ** 3
    c3 = (COLLECT_KN * KN_TO_MS) ** 3
    assert [(r["vessel_id"], r["window_end"]) for r in got] == [
        ("OC-01", T0 + timedelta(minutes=5)),
        ("OC-01", T0 + timedelta(minutes=10)),
        ("OC-02", T0 + timedelta(minutes=5)),
    ]
    first = got[0]
    assert set(first) == set(ws.WINDOW_COLUMNS)
    assert first["last_ts"] == T0 + timedelta(minutes=4)
    assert first["n"] == 4
    # State at the window's last tick by event time (seq 4), not the last row to arrive.
    assert (first["fuel_l"], first["battery_pct"], first["hold_fill_pct"]) == (992.0, 96.0, 4.0)
    assert first["sum_v3"] == pytest.approx(2 * v3 + 2 * c3)
    assert first["n_collect"] == 2
    assert (got[1]["n"], got[1]["last_ts"]) == (1, T0 + timedelta(minutes=6))


def test_window_rows_build_the_pure_scorer_input(spark: SparkSession) -> None:
    [r] = rows(ws.window_aggregates(as_df(spark, [tel(1, 1), tel(2, 2)])))
    w = ws.to_window_agg(r)
    assert (w.vessel_id, w.n, w.fuel_l, w.window_end) == ("OC-01", 2, 996.0, r["window_end"])


def test_stream_dedups_within_the_watermark_and_appends_only_closed_windows(
    spark: SparkSession, tmp_path: Path
) -> None:
    """dedup -> window aggregation chains in append mode (Spark 3.5); a window is emitted once
    the watermark (max event time - WATERMARK) passes its end."""
    src = tmp_path / "in"
    src.mkdir()

    def drop(name: str, events: list[Telemetry]) -> None:
        (src / name).write_text("\n".join(e.to_json() for e in events) + "\n")

    stream = parse_telemetry(spark.readStream.format("text").load(str(src)))
    q = (
        ws.windowed(stream)
        .writeStream.format("memory")
        .queryName("windows_test")
        .outputMode("append")
        .option("checkpointLocation", str(tmp_path / "ckpt"))
        .start()
    )
    try:
        drop("a.json", [tel(1, 1), tel(2, 2), tel(2, 2)])  # seq 2 duplicated in one file
        q.processAllAvailable()
        assert spark.table("windows_test").count() == 0  # 12:00-12:05 is still open
        drop("b.json", [tel(2, 2), tel(3, 7)])  # seq 2 again, in a later batch
        q.processAllAvailable()
        assert spark.table("windows_test").count() == 0  # watermark 11:57 < 12:05
        drop("c.json", [tel(4, 16)])  # watermark 12:06 closes the first window only
        q.processAllAvailable()
        q.processAllAvailable()  # a no-data batch emits windows the new watermark closed
        got = rows(spark.table("windows_test"))
    finally:
        q.stop()
    assert [(r["window_end"], r["n"]) for r in got] == [(T0 + timedelta(minutes=5), 2)]
