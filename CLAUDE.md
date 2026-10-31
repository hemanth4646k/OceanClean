# OceanClean

Big Data (BDA course) prototype: a single-vessel, dynamic route optimizer for ocean plastic cleanup. Synthetic IoT telemetry + public ocean-current data (Copernicus/NOAA) flow through a Lambda architecture to a live map. Goal: maximize debris collected per unit of vessel energy by anticipating drift.

Source of truth for requirements: [software_requirements_specification.md](software_requirements_specification.md). If code and SRS disagree, surface it; don't silently pick one.
UI mood references: `demo1.jpeg` (map + current particles + control panel), `demo2.jpeg` (operator "AI Route Optimization" Accept/Override modal), `demo3.jpeg` (admin metrics dashboard). Dark maritime theme.

## Architecture (see SRS §2)

```
sim vessels ─► ingestion API ─► Kafka ─► Spark Structured Streaming ─┬─► PostGIS (UPSERT live state, routes)
 (offline buffer)  (partition: vessel_id + zone)   (watermark, checkpoint)  └─► MinIO/S3 Parquet|Iceberg (append-only ticks)
Copernicus/NOAA NetCDF/GRIB ─► PySpark batch ETL ─► u/v drift grid (Parquet, spatio-temporal partitions)
PostGIS + drift grid ─► route optimizer (threshold-gated recalc) ─► waypoints ─► PostGIS ─► REST + WebSocket ─► React UI
```

- **Speed layer**: Spark Structured Streaming, event-time watermarks for out-of-order data, checkpointing mandatory.
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
simulator/    synthetic vessel + offline-queue telemetry producers
ingestion/    ingestion endpoint -> Kafka
streaming/    Spark Structured Streaming jobs
batch/        PySpark ocean-current ETL
routing/      optimizer + recalc threshold logic
api/          REST + WebSocket server
web/          React frontend
docs/adr/     architecture decisions;  docs/agents/  skill config
.scratch/     local-markdown specs and tickets
```

## Status

Setup only, no application code yet. Done: SRS, UI mood images, this file, skill/issue-tracker config, git repo (`main`), Gemini CLI. Next: `/grill-me` on the first vertical slice (simulator -> Kafka -> Spark -> PostGIS), then spec and tickets in `.scratch/<feature>/`. First open decisions: telemetry schema, Compose service set, Spark/Java versions, Iceberg vs plain Parquet, route-optimizer algorithm.

## Environment (dev machine)

Docker 29, Node 26, Python 3.10, Java 22. `uv` and `ripgrep` not installed. Spark 3.5 does not reliably support Java 22; run Spark in a container pinned to Java 17. Command output is compressed by the global `rtk` hook; re-run as `rtk bypass <cmd>` only if a result looks wrong.

## Commands

None established yet. When you add the first working command (compose up, test, lint, run job), record the exact invocation here. Do not guess commands in the meantime.

## Conventions

- Telemetry schema is a contract: JSON with debris density, lat/lon, speed, fuel/battery, heading, strict ISO-8601 UTC event timestamp. Change it in one shared place and update producers, Spark schema, and PostGIS together.
- Use event time, never processing time, for windows and joins.
- Geometry in PostGIS uses SRID 4326; document any deviation in an ADR.
- Config and secrets via env vars; commit `.env.example`, never `.env`. Large data (`*.nc`, `*.parquet`) is gitignored.
- Everything must run locally via Docker Compose with no cloud account.
- Tests with `/tdd`: favor pure-function tests (drift advection, intercept math, threshold gate) and Spark tests on small local fixtures. Don't mock Kafka or Postgres when a Compose container works.
- Python: type hints, `ruff`. Frontend: TypeScript strict.

## Agent skills

Intended flow: `/grill-with-docs` -> `/to-spec` -> `/to-tickets` -> `/implement` (drives `/tdd`, closes with `/code-review`). Hard bugs: `/diagnosing-bugs`. Unsure which skill: `/ask-matt`.

Installed globally: `grill-me`, `tdd`, `code-review`, `diagnosing-bugs`, `handoff`, `pr`, `research`, `teach`, `ask-matt`. NOT installed: `grill-with-docs`, `to-spec`, `to-tickets`, `implement`, `triage`, `wayfinder`. Until they are, use `/grill-me` to sharpen, write spec/tickets by hand under `.scratch/`, and build with `/tdd`.

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
