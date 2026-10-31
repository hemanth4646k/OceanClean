# 02 (M1.5) Fix the M1 code-review findings
Status: done
Blocked by: 01
Estimate: 45 min

Source: `/code-review` of commit `e61bbd0` (since `f1c5d4b`), 2026-10-31. Read CLAUDE.md first, especially "Streaming and data rules" and "Pitfalls", plus `docs/adr/0005-late-events-reach-every-sink.md`. Start the review for this ticket from `e61bbd0`.

Work test-first (`/tdd`) where a pure function exists; otherwise verify against the running stack. Don't start M2 until everything under "Done when" passes.

## Must fix (correctness)

1. **Late events are dropped before any sink** (`streaming/telemetry_stream.py` `build()`). `withWatermark(...).dropDuplicatesWithinWatermark(...)` discards rows older than the watermark, which would lose offline-buffer flushes, the backfill and bronze history. Apply ADR-0005:
   - Remove the watermark and stateful dedup from the main query.
   - Inside `foreachBatch`, `dropDuplicates(["vessel_id", "seq"])` (stateless), then UPSERT the newest row per vessel. The existing `WHERE vessel_state.event_ts < EXCLUDED.event_ts` guard already makes late rows harmless.
   - Log each batch's row count, plus how many rows were older than the stored state, so late arrivals show up in the logs.
2. **`failOnDataLoss=false`** (same file): remove it, since the default is `true`. Data loss must fail loudly.
3. **Ingestion returns 202 even when Kafka didn't acknowledge** (`ingestion/ingestion_app.py` `ingest()`):
   - Register a delivery callback per request that collects errors.
   - Check `producer.flush(timeout)`'s return value; anything still queued means failure.
   - Return 503 if any event wasn't acknowledged, 202 only when all were.
   - Fix the "without loss" comment so it matches the behaviour.
4. **Timestamps depend on the container's timezone**:
   - Add `TZ: UTC` to every service in `infra/docker-compose.yml`. A YAML anchor shared by all services is fine.
   - In `upsert_live_state`, make `collect()`ed `event_ts` values explicitly UTC-aware before passing them to psycopg (Spark returns naive datetimes in the Python process's local zone).
   - Optionally also set `spark.driver.extraJavaOptions=-Duser.timezone=UTC`.

## Must fix (standards)

5. **Credentials hardcoded in Compose**: `PG_DSN: postgresql://ocean:ocean@postgis:5432/oceanclean` in `infra/docker-compose.yml` (spark-stream).
   - Remove it. Build the DSN in code from `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`, plus a `POSTGRES_HOST` (default `postgis`) and port.
   - Put the helper in `common/oceanclean_common/` so the API can reuse it in M4, and add a unit test.
6. **Fresh checkout fails without `.env`**: every service uses `env_file: ../.env`.
   - Make it optional: Compose ≥ 2.24 accepts `env_file: [{ path: ../.env, required: false }]`. Check `docker compose version` first.
   - Make `.env.example` hold the only defaults: either Compose reads `../.env.example` as a fallback, or code defaults match it exactly.
   - Each setting gets exactly one default.
7. **Missing type hints** (CLAUDE.md: "type hints on every function"):
   - `ingestion_app.lifespan` should be `-> AsyncIterator[None]`.
   - `tests/test_sim_state.py` `tmp_path` should be typed as `pathlib.Path`.
   - Enable ruff's `ANN` rules in `pyproject.toml` (ignore `ANN401` if needed) so tooling enforces this from now on.

## Should fix (contract test strength)

8. **The contract test only compares field names**:
   - Extend `tests/test_telemetry.py` to compare **types** too: a mapping pydantic type → DDL type, e.g. `str→STRING`, `datetime→TIMESTAMP`, `int→BIGINT`, `float→DOUBLE`, `bool→BOOLEAN`.
   - Parse `infra/postgres/init.sql` and check that every contract column exists in `vessel_state` with a compatible type.
9. **No test parses producer JSON with Spark's schema**:
   - Add a Spark fixture test, run inside the `oceanclean-spark` image with `local[1]`, that runs `from_json(value, SPARK_DDL)` on `Telemetry.to_json()` output and asserts every field is non-null and `event_ts` is the exact UTC instant.
   - Move the latest-per-vessel and in-batch-dedup logic into a function that takes and returns a DataFrame (no I/O), and test it on a 5-row fixture: a duplicate seq, a late row, and two vessels.
   - Record the command to run Spark tests in CLAUDE.md "Commands".

## Cheap cleanups (smells; do these, they're minutes)

10. Add `SPARK_COLUMNS` to `telemetry.py`. Use it in the stream job and the test instead of re-parsing the DDL in two places.
11. Single source for the partition count: Compose `KAFKA_NUM_PARTITIONS`, ingestion `TELEMETRY_PARTITIONS` and Spark `spark.sql.shuffle.partitions` all hardcode `6`. Read it from one env var (`TELEMETRY_PARTITIONS` in `.env.example`).
12. `sim_state`: the `clock_now` key actually stores the **next tick** time. Rename it to `next_tick` (keep reading the old key once so the existing state file still loads).
13. Vessel id `"OC-01"` is hardcoded in `sim_main.py` and in the Compose `SIM_STATE_FILE`. Use one `VESSEL_ID` env var and derive the state-file path from it.
14. `ensure_topics` loops over a 1-tuple and has a conditional generator. Simplify it to create the single topic only if it's missing.

## Not in scope (judgement calls, leave for later)

- Data clumps (`lat, lon` / `u, v` pairs, bare-string zone ids): revisit in M3 when routing adds a `LatLon` type.
- Python 3.11 in the images vs ruff `py310`: harmless; the code stays 3.10-compatible.
- The partly speculative `u_ms`/`v_ms` args of `step_position`: M3 uses them.

## Done when

- `pytest` (Python image) and the Spark fixture tests pass; `ruff check` passes with `ANN` enabled.
- **Late-event proof against the running stack:**
  - POST an event with a new `seq` but an `event_ts` 2 sim-hours older than the live state. The stream log shows it was processed (counted as older than the stored state), not dropped, and `vessel_state` is unchanged.
  - POST the same `seq` twice in one batch. The batch log shows it deduplicated.
- **Ack proof:** with Kafka stopped (`docker compose stop kafka`), `POST /telemetry` returns 503 within the timeout instead of 202. Restart Kafka afterwards.
- **No credential literals:** `grep -rn "ocean:ocean" infra/ streaming/ ingestion/` finds nothing.
- **Cold start:** **ask the user before** running `docker compose -f infra/docker-compose.yml down -v`, which deletes this project's volumes. Once they agree, run it, then `up -d --build`; within 2 minutes `vessel_state` updates. This was blocked in M1.
- Update this ticket's Status, add a Comments entry and update CLAUDE.md Status **in the same commit** as the fixes. Then run `/code-review` since `e61bbd0`.

## Comments

2026-10-31: Done. Verified on a cold start (`down -v`, approved by the user, then `up -d --build`): `vessel_state` populated 10 s after `up` returned. Late-event proof: a new seq 2 sim-hours older than live state was logged as "1 not newer than live state" in batch 18 and left `vessel_state` untouched; a same-seq pair POSTed together was logged as "1 duplicate (vessel_id, seq) dropped" in batch 21. Ack proof: with Kafka stopped, `POST /telemetry` returned 503 ("kafka acknowledged 0/1 events") after 3.0 s; after `start kafka` live state advanced again within 7 s. `grep -rn "ocean:ocean" infra/ streaming/ ingestion/` is empty. 18 Python tests and 5 Spark fixture tests pass (the Spark tests also pass under `TZ=Asia/Kolkata`); ruff passes with `ANN`.

Decisions along the way:
- Every setting's only default is in `.env.example`. Compose loads it, then an optional `.env`; code uses `os.environ[...]` with no fallbacks. `tests/test_settings.py` fails if code reads a setting that's missing from `.env.example` or adds a second default via `.get()`.
- The contract is one `SPARK_FIELDS` tuple of (name, type); `SPARK_DDL` and `SPARK_COLUMNS` are derived from it.
- Kafka auto-create is disabled and `KAFKA_NUM_PARTITIONS` removed: ingestion creates the topic with `TELEMETRY_PARTITIONS`, so an auto-created topic can't silently get 1 partition.
- Kafka gets no `env_file`, because the image turns every `KAFKA_*` variable into a broker property.
- The flush timeout is 3 s, below the simulator's 5 s HTTP timeout, so the simulator sees a 503 and not a client timeout. The simulator now logs non-2xx responses (`raise_for_status`), but it still drops the tick: the offline buffer is ticket 04 work.
- Python's naive `collect()` datetimes are converted with `astimezone(timezone.utc)`, which is correct in any process timezone (`replace(tzinfo=utc)` would be off by the local offset).
- Spark image: added pytest, plus `pyspark`/`py4j` on `PYTHONPATH` (ENV only). The test fixture sets `spark.jars.ivy=/tmp/.ivy2`, because the host uid has no passwd entry and the JVM home falls back to `?`.
- Not verified: Compose with no `.env` file at all. A permission rule blocks moving `.env`; `docker compose config` resolves with the optional entry, which Compose 2.40 supports.

2026-10-31: `/code-review` since 3168de6 (both axes). Fixed in a follow-up commit:
- Ingestion now waits for **this request's** delivery reports instead of trusting `flush()`'s return value. Sync routes share the producer across threadpool workers, so `flush()` counted other requests' queued messages and could return spurious 503s. This replaces the "check `flush()`'s return value" bullet above. Verified: 40 concurrent POSTs all returned 202, and with Kafka stopped a POST still returns 503 after 3.0 s.
- The stream job's root logger is at WARNING. At INFO, py4j logged every gateway call and outnumbered the batch lines (125 vs 122); now there are none.

Left open (judgement calls, not ticket requirements):
- Rows dropped by `parse_telemetry` (malformed JSON, null id or ts) aren't counted in the batch log. This predates M1.5; add a parse-failure count when bronze lands (ticket 04).
- Container ports and mount paths (`--port 8000`, `/state`, `/checkpoints`, `5433:5432`) still appear in Compose next to the settings that reference them.
- pytest ships in the runtime Spark image (a few MB).
- Ingestion logs through `uvicorn.error`, so its warnings show in uvicorn's output.
- `_upsert_params` converts by column name (`event_ts`), not by `TIMESTAMP` type.
- The stale count uses `<=`, i.e. "not newer than live state", which is exactly what the UPSERT ignores; the log line says so.
