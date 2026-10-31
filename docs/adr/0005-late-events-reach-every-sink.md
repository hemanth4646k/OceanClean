# 0005 Late events reach every sink; watermarks only bound aggregations

Status: accepted, 2026-10-31 (from the M1 code review)

M1 put `withWatermark("event_ts", "10 minutes").dropDuplicatesWithinWatermark(["vessel_id","seq"])` upstream of `foreachBatch`. Spark drops rows older than the watermark before they reach any sink. Three features are late by design: offline-buffer flushes (`buffered=true`), the 30-day `--fast-forward` backfill, and anything replayed after an outage. All three would be silently lost from the lake and from live state. At `SIM_RATE=60`, the 10 sim-minute watermark is about 10 real seconds.

Decision:
- The main stream (parse → validate) has **no watermark**. Its `foreachBatch` writes every row: append to bronze Parquet (M3) and the guarded UPSERT into `vessel_state`. Duplicates and late rows are harmless there, because the UPSERT only applies events newer than the stored row, and bronze is raw by definition.
- In-batch dedup on `(vessel_id, seq)` (`dropDuplicates` inside `foreachBatch`, which is stateless) keeps obvious replays out of bronze.
- History dedup is a batch concern: the silver job deduplicates on `(vessel_id, seq)` over the full partition.
- Watermarks are used **only** by the separate windowed-aggregation query (5-min tumbling windows, M5). Late rows missing from a window there are acceptable and documented.
