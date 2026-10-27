"""Phase 4 Verification Gate Tests: PySpark Batch MLlib Hotspot Discovery."""

import h3
import pytest

from src.spark.batch_hotspots import discover_gyre_hotspots, get_spark_session
from src.spark.seed_datalake import generate_synthetic_telemetry


@pytest.fixture(scope="module")
def sample_parquet_data(tmp_path_factory):
    tmp_dir = str(tmp_path_factory.mktemp("telemetry_lake"))
    # Generate 5,000 synthetic rows for rapid test execution
    generate_synthetic_telemetry(num_rows=5_000, output_path=tmp_dir)
    return tmp_dir


def test_spark_mllib_hotspot_clustering(sample_parquet_data):
    """Success Criteria: Pytest executes a local SparkSession('local[2]') over sample Parquet data

    and returns top convergence zone centroids with non-zero plastic tonnage estimates.
    """
    spark = get_spark_session("Pytest-SparkAnalytics")
    try:
        result = discover_gyre_hotspots(parquet_path=sample_parquet_data, k=3, spark=spark)

        assert result["status"] == "SUCCESS"
        assert result["cluster_count"] == 3
        assert result["total_telemetry_analyzed"] >= 5_000

        hotspots = result["hotspots"]
        assert len(hotspots) == 3

        for h in hotspots:
            # 1. Centroid coordinates fall within North Pacific Gyre bounds
            assert 20.0 <= h["center_latitude"] <= 45.0, f"Lat {h['center_latitude']} outside gyre"
            assert -165.0 <= h["center_longitude"] <= -130.0, f"Lon {h['center_longitude']} outside gyre"

            # 2. Non-zero plastic tonnage estimates
            assert h["estimated_plastic_tonnage"] > 0, "Tonnage should be strictly positive"
            assert h["avg_polymer_density_kg_km2"] > 0
            assert h["telemetry_observations"] > 0

            # 3. Valid H3 resolution 6 representation
            h3_cell = h["h3_index_res6"]
            assert h3.is_valid_cell(h3_cell) is True
            assert h3.get_resolution(h3_cell) == 6

        # Verify sorted by plastic tonnage descending
        tonnages = [h["estimated_plastic_tonnage"] for h in hotspots]
        assert tonnages == sorted(tonnages, reverse=True)
    finally:
        spark.stop()
