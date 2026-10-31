# 0001 Plain Parquet medallion lake on MinIO (no Iceberg)

Status: accepted, 2026-10-31

SRS §2.3 allows "Iceberg or Parquet". Iceberg needs a catalog service and extra Spark jars, which costs about 2 h of setup risk on a one-day build and nothing the demo audience sees. We use plain Parquet on MinIO (s3a) in a bronze/silver/gold layout, append-only, partitioned by date (and hour for ticks). Revisit if we need snapshots/time travel or schema evolution.
