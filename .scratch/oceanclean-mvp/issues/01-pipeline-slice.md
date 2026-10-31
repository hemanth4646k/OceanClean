# 01 (M1) Compose + thin pipe: sim → ingestion → Kafka → Spark → PostGIS
Status: done
Blocked by: none
Estimate: 3 h

Spec: ../spec.md (Telemetry contract, Components)

## Do
- `infra/docker-compose.yml`: kafka (apache/kafka:3.7.2, KRaft, single node), postgis, minio + bucket init, spark (bitnamilegacy/spark:3.5.1, local[2]), ingestion, simulator. Memory limits per service. `.env.example`.
- `common/telemetry.py`: pydantic model, Spark StructType, `zone_of(lat, lon)`.
- `infra/postgres/init.sql`: `vessel_state` (PK vessel_id, geom Point 4326, all contract fields, updated_at).
- `ingestion/`: FastAPI `POST /telemetry` (object or list) → Kafka `telemetry` (6 partitions), key `vessel_id|zone`.
- `simulator/`: sim clock (configurable sim-seconds per real second), vessel moving on a fixed heading, emits the contract at 1 tick per sim-minute.
- `streaming/`: read Kafka, parse, watermark 10 min on event_ts, dedup (vessel_id, seq), foreachBatch UPSERT latest per vessel into `vessel_state`. Checkpoint volume.

## Done when
- `docker compose up -d` from clean; within 2 min `SELECT lat, lon, event_ts FROM vessel_state` changes between runs.
- Tests: zone_of, contract round-trip (pydantic ↔ JSON ↔ Spark schema field parity).
- Exact commands recorded in CLAUDE.md.

## Comments

2026-10-31: Done. Verified: vessel_state seq 252 → 258 within 6 s; topic `telemetry` has 6 partitions; 10 contract tests pass. Fixes along the way: PySpark 3.5 has no `StructType.fromDDL` (pass the DDL string to `from_json`); the checkpoint volume needed uid 1001 ownership. Not yet verified: a cold start from empty volumes (deleting volumes needs user approval).

2026-10-31: `/code-review` of e61bbd0 found issues, fixed in `02-m1-review-fixes.md`. Most important: the watermark dedup in `build()` drops late events (see ADR-0005). The "Do" bullet above that says "watermark 10 min … dedup" is superseded.
