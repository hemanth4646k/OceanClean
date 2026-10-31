"""StreamingQueryListener progress -> pipeline_metrics rows (M5)."""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

import pipeline_metrics as pm  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402

# The fields Spark 3.5 puts in StreamingQueryProgress.json for a Kafka source (trimmed).
KAFKA_PROGRESS = {
    "id": "5c0e",
    "runId": "9a1f",
    "name": "telemetry",
    "timestamp": "2026-10-31T13:05:07.250Z",
    "batchId": 42,
    "numInputRows": 300,
    "inputRowsPerSecond": 60.5,
    "processedRowsPerSecond": 120.25,
    "durationMs": {"addBatch": 2100, "triggerExecution": 2480},
    "sources": [
        {
            "description": "KafkaV2[Subscribe[telemetry]]",
            "numInputRows": 300,
            "metrics": {
                "avgOffsetsBehindLatest": "10.0",
                "maxOffsetsBehindLatest": "17",
                "minOffsetsBehindLatest": "3",
            },
        }
    ],
}


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    s = (
        SparkSession.builder.master("local[1]")
        .appName("oceanclean-metrics-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.ivy", "/tmp/.ivy2")
        .getOrCreate()
    )
    yield s
    s.stop()


def test_kafka_progress_maps_to_a_metrics_row() -> None:
    assert pm.progress_row(KAFKA_PROGRESS) == pm.MetricsRow(
        ts=datetime(2026, 10, 31, 13, 5, 7, 250_000, tzinfo=timezone.utc),
        query="telemetry",
        batch_id=42,
        input_rows=300,
        input_rps=60.5,
        processed_rps=120.25,
        duration_ms=2480.0,
        kafka_lag=17,
    )


def test_lag_is_the_largest_over_sources_and_none_without_kafka_metrics() -> None:
    two = {**KAFKA_PROGRESS, "sources": [*KAFKA_PROGRESS["sources"], {"metrics": {}}]}
    assert pm.progress_row(two).kafka_lag == 17
    assert pm.progress_row({**KAFKA_PROGRESS, "sources": [{"metrics": {}}]}).kafka_lag is None


def test_real_progress_json_from_spark_parses(spark: SparkSession, tmp_path: Path) -> None:
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.txt").write_text("x\ny\n")
    q = (
        spark.readStream.format("text")
        .load(str(src))
        .writeStream.format("memory")
        .queryName("metrics_test")
        .option("checkpointLocation", str(tmp_path / "ckpt"))
        .start()
    )
    try:
        q.processAllAvailable()
        progress = q.lastProgress
    finally:
        q.stop()
    row = pm.progress_row(progress)
    assert (row.query, row.batch_id, row.input_rows, row.kafka_lag) == ("metrics_test", 0, 2, None)
    assert row.ts.tzinfo == timezone.utc and row.duration_ms is not None
