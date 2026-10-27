"""PySpark MLlib Batch Analytics: BisectingKMeans Macro-Scale Gyre Convergence Hotspot Discovery."""

import logging
import os
import sys
from typing import Any

import h3
from pyspark.ml.clustering import BisectingKMeans
from pyspark.ml.feature import VectorAssembler
from pyspark.sql import SparkSession
from pyspark.sql.functions import avg, count
from pyspark.sql.functions import sum as spark_sum

logger = logging.getLogger(__name__)

# Ensure PySpark workers match driver Python binary and bind to local address in sandbox
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable


def get_spark_session(app_name: str = "OceanClean-Hotspots") -> SparkSession:
    """Builds or retrieves a SparkSession configured with local IP bindings."""
    return (
        SparkSession.builder
        .master("local[2]")
        .appName(app_name)
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )


def discover_gyre_hotspots(
    parquet_path: str,
    k: int = 3,
    spark: SparkSession | None = None,
) -> dict[str, Any]:
    """Runs distributed BisectingKMeans clustering over historical Parquet telemetry

    to discover major marine plastic convergence zones with estimated plastic tonnage.
    """
    should_stop_spark = False
    if spark is None:
        spark = get_spark_session()
        should_stop_spark = True

    try:
        if not os.path.exists(parquet_path):
            raise FileNotFoundError(f"Parquet path {parquet_path} does not exist")

        df = spark.read.parquet(parquet_path)
        row_count = df.count()
        if row_count == 0:
            return {"hotspots": [], "total_records": 0, "cluster_count": 0}

        # 1. Feature Assembly: Spatial coordinates [latitude, longitude]
        assembler = VectorAssembler(
            inputCols=["latitude", "longitude"],
            outputCol="features",
        )
        assembled_df = assembler.transform(df)

        # 2. Spark MLlib BisectingKMeans clustering
        bkm = BisectingKMeans(
            k=k,
            featuresCol="features",
            predictionCol="cluster_id",
            weightCol="polymer_density_kg_km2",
            seed=42,
        )
        model = bkm.fit(assembled_df)
        clustered_df = model.transform(assembled_df)

        # 3. Aggregate cluster statistics
        # In Gyre resolution-7 cells, area ~ 5.16 km^2. Total plastic mass = sum(density * 5.16) kg -> / 1000 for metric tons
        cluster_stats = (
            clustered_df
            .groupBy("cluster_id")
            .agg(
                avg("latitude").alias("center_lat"),
                avg("longitude").alias("center_lon"),
                avg("polymer_density_kg_km2").alias("avg_density"),
                spark_sum("polymer_density_kg_km2").alias("sum_density"),
                count("*").alias("sample_count"),
            )
            .collect()
        )

        hotspots: list[dict[str, Any]] = []
        for row in cluster_stats:
            c_lat = float(row["center_lat"])
            c_lon = float(row["center_lon"])
            avg_density = float(row["avg_density"])
            sum_density = float(row["sum_density"])
            sample_cnt = int(row["sample_count"])

            # Approximate tonnage: sum of density * 5.16 km2 / 1000
            estimated_tonnage = round((sum_density * 5.16) / 1000.0, 2)
            c_h3 = h3.latlng_to_cell(c_lat, c_lon, 6)  # Resolution 6 for macro-hotspot representation

            hotspots.append({
                "cluster_id": int(row["cluster_id"]),
                "center_latitude": round(c_lat, 4),
                "center_longitude": round(c_lon, 4),
                "h3_index_res6": c_h3,
                "avg_polymer_density_kg_km2": round(avg_density, 2),
                "estimated_plastic_tonnage": estimated_tonnage,
                "telemetry_observations": sample_cnt,
            })

        # Sort hotspots by plastic tonnage descending
        hotspots.sort(key=lambda x: x["estimated_plastic_tonnage"], reverse=True)

        return {
            "status": "SUCCESS",
            "cluster_count": len(hotspots),
            "total_telemetry_analyzed": row_count,
            "hotspots": hotspots,
        }
    finally:
        if should_stop_spark:
            spark.stop()
