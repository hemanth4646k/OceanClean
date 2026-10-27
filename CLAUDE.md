# CLAUDE.md — Marine IoT Telemetry, Big Data & Dynamic Trajectory Optimizer

> **Agent Directive:** Read this specification completely before writing any code. Follow the **Explore $\rightarrow$ Plan $\rightarrow$ Implement $\rightarrow$ Verify** loop for every phase. Do not proceed to Phase $N+1$ until all verification checks in Phase $N$ pass with zero errors.

---

## 1. System Overview & Architectural Boundaries

This system is a **backend-only, cloud-native distributed architecture** for autonomous and crewed ocean plastic cleanup operations. It ingests multi-tier marine IoT telemetry (Satellites, Aerial UAVs, Commercial Scout Ships, and Drifting Buoys), processes high-velocity streams and historical oceanographic datasets using **Apache Kafka** and **Apache Spark**, predicts plastic debris drift using open-source Lagrangian physics models and live marine weather APIs, and calculates fuel-optimal vessel interception routes.

### Strict Scope & Anti-Goal Guardrails (CRITICAL)
* **NO Frontend / UI:** Do not generate React, Vue, HTML, or CSS files. This repository is strictly a headless Cloud API, Big Data pipeline, and ML Optimization backend.
* **DO NOT Reinvent Ocean Current Forecasting:** Never write custom ML models or neural networks to predict ocean currents or waves. Always fetch live/forecasted marine current vectors from the free **Open-Meteo Marine API** (`https://marine-api.open-meteo.com/v1/marine`) or **NOAA ERDDAP** NetCDF datasets.
* **DO NOT Reinvent Physics or Routing Solvers:**
  * Use **`OpenDrift` (`opendrift.models.plastdrift`)** or vector advection over Open-Meteo grids for Lagrangian particle drift calculation.
  * Use **Google `OR-Tools` (`ortools`)** for Capacitated Vehicle/Vessel Routing with Time Windows (CVRPTW).
  * Use **Uber `H3` (`h3-py` / `h3-js`)** hexagonal hierarchical spatial indexing (Resolution 6 and 7) for spatial deduplication and heatmap cells—do not write raw bounding-box SQL math.

---

## 2. Permission Tiers & Agent Operating Rules

| Tier | Rule / Action | Agent Behavior |
| :--- | :--- | :--- |
| **ALWAYS** | Run single unit/integration tests, typechecks (`tsc --noEmit`, `ruff check`), Drizzle schema generation, and OpenAPI spec validation. | Execute autonomously after every file edit. |
| **ASK FIRST** | Modifying `compose.yaml` resource limits, adding unapproved third-party packages, or altering database primary keys. | Pause and request human confirmation with a diff summary. |
| **NEVER** | Building custom frontend code, writing custom TSP/VRP solvers from scratch, hardcoding secrets/credentials outside `.env.example`, or mocking core open-source libraries in production code. | Strictly prohibited. |

### Code Style & Invariants
* **TypeScript (`api/`):** Node.js 22+, NestJS 11, ES Modules (`import`/`export`), Drizzle ORM, Zod for payload validation. All timestamps MUST be UTC ISO-8601. All primary keys MUST be UUIDv4 or ULID.
* **Python (`ml-spark/`):** Python 3.11+, managed via `uv` or `pip`, FastAPI, Pydantic v2, PySpark 3.5+, Google OR-Tools, H3-Py, HTTPX. Enforce formatting and linting via `ruff`.
* **Geospatial Standard:** All coordinates follow WGS84 (`latitude` $\in [-90, 90]$, `longitude` $\in [-180, 180]$) paired with an Uber H3 index string (`h3_index` at resolution $7 \approx 5.16\text{ km}^2$ cell area).

---

## 3. Target Repository Structure

```text
marine-iot-cloud-optimizer/
├── CLAUDE.md                        # This master specification file
├── compose.yaml                     # Multi-container orchestration (Postgres, Kafka, MinIO, Spark, API, ML)
├── .env.example                     # Template environment variables
├── .github/workflows/ci.yml         # Automated lint, test, and multi-stage Docker build pipeline
├── api/                             # NestJS Cloud Gateway & State Management Microservice
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── drizzle.config.ts
│   ├── src/
│   │   ├── main.ts                  # Bootstrap, Swagger/OpenAPI at /docs, global Zod pipes
│   │   ├── app.module.ts
│   │   ├── common/                  # Guards (JWT, API Key x-sensor-key, Rate Throttling), Decorators
│   │   ├── infrastructure/
│   │   │   ├── database/            # Drizzle PostgreSQL connection, migrations, and seeders
│   │   │   └── kafka/               # Kafka producer/consumer client wrapper
│   │   └── modules/
│   │       ├── auth/                # Fleet commander & vessel operator JWT authentication
│   │       ├── telemetry/           # 3-Tier IoT ingestion (Satellite SAR, UAV, Ship/Buoy) -> Kafka
│   │       ├── debris-patches/      # H3-indexed plastic accumulation zones & Bayesian confidence state
│   │       ├── vessels/             # Cleanup ships: fuel capacity, storage tonnage, live heading
│   │       └── trajectories/        # Interception route dispatcher & Spark analytics proxy
│   └── test/                        # Jest E2E and contract tests
└── ml-spark/                        # Python FastAPI, PySpark Big Data & OR-Tools Optimization Engine
    ├── Dockerfile
    ├── requirements.txt
    ├── src/
    │   ├── main.py                  # FastAPI entrypoint (/drift, /optimize-routes, /spark-jobs)
    │   ├── clients/
    │   │   └── open_meteo.py        # Free Open-Meteo Marine API client (current velocity & direction)
    │   ├── drift/
    │   │   └── lagrangian.py        # OpenDrift / Advection physics wrapper for moving debris patches
    │   ├── optimizer/
    │   │   └── vessel_routing.py    # Google OR-Tools CVRPTW with current-assisted fuel cost matrix
    │   └── spark/
    │       ├── streaming_fusion.py  # Spark Structured Streaming: Kafka -> H3 spatial deduplication
    │       └── batch_hotspots.py    # Spark MLlib (DBSCAN) over Parquet data lake in MinIO/HDFS
    └── tests/                       # Pytest suite
```

---

## 4. Open-Source Libraries & External Free APIs Reference

Do not write custom implementations for any of the capabilities listed below:

1. **Ocean Currents & Wave Telemetry (Free, No Key Required):**
   * **Endpoint:** `GET https://marine-api.open-meteo.com/v1/marine`
   * **Query Parameters:** `latitude={lat}&longitude={lon}&current=ocean_current_velocity,ocean_current_direction,wave_height&hourly=ocean_current_velocity,ocean_current_direction`
   * **Usage:** Fetch real-time and 7-day hourly forecasted surface current speed ($\text{m/s}$ or $\text{km/h}$) and direction ($\theta \in [0^\circ, 360^\circ]$).
2. **Spatial Indexing & Sensor Deduplication:**
   * **Library:** `h3` (Python) and `h3-js` (TypeScript).
   * **Usage:** Convert raw $(\text{lat}, \text{lon})$ into resolution-7 H3 hexagons (`h3.latlng_to_cell(lat, lon, 7)`). Any two sensor hits mapping to the same H3 cell within a 60-minute window refer to the same debris patch.
3. **Lagrangian Particle Drift Advection:**
   * **Library:** `opendrift` (or `scipy.integrate.solve_ivp` over Open-Meteo vector grids for lightweight container execution).
   * **Physics Formula:** Given initial patch position $\vec{P}_0$, surface current velocity $\vec{v}_c(t)$, wind velocity $\vec{v}_w(t)$, and windage drift factor $\alpha \approx 0.02$:
     $$\vec{P}(t) = \vec{P}_0 + \int_{0}^{t} \left( \vec{v}_c(\tau) + \alpha \vec{v}_w(\tau) \right) d\tau$$
4. **Fleet Trajectory Optimization:**
   * **Library:** `ortools` (`from ortools.constraint_solver import pywrapcp, routing_enums_pb2`).
   * **Cost Function:** Define edge traversal cost $C(i, j)$ between H3 patch $i$ and patch $j$ using the Haversine distance $d_{ij}$ adjusted by the alignment between vessel heading unit vector $\hat{u}_{ij}$ and ocean current vector $\vec{v}_c$:
     $$C(i, j) = d_{ij} \cdot \left( 1 - \beta \frac{\hat{u}_{ij} \cdot \vec{v}_c}{\|\vec{v}_c\|_{\max}} \right) + \gamma \cdot H_{\text{wave}}$$
     where $\beta \in [0.1, 0.35]$ rewards sailing with the current and $\gamma \cdot H_{\text{wave}}$ penalizes high-wave storm cells.

---

## 5. Phased Implementation Plan for AI Agents

Execute these 6 phases sequentially. After completing each phase, run its **Verification Gate** commands.

---

### Phase 1: Cloud Infrastructure, Docker Compose & Database Schema

#### Goal
Scaffold the monorepo, container orchestration (`compose.yaml`), and PostgreSQL schema using Drizzle ORM in `api/`.

#### Tasks
1. Create `compose.yaml` with healthchecks for:
   * `postgres`: `postgres:16-alpine` (Port `5432`)
   * `kafka`: `apache/kafka:3.8.0` in KRaft mode (Port `9092`, no Zookeeper)
   * `minio`: `minio/minio:latest` configured as an S3/HDFS-compatible Data Lake for Parquet files (Ports `9000`, `9001`)
   * `spark-master` & `spark-worker`: `bitnami/spark:3.5`
   * `api`: NestJS service (Port `3000`)
   * `ml-spark`: Python FastAPI + PySpark driver service (Port `8000`)
2. Initialize `api/` with NestJS and Drizzle ORM. Create the following PostgreSQL tables in `api/src/infrastructure/database/schema.ts`:
   * **`users`**: `id` (UUID), `email`, `passwordHash`, `role` (`'FLEET_ADMIN' | 'VESSEL_CAPTAIN'`), `createdAt`.
   * **`vessels`**: `id` (UUID), `name`, `callsign` (unique), `operatorId` (FK to `users`), `status` (`'IDLE' | 'EN_ROUTE' | 'HARVESTING' | 'MAINTENANCE'`), `latitude`, `longitude`, `h3Index`, `maxCapacityTons`, `currentLoadTons`, `fuelLevelPct`, `cruiseSpeedKnots`, `updatedAt`.
   * **`debris_patches`**: `id` (UUID), `h3Index` (varchar, indexed), `latitude`, `longitude`, `estimatedMassKg`, `polymerDensityKgKm2`, `confidenceScore` (float $0.0 - 1.0$), `status` (`'UNVERIFIED_ANOMALY' | 'CONFIRMED_PATCH' | 'INTERCEPT_ASSIGNED' | 'CLEARED'`), `currentVelocityMs`, `currentDirectionDeg`, `predictedLat6h`, `predictedLon6h`, `lastObservedAt`.
   * **`telemetry_events`**: `id` (UUID), `sourceTier` (`'SATELLITE_SAR' | 'AERIAL_UAV' | 'VESSEL_OPTICAL' | 'DRIFT_BUOY'`), `sensorDeviceId`, `h3Index`, `latitude`, `longitude`, `detectedDensityKgKm2`, `rawConfidence`, `seaStateWaveM`, `observedAt`.
   * **`interception_routes`**: `id` (UUID), `vesselId` (FK), `status` (`'PLANNED' | 'ACTIVE' | 'COMPLETED' | 'ABORTED'`), `totalDistanceNm`, `estimatedFuelLiters`, `expectedYieldKg`, `waypointsJson` (JSONB array of ordered H3 intercepts with ETA and predicted drift coordinates), `createdAt`.

#### Verification Gate (Phase 1)
```bash
cd api && npm install
npx drizzle-kit generate
npm run build
```
*Success Criteria:* Zero TypeScript compilation errors and valid SQL migration files generated in `api/drizzle/`.

---

### Phase 2: 3-Tier IoT Telemetry Ingestion & Bayesian Sensor Fusion (`api/`)

#### Goal
Build the NestJS modules for Authentication, Vessels, Debris Patches, and the 3-Tier Telemetry Ingestion Gateway that publishes raw events to Kafka and updates PostgreSQL via Bayesian confidence fusion.

#### Tasks
1. **Security & Guards (`api/src/common/guards/`):**
   * Implement `JwtAuthGuard` and `RolesGuard` for `FLEET_ADMIN` and `VESSEL_CAPTAIN`.
   * Implement `SensorApiKeyGuard` validating the `x-sensor-key` header (using constant-time `crypto.timingSafeEqual`) for automated IoT webhooks.
2. **3-Tier Telemetry Endpoint (`POST /api/v1/telemetry/ingest` & `POST /api/v1/telemetry/batch-sync`):**
   * Validate payloads with Zod (`sourceTier`, `latitude`, `longitude`, `detectedDensityKgKm2`, `observedAt`). Support batch arrays for **Disconnected Edge Sync** (when ships reconnect to satellite internet and burst-upload buffered pings).
   * Compute `h3Index = latLngToCell(dto.latitude, dto.longitude, 7)`.
   * Publish raw telemetry messages asynchronously to the Kafka topic `marine.telemetry.raw`.
3. **Bayesian Confidence Fusion (`DebrisPatchesService`):**
   * Base sensor reliability weights:
     * `SATELLITE_SAR`: prior weight $w = 0.55$
     * `AERIAL_UAV`: weight $w = 0.85$
     * `VESSEL_OPTICAL` / `DRIFT_BUOY`: weight $w = 0.95$
   * When a new telemetry ping arrives for an existing active `h3Index`, update the patch's `confidenceScore` using log-odds Bayesian updating:
     $$P_{\text{new}} = \frac{P_{\text{prior}} \cdot w}{P_{\text{prior}} \cdot w + (1 - P_{\text{prior}})(1 - w)}$$
   * Automatically transition `debris_patches.status` from `'UNVERIFIED_ANOMALY'` to `'CONFIRMED_PATCH'` once `confidenceScore` $\ge 0.80$.

#### Verification Gate (Phase 2)
```bash
cd api && npm run test
```
*Success Criteria:* Unit tests verify that a `SATELLITE_SAR` ping creates an `UNVERIFIED_ANOMALY` ($0.55$ confidence) and a subsequent `AERIAL_UAV` ping in the same H3 cell merges with it and promotes it to `CONFIRMED_PATCH` ($\ge 0.80$ confidence).

---

### Phase 3: Open-Meteo Ocean Currents & Lagrangian Drift Service (`ml-spark/`)

#### Goal
Implement the Python FastAPI microservice that fetches real ocean current vectors from Open-Meteo and calculates where floating plastic patches will drift over the next $6$, $12$, and $24$ hours.

#### Tasks
1. **Open-Meteo Client (`ml-spark/src/clients/open_meteo.py`):**
   * Use `httpx.AsyncClient` to query `https://marine-api.open-meteo.com/v1/marine`.
   * Implement an in-memory TTL cache keyed by H3 resolution-5 cell so nearby patches reuse the same oceanographic forecast grid without hitting rate limits.
   * Provide a deterministic fallback vector calculation if the container runs in an offline CI test environment.
2. **Lagrangian Drift Engine (`ml-spark/src/drift/lagrangian.py`):**
   * Expose `POST /api/v1/ml/predict-drift` accepting a list of active debris patches (`id`, `latitude`, `longitude`, `observed_at`) and target horizon hours (`horizons = [6, 12, 24]`).
   * Convert spherical velocity components $(u, v)$ from Open-Meteo's `ocean_current_velocity` and `ocean_current_direction`:
     $$u = V_c \cdot \sin(\theta_{\text{rad}}), \quad v = V_c \cdot \cos(\theta_{\text{rad}})$$
   * Integrate forward in time across the hourly Open-Meteo forecast series using earth radius $R = 6371000\text{ m}$:
     $$\Delta \text{lat} = \frac{v \cdot \Delta t}{R} \left(\frac{180}{\pi}\right), \quad \Delta \text{lon} = \frac{u \cdot \Delta t}{R \cdot \cos(\text{lat}_{\text{rad}})} \left(\frac{180}{\pi}\right)$$
   * Return the new `predicted_lat`, `predicted_lon`, and updated `h3_index` for each requested time horizon.

#### Verification Gate (Phase 3)
```bash
cd ml-spark && pytest tests/test_drift.py -v
```
*Success Criteria:* Pytest confirms that a debris patch placed in a $1.5\text{ m/s}$ eastward current ($\theta = 90^\circ$) shifts east in longitude after $6\text{ hours}$ while latitude remains constant, and returns a valid H3 index.

---

### Phase 4: Big Data Pipeline — PySpark Streaming & Batch MLlib Analytics (`ml-spark/`)

#### Goal
Implement the Lambda Big Data architecture using **PySpark Structured Streaming** for high-velocity telemetry aggregation and **PySpark MLlib (DBSCAN / K-Means)** over Parquet archives in MinIO/HDFS for seasonal garbage patch hotspot discovery.

#### Tasks
1. **Synthetic Big Data Parquet Seeder (`ml-spark/src/spark/seed_datalake.py`):**
   * Generate $100,000+$ historical marine telemetry rows across the North Pacific Subtropical Gyre ($25^\circ\text{N}-40^\circ\text{N}$, $135^\circ\text{W}-160^\circ\text{W}$) and write them as partitioned **Apache Parquet** files (`s3a://marine-datalake/telemetry/year=2026/month=10/` or local volume mount).
2. **Speed Layer (`ml-spark/src/spark/streaming_fusion.py`):**
   * Configure a PySpark Structured Streaming job reading from Kafka topic `marine.telemetry.raw`.
   * Apply a 15-minute tumbling watermark window grouped by `h3_index`, computing average `detectedDensityKgKm2`, max `seaStateWaveM`, and event count, sinking aggregated records to PostgreSQL and Parquet.
3. **Batch Layer (`ml-spark/src/spark/batch_hotspots.py`):**
   * Load historical Parquet files into a Spark DataFrame.
   * Run distributed **Spark MLlib `BisectingKMeans`** (or spatial H3 density clustering) weighted by `polymerDensityKgKm2` to identify macro-scale plastic convergence zones ("Seasonal Gyre Hotspots").
   * Expose results via FastAPI `GET /api/v1/ml/analytics/hotspots` and proxy through NestJS `GET /api/v1/trajectories/analytics/hotspots`.

#### Verification Gate (Phase 4)
```bash
cd ml-spark && pytest tests/test_spark_analytics.py -v
```
*Success Criteria:* Pytest executes a local `SparkSession("local[2]")` over sample Parquet data and returns top convergence zone centroids with non-zero plastic tonnage estimates.

---

### Phase 5: Current-Assisted Moving-Target Route Optimizer (`ml-spark/` & `api/`)

#### Goal
Build the fleet trajectory optimizer using **Google OR-Tools** that assigns cleanup vessels to confirmed debris patches while accounting for patch drift, ocean current assistance/resistance, wave hazards, and vessel storage capacity.

#### Tasks
1. **OR-Tools Optimization Engine (`ml-spark/src/optimizer/vessel_routing.py`):**
   * Expose `POST /api/v1/ml/optimize-routes` accepting active `vessels` and `confirmed_patches`.
   * Step 1: Project each patch's coordinates forward by the estimated vessel transit time using the Phase 3 Drift Engine.
   * Step 2: Build an asymmetric distance and fuel-cost matrix $M_{ij}$ between all vessels and drifted patch coordinates:
     * Compute Haversine distance $d_{ij}$ (in nautical miles).
     * Compute bearing $\hat{u}_{ij}$ and dot-product with local ocean current vector $\vec{v}_c$.
     * Apply a $300\%$ cost penalty if `seaStateWaveM` $> 4.0\text{ m}$ (storm hazard avoidance).
   * Step 3: Configure OR-Tools `RoutingModel` with:
     * **Capacity Dimension:** Vessel `maxCapacityTons - currentLoadTons` vs. patch `estimatedMassKg`.
     * **Disjunctions:** Allow dropping low-yield patches if fleet capacity or fuel range is exceeded, prioritizing high plastic density (`polymerDensityKgKm2`).
   * Step 4: Return ordered interception waypoints, total nautical miles, estimated fuel burn (liters), and expected plastic yield (kg) for each vessel.
2. **NestJS Trajectory Orchestrator (`api/src/modules/trajectories/`):**
   * Implement `POST /api/v1/trajectories/generate` (Admin-only) which queries active vessels and `CONFIRMED_PATCH` records from PostgreSQL, calls the Python `ml-spark` microservice, persists the resulting `interception_routes`, and updates assigned patches to `INTERCEPT_ASSIGNED`.
   * Implement `PATCH /api/v1/trajectories/:id/waypoints/:h3Index/complete` for vessel captains to mark a debris patch as harvested (`CLEARED`) and increment the vessel's `currentLoadTons`.

#### Verification Gate (Phase 5)
```bash
cd ml-spark && pytest tests/test_optimizer.py -v
cd ../api && npm run test:e2e
```
*Success Criteria:*
1. `test_optimizer.py` proves that given two equidistant patches of equal mass, the OR-Tools solver selects the patch aligned *with* the ocean current at lower fuel cost.
2. `test_optimizer.py` proves that vessel capacity constraints prevent assigning $50\text{ tons}$ of debris to a vessel with $20\text{ tons}$ of remaining storage.

---

### Phase 6: Cloud Simulation Seeder, CI/CD & End-to-End Verification

#### Goal
Create a one-command simulation script and GitHub Actions workflow to verify the entire cloud pipeline end-to-end without any manual setup.

#### Tasks
1. **End-to-End Simulation Script (`scripts/simulate_ocean_mission.py`):**
   * Seeds 3 cleanup vessels and 2 fleet operator accounts via `api/`.
   * Simulates a **Tier 1 Satellite SAR Pass** (20 wide-area anomalies).
   * Simulates a **Tier 2 Aerial UAV Sweep** confirming 12 high-density patches.
   * Triggers the **Open-Meteo + Lagrangian Drift Update** worker.
   * Triggers **OR-Tools Fleet Route Optimization** and prints the complete JSON mission manifest (waypoints, fuel saved via ocean currents, total plastic yield, and Spark hotspot summaries).
2. **CI/CD Workflow (`.github/workflows/ci.yml`):**
   * Job 1: Lint & Typecheck (`api` ESLint/TSC + `ml-spark` Ruff).
   * Job 2: Unit & Integration Tests (`jest` with Postgres service container + `pytest`).
   * Job 3: Docker Compose Build & Smoke Test.

#### Verification Gate (Phase 6 — Final Sign-Off)
```bash
docker compose up -d --build
python3 scripts/simulate_ocean_mission.py
```
*Success Criteria:* All containers report `healthy`, the simulation script completes with HTTP `200/201` responses across all pipeline stages, and valid interception routes are persisted in PostgreSQL.

---

## 6. Quick Reference Commands for AI Agents

```bash
# 1. Start full cloud & big data infrastructure
docker compose up -d postgres kafka minio spark-master spark-worker

# 2. Run NestJS API migrations & unit tests
cd api && npx drizzle-kit push && npm test

# 3. Run Python ML/Spark unit tests & linter
cd ml-spark && ruff check . && pytest -v

# 4. Inspect OpenAPI / Swagger documentation
curl -s http://localhost:3000/docs-json | jq .info
```