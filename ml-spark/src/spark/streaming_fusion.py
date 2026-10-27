"""PySpark Structured Streaming: Kafka Ingestion & Tumbling Window Spatial Fusion."""

import logging
import os
import sys

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    from_json,
    to_timestamp,
    window,
)
from pyspark.sql.functions import (
    max as spark_max,
)
from pyspark.sql.types import (
    DoubleType,
    FloatType,
    StringType,
    StructField,
    StructType,
)

logger = logging.getLogger(__name__)

os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

TELEMETRY_SCHEMA = StructType([
    StructField("eventId", StringType(), False),
    StructField("sourceTier", StringType(), False),
    StructField("sensorDeviceId", StringType(), False),
    StructField("h3Index", StringType(), False),
    StructField("latitude", DoubleType(), False),
    StructField("longitude", DoubleType(), False),
    StructField("detectedDensityKgKm2", DoubleType(), False),
    StructField("rawConfidence", FloatType(), True),
    StructField("seaStateWaveM", DoubleType(), True),
    StructField("observedAt", StringType(), False),
])


def create_streaming_pipeline(
    kafka_brokers: str = "localhost:9092",
    topic: str = "marine.telemetry.raw",
    checkpoint_dir: str = "/tmp/spark-checkpoints/streaming_fusion",
    output_parquet_dir: str = "/tmp/marine-datalake/streaming_aggregated",
    spark: SparkSession = None,
):
    """Configures a 15-minute tumbling window PySpark Structured Streaming job

    for spatial deduplication and density aggregation by H3 cell.
    """
    if spark is None:
        spark = (
            SparkSession.builder
            .master("local[2]")
            .appName("MarineTelemetryStreamingFusion")
            .config("spark.driver.host", "127.0.0.1")
            .config("spark.driver.bindAddress", "127.0.0.1")
            .getOrCreate()
        )

    # 1. Read Kafka Stream
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_brokers)
        .option("subscribe", topic)
        .option("startingOffsets", "latest")
        .load()
    )

    # 2. Parse JSON telemetry payload
    parsed_stream = (
        raw_stream
        .selectExpr("CAST(value AS STRING) as json_payload")
        .select(from_json(col("json_payload"), TELEMETRY_SCHEMA).alias("data"))
        .select("data.*")
        .withColumn("timestamp", to_timestamp(col("observedAt")))
    )

    # 3. 15-Minute tumbling watermark window grouped by h3Index
    aggregated_stream = (
        parsed_stream
        .withWatermark("timestamp", "15 minutes")
        .groupBy(
            window(col("timestamp"), "15 minutes"),
            col("h3Index"),
        )
        .agg(
            avg("detectedDensityKgKm2").alias("avg_detected_density_kg_km2"),
            spark_max("seaStateWaveM").alias("max_sea_state_wave_m"),
            count("*").alias("event_count"),
        )
    )

    # 4. Stream sink to Parquet data lake
    query = (
        aggregated_stream.writeStream
        .format("parquet")
        .option("path", output_parquet_dir)
        .option("checkpointLocation", checkpoint_dir)
        .outputMode("append")
    )

    return query
