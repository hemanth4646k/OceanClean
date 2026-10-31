"""Speed layer: Kafka telemetry -> event-time watermark + dedup -> PostGIS live state UPSERT."""

from __future__ import annotations

import os

import psycopg
from oceanclean_common.telemetry import SPARK_DDL, TELEMETRY_TOPIC
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

KAFKA = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
PG_DSN = os.environ["PG_DSN"]
CHECKPOINT = os.environ.get("CHECKPOINT_DIR", "/checkpoints/telemetry")
WATERMARK = os.environ.get("WATERMARK", "10 minutes")
TRIGGER = os.environ.get("TRIGGER", "2 seconds")

COLS = [c.strip().split()[0] for c in SPARK_DDL.split(",")]

UPSERT_SQL = f"""
INSERT INTO vessel_state ({", ".join(COLS)}, geom, updated_at)
VALUES ({", ".join(["%s"] * len(COLS))}, ST_SetSRID(ST_MakePoint(%s, %s), 4326), now())
ON CONFLICT (vessel_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c != "vessel_id")},
  geom = EXCLUDED.geom, updated_at = now()
WHERE vessel_state.event_ts < EXCLUDED.event_ts
"""


def upsert_live_state(batch: DataFrame, batch_id: int) -> None:
    # Only the newest event per vessel matters for live state; late events lose the WHERE.
    w = Window.partitionBy("vessel_id").orderBy(F.col("event_ts").desc(), F.col("seq").desc())
    latest = batch.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")
    rows = latest.select(*COLS).collect()
    if not rows:
        return
    with psycopg.connect(PG_DSN) as conn:
        conn.cursor().executemany(
            UPSERT_SQL, [(*(r[c] for c in COLS), r["lon"], r["lat"]) for r in rows]
        )


def build(spark: SparkSession) -> DataFrame:
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA)
        .option("subscribe", TELEMETRY_TOPIC)
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", 200_000)
        .option("failOnDataLoss", "false")
        .load()
    )
    parsed = (
        raw.select(F.from_json(F.col("value").cast("string"), SPARK_DDL).alias("t"))
        .select("t.*")
        .where(F.col("vessel_id").isNotNull() & F.col("event_ts").isNotNull())
    )
    # Event time only: the watermark bounds dedup state;
    # (vessel_id, seq) makes offline flushes idempotent.
    return parsed.withWatermark("event_ts", WATERMARK).dropDuplicatesWithinWatermark(
        ["vessel_id", "seq"]
    )


def main() -> None:
    spark = (
        SparkSession.builder.appName("oceanclean-telemetry-stream")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "6")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    (
        build(spark)
        .writeStream.foreachBatch(upsert_live_state)
        .option("checkpointLocation", CHECKPOINT)
        .trigger(processingTime=TRIGGER)
        .start()
        .awaitTermination()
    )


if __name__ == "__main__":
    main()
