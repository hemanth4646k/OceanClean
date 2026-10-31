# OceanClean

Big Data (BDA course) prototype: a single-vessel, dynamic route optimizer for ocean plastic cleanup. Synthetic IoT telemetry + public ocean-current data (Copernicus/NOAA) flow through a Lambda architecture to a live map. Goal: maximize debris collected per unit of vessel energy by anticipating drift.

Source of truth for requirements: [software_requirements_specification.md](software_requirements_specification.md). If code and SRS disagree, surface it; don't silently pick one.
UI: dark maritime theme. Live map with current particles and a control panel, an operator "AI Route Optimization" Accept/Modify/Reject modal, and admin Metrics/Analytics dashboards.

## Architecture (see SRS §2)

```
sim vessels ─► ingestion API ─► Kafka ─► Spark Structured Streaming ─┬─► PostGIS (UPSERT live state, routes)
 (offline buffer)  (partition: vessel_id + zone)   (watermark, checkpoint)  └─► MinIO/S3 Parquet|Iceberg (append-only ticks)
Copernicus/NOAA NetCDF/GRIB ─► PySpark batch ETL ─► u/v drift grid (Parquet, spatio-temporal partitions)
PostGIS + drift grid ─► route optimizer (threshold-gated recalc) ─► waypoints ─► PostGIS ─► REST + WebSocket ─► React UI
```

- **Speed layer**: Spark Structured Streaming, checkpointing mandatory. Watermarks bound **only** windowed aggregations; the lake and live-state sinks receive every event, late or not (ADR-0005).
- **Batch layer**: PySpark ETL, interpolate `u`/`v` vectors onto a standard grid.
- **Dual write**: PostGIS = mutable live state; lake = immutable history. Never update lake rows in place.
- **Recalc gate**: heavy route recompute only when drift deviation exceeds a threshold (SRS §3.3). Target SLA < 60 s for a local grid.
- **Human-in-the-loop**: operator Accept/Reject/Modify; on ignore/timeout the vessel holds trajectory or loiters (fail-safe, SRS §5.4).

## Stack (open-source only, no vendor lock-in, SRS §4.3)

Python, Apache Kafka, Spark/PySpark, PostgreSQL+PostGIS, MinIO, Parquet/Iceberg, Docker Compose. Frontend: React, shadcn/ui, Tailwind (dark default), Recharts, Leaflet or OpenLayers with a 2D canvas velocity-particle overlay (no 3D/WebGL). Desktop and landscape-tablet (1080p+) only; no mobile.

Out of scope: fleet orchestration, physical hardware. Single vessel only.

## Layout (planned; create as needed, keep this list current)

```
infra/        docker-compose.yml, service configs
common/       shared telemetry contract, geo/zone helpers
simulator/    synthetic vessel + offline-queue telemetry producers
ingestion/    ingestion endpoint -> Kafka
streaming/    Spark Structured Streaming jobs
batch/        PySpark ocean-current ETL
routing/      optimizer + recalc threshold logic
api/          REST + WebSocket server
web/          React frontend
docs/adr/     architecture decisions;  docs/agents/  skill config;  docs/images/  README screenshots
.scratch/     local-markdown specs and tickets
```

## Status

Planning done (grilling 2026-10-31). Demo is a live demo + presentation on 2026-11-01. Spec: `.scratch/oceanclean-mvp/spec.md`; milestones `issues/01..07`; decisions in `docs/adr/0001..0009`; terms in `GLOSSARY.md`. Resolved: telemetry schema (frozen in spec), Compose set, Spark 3.5.1 on Java 17 via `bitnamilegacy/spark:3.5.1` in `local[2]`, plain Parquet (no Iceberg), own intercept optimizer, NOAA SCUD + NCEI microplastics with fetch-and-cache, sim clock, single cleaner. M1 done (pipe works). M1.5 review fixes done (`issues/02`): late events reach every sink, Kafka acks are checked, settings live only in `.env.example`, contract tests cover types and Spark parsing, cold start verified. M2 done (`issues/03`): fetch-and-cache of SCUD currents + NCEI microplastics, Spark ETL to silver/gold, hotspot validation 3.9× (median), mission-grid + hotspot exports, works offline. M3 done (`issues/04`): pure-Python routing library (`routing/`), simulator debris world + route follower + offline buffer + fuel/battery, `debris_survey` topic → `debris_patches`, foreachBatch dual write (bronze ticks + guarded UPSERT) with the recalc gate proposing `pending` routes (ADR-0007). M4 done (`issues/05`): FastAPI `api/` (REST, `/ws` snapshot + deltas + alerts, accept/reject transitions, sim clock control via the `sim_clock` table) and the `web/` live map (offline base map, canvas current particles, heat, hotspots, patches, ghosts + drift lines, route, wake, clock bar), served by nginx on :8080. M5 done (`issues/06`): HITL autopilot (default) or operator modal with the sim clock held, 30 s timeout → expired, Modify (ADR-0008); a third, watermarked 5-min window query scoring derived energy and a fuel-burn anomaly → `alerts` → toasts; a StreamingQueryListener → `pipeline_metrics`; the `telemetry-etl` batch job (silver/gold telemetry → `analytics.json`); Metrics and Analytics tabs (Recharts) behind the Admin role. M6 done (`issues/07`): `--fast-forward 30d` backfill of the previous mission at 1 Hz (2.59M events in ~3.5 min, ADR-0009; live seqs start at 10,000,001), silver segments on seq gaps, and the time slider (`/replay`: hotspot parcels drifting through the mission window's real currents). Submission: root `README.md` (overview, run steps, screenshots in `docs/images/`), MIT `LICENSE`. Presentation prep left to the user (not tracked): a network-off rehearsal and a 2-min backup video.

## Environment (dev machine)

Docker 29, Node 26, Python 3.10, Java 22. `uv` and `ripgrep` not installed. Spark 3.5 does not reliably support Java 22; run Spark in a container pinned to Java 17. Command output is compressed by the global `rtk` hook; re-run as `rtk bypass <cmd>` only if a result looks wrong.

## Commands

All from the repo root. Compose reads `.env.example` (the only defaults); create a `.env` only to override values.

```
./start.sh   # whole stack: build, batch layer on a fresh lake (infra/minio/has_objects.py checks the exports), up, wait for the API
./stop.sh    # down (batch profile too), volumes kept
docker compose -f infra/docker-compose.yml up -d --build      # whole stack
docker compose -f infra/docker-compose.yml logs -f spark-stream
docker exec oceanclean-postgis-1 psql -U ocean -d oceanclean -c "select seq, event_ts, lat, lon from vessel_state"
docker run --rm -u "$(id -u)" -e HOME=/tmp --network oceanclean_default --env-file .env.example -v "$PWD":/app -w /app oceanclean-py sh -c "pytest -q && ruff check . && ruff format --check ."   # tests + lint; network/env let tests/test_store.py reach PostGIS (skipped otherwise)
docker run --rm -u "$(id -u)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/app -w /app oceanclean-spark python -m pytest -q -p no:cacheprovider tests/*_spark.py   # Spark fixture tests (skipped in the py image); bitnami's entrypoint gives the uid a passwd entry, so streaming/file writes work
# Batch layer (M2): fetch NOAA data (API, else data/cache) -> bronze, then Spark ETL -> silver/gold/exports.
mkdir -p data/cache   # before the first fetch, or Docker creates it root-owned
docker compose -f infra/docker-compose.yml --profile batch run --rm --build -u "$(id -u):$(id -g)" fetch
docker compose -f infra/docker-compose.yml --profile batch run --rm spark-batch
docker exec oceanclean-postgis-1 psql -U ocean -d oceanclean -c "select dataset, source, fetched_at from data_sources"
# Telemetry history (M5): bronze ticks -> silver (dedup, per-tick energy/debris) -> gold daily(+zone) -> analytics.json.
# The `analytics` service (part of `up -d`) reruns it every ANALYTICS_REFRESH_S; run it by hand for an immediate refresh:
docker compose -f infra/docker-compose.yml --profile batch run --rm telemetry-etl
docker compose -f infra/docker-compose.yml logs --tail 5 analytics
# Live map (M4): http://localhost:8080 (nginx, proxies /api and /ws to the API on :8002). Time slider (M6): "Open time slider" in the side panel.
(cd web && npm run dev)   # dev server on :5173 with the same proxy; `npm run build` = tsc + vite build
curl -s localhost:8002/sim/clock; curl -s -XPOST localhost:8002/sim/clock -H 'content-type: application/json' -d '{"paused": false, "rate": 3600}'
# Routing (M3): proposals; Accept from the map, or by hand:
docker exec oceanclean-postgis-1 psql -U ocean -d oceanclean -c "select route_id, status, reason, planned_at, round(compute_ms) from routes order by 1"
curl -s -XPOST localhost:8002/routes/<N>/accept   # or /reject; accept supersedes the active route in one transaction
# HITL + faults (M5): autopilot on/off (default AUTOPILOT), a 6 sim-h fuel leak; admin data behind the Metrics/Analytics tabs (http://localhost:8080/#metrics).
curl -s -XPOST localhost:8002/hitl -H 'content-type: application/json' -d '{"autopilot": false}'
curl -s -XPOST localhost:8002/sim/fault -H 'content-type: application/json' -d '{"hours": 6}'
curl -s 'localhost:8002/metrics?minutes=15&hours=48'; curl -s localhost:8002/analytics
infra/reset_sim.sh   # clean sim start: new clock + world, empty live/M5 tables, windows checkpoint and telemetry lake history; keeps currents/hotspots
# Backfill (M6): the previous mission's 30 days at 1 Hz (2.59M events) burst through ingestion -> Kafka -> bronze (ADR-0009).
# Run once per reset, after the live run is an hour of sim time past SIM_START (it refuses earlier); then refresh analytics.
# A rerun with the same span and tick is harmless (same seqs, silver dedups); a different span or tick needs a reset first.
docker compose -f infra/docker-compose.yml --profile batch run --rm --build backfill   # ~3.5 min; watch the Metrics tab
docker compose -f infra/docker-compose.yml --profile batch run --rm backfill python simulator/sim_main.py --fast-forward 30d --tick 60   # fallback: ~43k events
```

The simulator and spark-stream wait for the batch layer's gold exports (`mission_currents.npz`, `hotspots.json`); run the batch profile once on a fresh volume. Python services bake their code into `oceanclean-py`, so `up -d --build` after editing them; spark-stream mounts its code, so `restart spark-stream` is enough.

The fetch reuses cached closed months, so only the open month needs the network; a full 25-month download takes about 25 minutes. Without network it falls back to `data/cache` and records `source=cache`. Schema changes to `infra/postgres/init.sql` reach a running DB only by re-applying it (it is idempotent): `docker exec -i oceanclean-postgis-1 psql -U ocean -d oceanclean < infra/postgres/init.sql`.

The host has no `python3-venv`; run Python tooling in the `oceanclean-py` image. Python services include the API (`api/`), so rebuild it the same way; `web` is its own image (`up -d --build web`). Ports: web 8080, API 8002, ingestion 8001, PostGIS 5433, MinIO 9000/9001, Kafka 29092 (host), Spark UI 4040 (stream), 4041 (currents ETL), 4042 (telemetry ETL).

## Conventions

- Telemetry schema is a contract: JSON with debris density, lat/lon, speed, fuel/battery, heading, strict ISO-8601 UTC event timestamp. Change it in one shared place and update producers, Spark schema, and PostGIS together.
- Use event time, never processing time, for windows and joins.
- Geometry in PostGIS uses SRID 4326; document any deviation in an ADR.
- Config and secrets via env vars; commit `.env.example`, never `.env`. Large data (`*.nc`, `*.parquet`) is gitignored.
- Everything must run locally via Docker Compose with no cloud account.
- Tests with `/tdd`: favor pure-function tests (drift advection, intercept math, threshold gate) and Spark tests on small local fixtures. Don't mock Kafka or Postgres when a Compose container works.
- Python: type hints on every function, including return types and test parameters. `ruff`. Frontend: TypeScript strict.

### Streaming and data rules (from the M1 review)

- Never put a watermark-based operator (`dropDuplicatesWithinWatermark`, windowed aggregations) upstream of the lake or live-state sinks: Spark silently drops rows older than the watermark. Offline-buffer flushes and the `--fast-forward` backfill are late by design. History dedup happens in the batch silver job on `(vessel_id, seq)`; live state relies on the guarded UPSERT (`WHERE stored.event_ts < new.event_ts`).
- Watermarks and windows are in **sim time**. At `SIM_RATE=60`, 10 sim-minutes is 10 real seconds; size them with that in mind.
- Never set `failOnDataLoss=false`; data loss must fail loudly.
- Producers must confirm delivery: register a delivery callback and check `flush()`'s return value. Return 2xx only for events the broker acknowledged; otherwise 503.
- Timestamps are timezone-aware UTC end to end. Set `TZ=UTC` on every container and convert Spark `collect()` results explicitly; never rely on container defaults.
- No credential or connection literals in code or Compose. Build DSNs from `POSTGRES_*`/`MINIO_*` env vars (`oceanclean_common.settings.pg_dsn`), and give each setting exactly one default, in `.env.example`. Read settings with `os.environ[...]`, never `.get(name, default)`, and read them inside `main()`/lifespan rather than at import, so tests can import the module. `tests/test_settings.py` checks the first two rules.
- Contract changes need a test that checks names **and types** across pydantic, `SPARK_DDL` and `infra/postgres/init.sql`, plus one test that parses producer JSON with `from_json(SPARK_DDL)`.
- Producers must keep `seq` and the sim clock monotonic across restarts (persist edge state); otherwise dedup drops and the UPSERT guard rejects the new events.

### Pitfalls (learned the hard way; don't repeat)

- PySpark is **3.5**: check an API exists in 3.5 before using it. `StructType.fromDDL` is 4.0-only; pass the DDL string to `from_json`.
- Containers run as non-root (Spark is uid 1001). Create every directory a volume mounts onto in the Dockerfile with the right owner; a named volume copies ownership only on first creation.
- In Dockerfiles, never `chmod`/`chown` files that come from a base layer: Docker copies them all into a new layer. That once added 900 MB to the Spark image. Touch only files you added.
- Disk is tight (about 10 GB free). Run `docker system df` after builds; prune build cache and dangling images, not tagged base images.
- Run tool containers with `-u "$(id -u)" -e HOME=/tmp`; running as root leaves root-owned caches in the repo.
- Wait on async pipelines with a Monitor until-loop that also exits on the first error in the logs, not with fixed sleeps.
- Update ticket status and CLAUDE.md in the **same commit** as the code they describe, not ahead of it.
- Spark tests must run through bitnami's entrypoint (no `--entrypoint python`): under an arbitrary uid it adds the passwd entry Hadoop's login needs, and without it any filesystem write (checkpoints, Parquet) fails. Streaming tests use a text-file source and memory sink under `tmp_path`.
- Don't `pkill -f <pattern>` in a Bash call: it matches the calling shell's own command line and kills it. Stop the Vite dev server with `fuser -k 5173/tcp`.
- Web formatting is Prettier with `--single-quote --no-semi --print-width 100` (no config file); lint is `npm run lint` (oxlint). Headless screenshots: `google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1600,990 --virtual-time-budget=6000 --screenshot=<file> <url>` (about 900 px of app height).
- `ruff check --fix` deletes imports it thinks are unused, including ones another module imports from this one. Import names from the module that defines them.

## Agent skills

Intended flow: `/grill-with-docs` -> `/to-spec` -> `/to-tickets` -> `/implement` (drives `/tdd`, closes with `/code-review`). Hard bugs: `/diagnosing-bugs`. Unsure which skill: `/ask-matt`.

Per-ticket loop: `/clear` → "implement `.scratch/oceanclean-mvp/issues/NN-*.md`" → `/tdd` for pure logic, run the stack for glue → `/code-review` since the ticket's starting commit → set `Status: done` + a comment → commit.

Installed globally: `grill-me` (broken: it calls a `grilling` skill that isn't installed; run the interview directly), `tdd`, `code-review`, `diagnosing-bugs`, `handoff`, `pr`, `research`, `teach`, `ask-matt`. NOT installed: `grill-with-docs`, `to-spec`, `to-tickets`, `implement`, `triage`, `wayfinder`. Until they are, use `/grill-me` to sharpen, write spec/tickets by hand under `.scratch/`, and build with `/tdd`.

### Delegating to Gemini CLI

Claude plans, designs, reviews, and writes the hard logic. Light, well-specified work (Compose/config boilerplate, simple React components, scaffolding, docs) may go to Gemini Flash:

```
eval "$(sed -n '126p' ~/.bashrc)"   # loads GEMINI_API_KEY; the shell used by agents does not read .bashrc
gemini -p "<self-contained task or path to a .scratch ticket>"   # default model; do NOT pass -m
```

- Do not pass `-m gemini-3.8-flash`: it hangs. The default model works.
- `gemini-3.1-pro-preview` returns 429 (free-tier key, quota 0); don't use it unless the key gets billing.
- Always review Gemini's diff before committing. One agent edits a given file at a time.
- Never print or commit the API key.

### Issue tracker

Local markdown under `.scratch/<feature>/` (spec.md, issues/NN-slug.md). No remote. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily as terms and decisions get resolved. See `docs/agents/domain.md`.
