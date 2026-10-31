"""Speed layer: Kafka -> parse -> per-batch dedup -> dual write (bronze lake + PostGIS) -> gate.

No watermark on these queries (ADR-0005): offline flushes, the backfill and replays are late by
design and must reach every sink. Late rows are harmless: bronze is raw history (silver dedups
on (vessel_id, seq)), and the UPSERTs only apply rows newer than the stored ones.

Three queries share the session: telemetry (dual write, then the recalc gate and optimizer),
debris surveys (latest patch positions for the optimizer, plus their own bronze history), and
the watermarked 5-minute windows (energy and the fuel-burn anomaly, `window_stream`). A listener
records every micro-batch's progress in `pipeline_metrics`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime

import psycopg
from currents import CurrentField
from oceanclean_common.debris import DEBRIS_TOPIC, SURVEY_COLUMNS, SURVEY_DDL
from oceanclean_common.regions import BRONZE_DEBRIS_SURVEY, BRONZE_TELEMETRY, EXPORT_MISSION_GRID
from oceanclean_common.settings import lake_url, pg_dsn, s3a_conf, sim_start, to_utc
from oceanclean_common.telemetry import SPARK_COLUMNS, SPARK_DDL, TELEMETRY_TOPIC
from pipeline_metrics import MetricsListener
from pyspark.errors import AnalysisException
from pyspark.sql import DataFrame, Row, SparkSession, Window
from pyspark.sql import functions as F
from route_step import Router
from stream_store import add_lake_rows
from window_stream import make_window_writer, windowed

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

SURVEY_UPSERT_SQL = f"""
INSERT INTO debris_patches ({", ".join(SURVEY_COLUMNS)}, geom, updated_at)
VALUES ({", ".join(["%s"] * len(SURVEY_COLUMNS))}, ST_SetSRID(ST_MakePoint(%s, %s), 4326), now())
ON CONFLICT (patch_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in SURVEY_COLUMNS if c != "patch_id")},
  geom = EXCLUDED.geom, updated_at = now()
WHERE debris_patches.survey_ts < EXCLUDED.survey_ts
"""


def parse_json(raw: DataFrame, ddl: str, *required: str) -> DataFrame:
    """Kafka `value` (producer JSON) -> contract columns; rows missing a key column are dropped."""
    parsed = raw.select(F.from_json(F.col("value").cast("string"), ddl).alias("t")).select("t.*")
    for c in required:
        parsed = parsed.where(F.col(c).isNotNull())
    return parsed


def parse_telemetry(raw: DataFrame) -> DataFrame:
    return parse_json(raw, SPARK_DDL, "vessel_id", "event_ts")


def parse_survey(raw: DataFrame) -> DataFrame:
    return parse_json(raw, SURVEY_DDL, "patch_id", "survey_ts")


def dedup_batch(batch: DataFrame) -> DataFrame:
    """Stateless in-batch dedup on (vessel_id, seq); history dedup is the silver job's."""
    return batch.dropDuplicates(["vessel_id", "seq"])


def newest_per(batch: DataFrame, key: str, *order: str) -> DataFrame:
    w = Window.partitionBy(key).orderBy(*(F.col(c).desc() for c in order))
    return batch.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def latest_per_vessel(batch: DataFrame) -> DataFrame:
    """Newest row per vessel by event time (seq breaks ties); only it can move live state."""
    return newest_per(batch, "vessel_id", "event_ts", "seq")


def stale_rows(batch: DataFrame, stored: DataFrame) -> DataFrame:
    """Rows not newer than the stored live state (STORED_DDL), i.e. ones the UPSERT ignores."""
    return batch.join(F.broadcast(stored), "vessel_id").where(
        F.col("event_ts") <= F.col("stored_ts")
    )


def bronze_partitions(batch: DataFrame, ts: str) -> DataFrame:
    """Event-time (sim time, UTC) partition columns: late rows land in their own hour."""
    return batch.withColumn("date", F.to_date(ts)).withColumn("hour", F.hour(ts))


def append_bronze(batch: DataFrame, url: str, *by: str) -> None:
    """Append-only history (ADR-0001): never overwrite or update lake rows."""
    batch.coalesce(1).write.mode("append").partitionBy(*by).parquet(url)


def _upsert_params(r: Row, cols: tuple[str, ...], ts: str) -> tuple[object, ...]:
    values = (to_utc(r[c]) if c == ts else r[c] for c in cols)
    return (*values, r["lon"], r["lat"])


def make_writer(dsn: str, bronze_url: str, router: Router) -> Callable[[DataFrame, int], None]:
    def write_batch(batch: DataFrame, batch_id: int) -> None:
        batch.persist()
        try:
            total = batch.count()
            if total == 0:
                return
            unique = dedup_batch(batch)
            n_unique = unique.count()
            append_bronze(bronze_partitions(unique, "event_ts"), bronze_url, "date", "hour")
            latest = latest_per_vessel(unique).select(*SPARK_COLUMNS).collect()
            with psycopg.connect(dsn) as conn:
                stored = conn.execute(
                    "SELECT vessel_id, event_ts FROM vessel_state WHERE vessel_id = ANY(%s)",
                    [[r["vessel_id"] for r in latest]],
                ).fetchall()
                stored_df = batch.sparkSession.createDataFrame(stored, STORED_DDL)
                n_stale = stale_rows(unique, stored_df).count() if stored else 0
                conn.cursor().executemany(
                    UPSERT_SQL, [_upsert_params(r, SPARK_COLUMNS, "event_ts") for r in latest]
                )
                add_lake_rows(conn, BRONZE_TELEMETRY, n_unique)
            log.info(
                "batch %d: %d rows, %d duplicate (vessel_id, seq) dropped, %d to bronze, "
                "%d not newer than live state (late/replayed), %d vessel(s) offered to UPSERT",
                batch_id,
                total,
                total - n_unique,
                n_unique,
                n_stale,
                len(latest),
            )
        finally:
            batch.unpersist()
        # Routing is advisory: a planner bug must not stop the sinks above.
        for r in latest:
            try:
                with psycopg.connect(dsn) as conn:
                    router.step(conn, r["vessel_id"])
            except Exception:
                log.exception("routing step failed for %s", r["vessel_id"])

    return write_batch


def make_survey_writer(dsn: str, bronze_url: str) -> Callable[[DataFrame, int], None]:
    def write_batch(batch: DataFrame, batch_id: int) -> None:
        batch.persist()
        try:
            n = batch.count()
            if n == 0:
                return
            append_bronze(bronze_partitions(batch, "survey_ts").drop("hour"), bronze_url, "date")
            latest = newest_per(batch, "patch_id", "survey_ts").select(*SURVEY_COLUMNS).collect()
            with psycopg.connect(dsn) as conn:
                conn.cursor().executemany(
                    SURVEY_UPSERT_SQL,
                    [_upsert_params(r, SURVEY_COLUMNS, "survey_ts") for r in latest],
                )
                add_lake_rows(conn, BRONZE_DEBRIS_SURVEY, n)
            live = sum(1 for r in latest if r["mass_kg"] > 0)
            log.info("survey batch %d: %d patches (%d with debris)", batch_id, len(latest), live)
        finally:
            batch.unpersist()

    return write_batch


def read_kafka(
    spark: SparkSession, bootstrap: str, topic: str, offsets: str = "earliest"
) -> DataFrame:
    # failOnDataLoss stays at its default (true): lost offsets must fail the query loudly.
    # startingOffsets applies only to a fresh checkpoint; a restart resumes from its offsets.
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", offsets)
        .option("maxOffsetsPerTrigger", 200_000)
        .load()
    )


def field_loader(
    spark: SparkSession, url: str, sim_start: datetime
) -> Callable[[], CurrentField | None]:
    def load() -> CurrentField | None:
        try:
            data = spark.read.format("binaryFile").load(url).select("content").first()
        except AnalysisException:
            return None
        return None if data is None else CurrentField.from_npz(bytes(data[0]), sim_start)

    return load


def main() -> None:
    # Root at WARNING: py4j logs every gateway call at INFO and would bury the batch lines.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    for name in ("telemetry_stream", "window_stream", "pipeline_metrics"):
        logging.getLogger(name).setLevel(logging.INFO)
    env = os.environ
    builder = (
        SparkSession.builder.appName("oceanclean-telemetry-stream")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", env["TELEMETRY_PARTITIONS"])
    )
    for k, v in s3a_conf(env).items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    dsn, bootstrap, trigger = pg_dsn(env), env["KAFKA_BOOTSTRAP"], env["STREAM_TRIGGER"]
    router = Router(field_loader(spark, lake_url(env, EXPORT_MISSION_GRID), sim_start(env)))
    spark.streams.addListener(MetricsListener(dsn))
    (
        parse_telemetry(read_kafka(spark, bootstrap, TELEMETRY_TOPIC))
        .writeStream.queryName("telemetry")
        .foreachBatch(make_writer(dsn, lake_url(env, BRONZE_TELEMETRY), router))
        .option("checkpointLocation", env["CHECKPOINT_DIR"])
        .trigger(processingTime=trigger)
        .start()
    )
    (
        parse_survey(read_kafka(spark, bootstrap, DEBRIS_TOPIC))
        .writeStream.queryName("debris_survey")
        .foreachBatch(make_survey_writer(dsn, lake_url(env, BRONZE_DEBRIS_SURVEY)))
        .option("checkpointLocation", env["SURVEY_CHECKPOINT_DIR"])
        .trigger(processingTime=trigger)
        .start()
    )
    # "latest": events of a run before a sim reset would push the watermark past the new run.
    (
        windowed(parse_telemetry(read_kafka(spark, bootstrap, TELEMETRY_TOPIC, "latest")))
        .writeStream.queryName("windows")
        .outputMode("append")
        .foreachBatch(make_window_writer(dsn, float(env["SIM_TICK_SECONDS"])))
        .option("checkpointLocation", env["WINDOW_CHECKPOINT_DIR"])
        .trigger(processingTime=trigger)
        .start()
    )
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
