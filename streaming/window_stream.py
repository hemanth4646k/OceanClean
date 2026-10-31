"""Speed layer, third query: 5-minute event-time windows -> energy, fuel-burn anomaly, alerts (M5).

This is the only watermarked query (ADR-0005). It reads Kafka on its own from the latest offsets:
older events from before a sim reset would push the watermark past the new run. A late row
(an offline-buffer flush older than the watermark) misses its window; that is acceptable here,
because the lake and live state get every row from the telemetry query.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import psycopg
from anomaly import WindowAgg
from energy import COLLECT_KN
from geo import KN_TO_MS
from oceanclean_common.settings import to_utc
from pyspark.sql import DataFrame, Row
from pyspark.sql import functions as F
from stream_store import store_windows

log = logging.getLogger("window_stream")

WINDOW = "5 minutes"
WATERMARK = "10 minutes"  # sim time; at SIM_RATE=3600 that is 1/6 real second
WINDOW_COLUMNS = (
    "vessel_id",
    "window_end",
    "last_ts",
    "n",
    "fuel_l",
    "battery_pct",
    "hold_fill_pct",
    "sum_v3",
    "n_collect",
)


def window_aggregates(df: DataFrame) -> DataFrame:
    """Per vessel and tumbling window: state at the last tick plus the power model's sums."""
    last = F.col("event_ts")
    return (
        df.groupBy("vessel_id", F.window("event_ts", WINDOW))
        .agg(
            F.max("event_ts").alias("last_ts"),
            F.count(F.lit(1)).cast("int").alias("n"),
            F.max_by("fuel_l", last).alias("fuel_l"),
            F.max_by("battery_pct", last).alias("battery_pct"),
            F.max_by("hold_fill_pct", last).alias("hold_fill_pct"),
            F.sum(F.pow(F.col("speed_kn") * KN_TO_MS, 3)).alias("sum_v3"),
            F.sum((F.col("speed_kn") == COLLECT_KN).cast("int")).alias("n_collect"),
        )
        .select("vessel_id", F.col("window.end").alias("window_end"), *WINDOW_COLUMNS[2:])
    )


def windowed(parsed: DataFrame) -> DataFrame:
    """The streaming chain: watermark, dedup on (vessel_id, seq) within it, then the windows."""
    return window_aggregates(
        parsed.withWatermark("event_ts", WATERMARK).dropDuplicatesWithinWatermark(
            ["vessel_id", "seq"]
        )
    )


def to_window_agg(r: Row | dict[str, object]) -> WindowAgg:
    d = r.asDict() if isinstance(r, Row) else r
    return WindowAgg(
        **{**d, "window_end": to_utc(d["window_end"]), "last_ts": to_utc(d["last_ts"])}
    )


def make_window_writer(dsn: str, tick_s: float) -> Callable[[DataFrame, int], None]:
    def write_batch(batch: DataFrame, batch_id: int) -> None:
        windows = [to_window_agg(r) for r in batch.collect()]
        if not windows:
            return
        with psycopg.connect(dsn) as conn:
            n_alerts = store_windows(conn, windows, tick_s)
        log.info("window batch %d: %d window(s), %d alert(s)", batch_id, len(windows), n_alerts)

    return write_batch
