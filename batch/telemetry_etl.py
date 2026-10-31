"""Batch layer, telemetry: bronze ticks -> silver (dedup, per-tick energy and debris) -> gold (M5).

Bronze holds every tick the stream received, duplicates and late rows included (ADR-0005). Silver
keeps one row per (vessel_id, seq) and measures each tick from the one before it: energy
is fuel burned (as brake energy) plus battery drawn, debris is the hold's growth. Refuels and
offloads are state resets, not consumption, so their jumps count as zero. Gold sums them per day
and per day and 5-degree zone; a small JSON export feeds the API's Analytics tab.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone

import psycopg
from currents_etl import write_bytes
from energy import BATTERY_KWH, HOLD_CAPACITY_KG, KWH_PER_L
from oceanclean_common.regions import (
    BRONZE_TELEMETRY,
    EXPORT_ANALYTICS,
    GOLD_TELEMETRY_DAILY,
    GOLD_TELEMETRY_DAILY_ZONE,
    SILVER_TELEMETRY,
)
from oceanclean_common.settings import lake_url, pg_dsn, s3a_conf
from oceanclean_common.telemetry import SPARK_COLUMNS, ZONE_DEG
from pyspark.errors import AnalysisException
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

log = logging.getLogger("telemetry_etl")

SET_LAKE_ROWS_SQL = """
INSERT INTO lake_counts (dataset, rows, updated_at) VALUES (%s, %s, now())
ON CONFLICT (dataset) DO UPDATE SET rows = EXCLUDED.rows, updated_at = now()
"""


def zone_col(lat: str, lon: str) -> Column:
    """Spark twin of `oceanclean_common.telemetry.zone_of`, e.g. (35.1, -142.4) -> 'N35W145'."""
    la = F.floor(F.col(lat) / ZONE_DEG) * ZONE_DEG
    lo = F.floor(F.col(lon) / ZONE_DEG) * ZONE_DEG
    return F.format_string(
        "%s%02d%s%03d",
        F.when(la >= 0, "N").otherwise("S"),
        F.abs(la),
        F.when(lo >= 0, "E").otherwise("W"),
        F.abs(lo),
    )


def silver_telemetry(bronze: DataFrame) -> DataFrame:
    """One row per (vessel_id, seq), with the energy and debris of the tick that ended at it."""
    ticks = bronze.select(*SPARK_COLUMNS).dropDuplicates(["vessel_id", "seq"])
    w = Window.partitionBy("vessel_id").orderBy("seq")

    # Only a tick's direct predecessor measures it. A seq gap starts a new segment: the backfill's
    # last tick and a live run's first (LIVE_SEQ_START + 1) are different missions.
    follows = F.col("seq") - F.lag("seq").over(w) == 1

    def drop(c: str) -> Column:
        return F.when(follows, F.lag(c).over(w) - F.col(c)).otherwise(F.lit(0.0))

    burned = F.greatest(drop("fuel_l"), F.lit(0.0))  # negative = refuelled
    return ticks.select(
        "*",
        (burned * KWH_PER_L + drop("battery_pct") / 100 * BATTERY_KWH).alias("energy_kwh"),
        (F.greatest(-drop("hold_fill_pct"), F.lit(0.0)) / 100 * HOLD_CAPACITY_KG).alias(
            "collected_kg"
        ),
        zone_col("lat", "lon").alias("zone"),
        F.to_date("event_ts").alias("date"),
    )


def _sums(df: DataFrame, rows: Column, *by: str) -> DataFrame:
    energy, collected = F.sum("energy_kwh"), F.sum("collected_kg")
    return df.groupBy(*by).agg(
        rows.alias("rows"),
        energy.alias("energy_kwh"),
        collected.alias("collected_kg"),
        F.when(energy > 0, collected / energy).alias("kg_per_kwh"),
    )


def daily(silver: DataFrame) -> DataFrame:
    return _sums(silver, F.count(F.lit(1)), "date")


def daily_zone(silver: DataFrame) -> DataFrame:
    return _sums(silver, F.count(F.lit(1)), "date", "zone")


def zone_totals(gold_zone: DataFrame) -> DataFrame:
    """Whole-mission yield per zone, rolled up from the gold day-zone view."""
    return _sums(gold_zone, F.sum("rows"), "zone")


def _json_rows(df: DataFrame) -> list[dict[str, object]]:
    out = []
    for r in df.collect():
        d = r.asDict()
        out.append({k: v.isoformat() if isinstance(v, date) else v for k, v in d.items()})
    return out


def main() -> None:
    # Root at WARNING: py4j logs every gateway call at INFO.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    log.setLevel(logging.INFO)
    env = os.environ
    builder = (
        SparkSession.builder.appName("oceanclean-telemetry-etl")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
    )
    for k, v in s3a_conf(env).items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    def url(key: str) -> str:
        return lake_url(env, key)

    try:
        bronze = spark.read.parquet(url(BRONZE_TELEMETRY))
    except AnalysisException:  # a fresh volume or just after a sim reset: nothing to do yet
        log.info("no bronze telemetry yet; nothing to aggregate")
        spark.stop()
        return
    # Silver is rebuilt from all of bronze: dedup and deltas need each vessel's whole history.
    silver_telemetry(bronze).write.mode("overwrite").partitionBy("date").parquet(
        url(SILVER_TELEMETRY)
    )
    silver = spark.read.parquet(url(SILVER_TELEMETRY)).cache()
    gold_daily = daily(silver).orderBy("date").cache()
    gold_zone = daily_zone(silver).orderBy("date", "zone").cache()
    gold_daily.coalesce(1).write.mode("overwrite").parquet(url(GOLD_TELEMETRY_DAILY))
    gold_zone.coalesce(1).write.mode("overwrite").parquet(url(GOLD_TELEMETRY_DAILY_ZONE))

    zones = zone_totals(gold_zone).orderBy("zone")
    doc = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "daily": _json_rows(gold_daily),
        "zones": _json_rows(zones),
    }
    write_bytes(spark, url(EXPORT_ANALYTICS), json.dumps(doc).encode())

    counts = {
        SILVER_TELEMETRY: silver.count(),
        GOLD_TELEMETRY_DAILY: gold_daily.count(),
        GOLD_TELEMETRY_DAILY_ZONE: gold_zone.count(),
    }
    with psycopg.connect(pg_dsn(env)) as conn:
        conn.cursor().executemany(SET_LAKE_ROWS_SQL, list(counts.items()))
    log.info(
        "silver/telemetry %d rows; gold %d days, %d day-zones; %d zones in the export",
        counts[SILVER_TELEMETRY],
        counts[GOLD_TELEMETRY_DAILY],
        counts[GOLD_TELEMETRY_DAILY_ZONE],
        len(doc["zones"]),
    )
    spark.stop()


if __name__ == "__main__":
    main()
