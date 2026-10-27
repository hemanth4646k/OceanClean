"""Synthetic Big Data Parquet Seeder for Marine Telemetry Data Lake."""

import logging
import os
import random
import uuid
from datetime import datetime, timedelta

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Gyre boundary: 25N - 40N, 135W - 160W
MIN_LAT, MAX_LAT = 25.0, 40.0
MIN_LON, MAX_LON = -160.0, -135.0

# 3 synthetic high-accumulation convergence centers inside the Gyre
GYRE_CENTROIDS = [
    (32.5, -145.0, 45.0),  # Eastern Pacific Subtropical convergence
    (28.0, -152.0, 35.0),  # Central Gyre Core
    (35.2, -139.5, 55.0),  # North-East Sub-loop
]


def generate_synthetic_telemetry(
    num_rows: int = 100_000,
    output_path: str = "/tmp/marine-datalake/parquet/year=2026/month=10",
) -> str:
    """Generates synthetic telemetry rows and writes them as partitioned Parquet files."""
    os.makedirs(output_path, exist_ok=True)
    logger.info("Generating %d synthetic telemetry rows in %s...", num_rows, output_path)

    sources = ["SATELLITE_SAR", "AERIAL_UAV", "VESSEL_OPTICAL", "DRIFT_BUOY"]
    base_time = datetime(2026, 10, 1, 0, 0, 0)

    # Pre-generate arrays with numpy for speed
    event_ids = [str(uuid.uuid4()) for _ in range(num_rows)]
    source_tiers = np.random.choice(sources, size=num_rows, p=[0.4, 0.3, 0.15, 0.15])

    # Cluster points around the 3 gyre centroids with Gaussian noise
    chosen_centroids = np.random.choice(len(GYRE_CENTROIDS), size=num_rows, p=[0.4, 0.35, 0.25])
    lats = np.zeros(num_rows, dtype=np.float64)
    lons = np.zeros(num_rows, dtype=np.float64)
    densities = np.zeros(num_rows, dtype=np.float64)

    for idx, (c_lat, c_lon, base_density) in enumerate(GYRE_CENTROIDS):
        mask = (chosen_centroids == idx)
        count = np.sum(mask)
        if count > 0:
            lats[mask] = np.clip(np.random.normal(c_lat, 2.0, count), MIN_LAT, MAX_LAT)
            lons[mask] = np.clip(np.random.normal(c_lon, 3.5, count), MIN_LON, MAX_LON)
            densities[mask] = np.clip(np.random.normal(base_density, 12.0, count), 1.0, 150.0)

    sea_states = np.clip(np.random.normal(2.2, 0.8, num_rows), 0.5, 6.0)
    confidences = np.clip(np.random.normal(0.82, 0.1, num_rows), 0.5, 0.99)
    timestamps = [
        (base_time + timedelta(seconds=int(random.random() * 26 * 86400))).isoformat() + "Z"
        for _ in range(num_rows)
    ]

    # Compute resolution-7 H3 indexes
    h3_indexes = [
        h3.latlng_to_cell(float(lats[i]), float(lons[i]), 7)
        for i in range(num_rows)
    ]

    schema = pa.schema([
        ("event_id", pa.string()),
        ("source_tier", pa.string()),
        ("latitude", pa.float64()),
        ("longitude", pa.float64()),
        ("h3_index", pa.string()),
        ("detected_density_kg_km2", pa.float64()),
        ("polymer_density_kg_km2", pa.float64()),
        ("raw_confidence", pa.float64()),
        ("sea_state_wave_m", pa.float64()),
        ("observed_at", pa.string()),
    ])

    table = pa.Table.from_arrays(
        [
            pa.array(event_ids),
            pa.array(source_tiers),
            pa.array(lats),
            pa.array(lons),
            pa.array(h3_indexes),
            pa.array(densities),
            pa.array(densities),  # polymer density matches detected density
            pa.array(confidences),
            pa.array(sea_states),
            pa.array(timestamps),
        ],
        schema=schema,
    )

    parquet_file = os.path.join(output_path, "telemetry_part_000.parquet")
    pq.write_table(table, parquet_file, compression="SNAPPY")
    logger.info("Successfully wrote %d rows to %s", num_rows, parquet_file)
    return parquet_file


if __name__ == "__main__":
    generate_synthetic_telemetry(100_000)
