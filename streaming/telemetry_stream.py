"""Speed layer: Kafka telemetry -> parse -> per-batch dedup -> PostGIS live state UPSERT.

No watermark here (ADR-0005): offline flushes, the backfill and replays are late by design and
must reach every sink. Late rows are harmless because the UPSERT only applies newer events.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone

import psycopg
from oceanclean_common.settings import pg_dsn
from oceanclean_common.telemetry import SPARK_COLUMNS, SPARK_DDL, TELEMETRY_TOPIC
from pyspark.sql import DataFrame, Row, SparkSession, Window
from pyspark.sql import functions as F

log = logging.getLogger("telemetry_stream")

STORED_DDL = "vessel_id STRING, stored_ts TIMESTAMP"

UPSERT_SQL = f"""
INSERT INTO vessel_state ({", ".join(SPARK_COLUMNS)}, geom, updated_at)
VALUES ({", ".join(["%s"] * len(SPARK_COLUMNS))}, ST_SetSRID(ST_MakePoint(%s, %s), 4326), now())
ON CONFLICT (vessel_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in SPARK_COLUMNS if c != "vessel_id")},
  geom = EXCLUDED.geom, updated_at = now()
WHERE vessel_state.event_ts < EXCLUDED.event_ts
"""


def to_utc(ts: datetime) -> datetime:
    """Spark collect() returns naive datetimes in the Python process's local zone; make it UTC."""
    return ts.astimezone(timezone.utc)


def parse_telemetry(raw: DataFrame) -> DataFrame:
    """Kafka `value` (producer JSON) -> contract columns; rows that don't parse are dropped."""
    return (
        raw.select(F.from_json(F.col("value").cast("string"), SPARK_DDL).alias("t"))
        .select("t.*")
        .where(F.col("vessel_id").isNotNull() & F.col("event_ts").isNotNull())
    )


def dedup_batch(batch: DataFrame) -> DataFrame:
    """Stateless in-batch dedup on (vessel_id, seq); history dedup is the silver job's."""
    return batch.dropDuplicates(["vessel_id", "seq"])


def latest_per_vessel(batch: DataFrame) -> DataFrame:
    """Newest row per vessel by event time (seq breaks ties); only it can move live state."""
    w = Window.partitionBy("vessel_id").orderBy(F.col("event_ts").desc(), F.col("seq").desc())
    return batch.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def stale_rows(batch: DataFrame, stored: DataFrame) -> DataFrame:
    """Rows not newer than the stored live state (STORED_DDL), i.e. ones the UPSERT ignores."""
    return batch.join(F.broadcast(stored), "vessel_id").where(
        F.col("event_ts") <= F.col("stored_ts")
    )


def _upsert_params(r: Row) -> tuple[object, ...]:
    values = (to_utc(r[c]) if c == "event_ts" else r[c] for c in SPARK_COLUMNS)
    return (*values, r["lon"], r["lat"])


def make_writer(dsn: str) -> Callable[[DataFrame, int], None]:
    def write_batch(batch: DataFrame, batch_id: int) -> None:
        batch.persist()
        try:
            total = batch.count()
            if total == 0:
                return
            unique = dedup_batch(batch)
            n_unique = unique.count()
            latest = latest_per_vessel(unique).select(*SPARK_COLUMNS).collect()
            with psycopg.connect(dsn) as conn:
                stored = conn.execute(
                    "SELECT vessel_id, event_ts FROM vessel_state WHERE vessel_id = ANY(%s)",
                    [[r["vessel_id"] for r in latest]],
                ).fetchall()
                stored_df = batch.sparkSession.createDataFrame(stored, STORED_DDL)
                n_stale = stale_rows(unique, stored_df).count() if stored else 0
                conn.cursor().executemany(UPSERT_SQL, [_upsert_params(r) for r in latest])
            log.info(
                "batch %d: %d rows, %d duplicate (vessel_id, seq) dropped, "
                "%d not newer than live state (late/replayed), %d vessel(s) offered to UPSERT",
                batch_id,
                total,
                total - n_unique,
                n_stale,
                len(latest),
            )
        finally:
            batch.unpersist()

    return write_batch


def read_kafka(spark: SparkSession, bootstrap: str) -> DataFrame:
    # failOnDataLoss stays at its default (true): lost offsets must fail the query loudly.
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", TELEMETRY_TOPIC)
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", 200_000)
        .load()
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    spark = (
        SparkSession.builder.appName("oceanclean-telemetry-stream")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", os.environ["TELEMETRY_PARTITIONS"])
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    (
        parse_telemetry(read_kafka(spark, os.environ["KAFKA_BOOTSTRAP"]))
        .writeStream.foreachBatch(make_writer(pg_dsn(os.environ)))
        .option("checkpointLocation", os.environ["CHECKPOINT_DIR"])
        .trigger(processingTime=os.environ["STREAM_TRIGGER"])
        .start()
        .awaitTermination()
    )


if __name__ == "__main__":
    main()
