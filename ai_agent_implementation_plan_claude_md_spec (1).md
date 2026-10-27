# CLAUDE.md — Frontend & Real-Time WebGL Visualization Extension Plan

> **Agent Directive:** Phases 1 through 5 (Core Cloud Infrastructure, PostgreSQL/Drizzle Schema, 3-Tier Telemetry & Bayesian Fusion API, Open-Meteo Lagrangian Drift Service, PySpark Big Data Pipeline, and Google OR-Tools Route Optimizer) are **ALREADY IMPLEMENTED**.
>
> **Your Mission:** Execute **Phases 6 through 10** below to extend the existing backend with real-time UI streaming bridges and build the interactive **WebGL Maritime Command Center & Vessel Bridge Helm (`web/`)**. Follow the **Explore $\rightarrow$ Plan $\rightarrow$ Implement $\rightarrow$ Verify** loop for each phase. Do not break existing backend unit or E2E tests.

---

## 1. Baseline Architecture Audit (Already Implemented in Phases 1–5)

Before writing code, inspect the existing repository to confirm the completed baseline:
* **`compose.yaml`:** Running `postgres`, `kafka` (KRaft), `minio` (Parquet Data Lake), `spark-master`, `spark-worker`, `api` (NestJS on `:3000`), and `ml-spark` (FastAPI + PySpark on `:8000`).
* **`api/` (NestJS + Drizzle ORM):**
  * Tables: `users`, `vessels`, `debris_patches`, `telemetry_events`, `interception_routes`.
  * Modules: `auth`, `telemetry` (Bayesian confidence fusion + H3 indexing + Kafka producer), `debris-patches`, `vessels`, `trajectories`.
* **`ml-spark/` (Python FastAPI + PySpark + OR-Tools):**
  * Open-Meteo Marine API integration (`https://marine-api.open-meteo.com/v1/marine`).
  * Lagrangian drift prediction (`POST /api/v1/ml/predict-drift`).
  * PySpark Structured Streaming & MLlib `BisectingKMeans` seasonal hotspot clustering (`GET /api/v1/ml/analytics/hotspots`).
  * Google OR-Tools current-assisted CVRPTW solver (`POST /api/v1/ml/optimize-routes`).

---

## 2. Extension Guardrails & Frontend Tech Stack

### Strict Rules for the Extension
* **DO NOT Rewrite Existing Backend Domain Logic:** Only add additive endpoints, CORS configuration, and Server-Sent Events (SSE) emitters in `api/` and `ml-spark/` as specified in Phase 6.
* **DO NOT Use Paid Map Tokens:** Never use Mapbox GL v2/v3 with a paid wall. Use **MapLibre GL JS** (`maplibre-gl` + `react-map-gl/maplibre`) with free **CARTO Dark Matter** base tiles and **OpenSeaMap** nautical overlays, paired with **Uber `deck.gl`** WebGL layers.
* **Frontend Stack (`web/`):**
  * **Core:** React 19, TypeScript 5.6+, Vite 6, Tailwind CSS v3.4+.
  * **Geospatial & WebGL:** `maplibre-gl`, `react-map-gl`, `@deck.gl/core`, `@deck.gl/react`, `@deck.gl/layers`, `@deck.gl/geo-layers` (`H3HexagonLayer`, `TripsLayer`), `h3-js`.
  * **State, Charts & Icons:** `@tanstack/react-query` v5, `recharts`, `lucide-react`, `clsx`, `tailwind-merge`.

---

## 3. UI/UX Design Specification: "Abyssal Mission Control"

The frontend must look and feel like a high-stakes maritime autonomous fleet operations center (inspired by SpaceX Starlink Maritime, Palantir Foundry, and The Ocean Cleanup):

### Color & Surface Tokens
* **Canvas Background:** Deep Abyssal Slate (`#040914`) with full-viewport 3D WebGL map occupancy (`100vw x 100vh`) and floating glassmorphic HUD panels (`bg-slate-950/80 backdrop-blur-xl border border-cyan-500/20 shadow-2xl`).
* **Semantic Telemetry Palette:**
  * **Bioluminescent Cyan (`#00F0FF`):** Live ocean current flow particles, active cleanup vessel markers, and SSE heartbeat indicators.
  * **Radar Amber (`#F59E0B`):** Tier 1 `SATELLITE_SAR` unverified anomalies (`confidenceScore` $< 0.80$, rendered as pulsing translucent H3 hexagons).
  * **Coral Crimson (`#EF4444`):** Tier 2/3 `CONFIRMED_PATCH` high-density polymer targets (`confidenceScore` $\ge 0.80$, rendered as 3D extruded H3 hexagons scaled by `polymerDensityKgKm2`).
  * **Harvester Emerald (`#10B981`):** Active Google OR-Tools vessel interception trajectories, positive current-alignment fuel bonuses, and `CLEARED` patches.
  * **Storm Violet (`#A855F7`):** High-wave storm hazard zones ($H_{\text{wave}} > 4.0\text{ m}$) and PySpark MLlib seasonal convergence cluster hulls.
* **Typography:**
  * **UI & Headers:** `Inter` or `Plus Jakarta Sans` (semi-bold tracking-tight).
  * **Telemetry, Coordinates & Logs:** `JetBrains Mono` (`tabular-nums`) for all $(\text{lat}, \text{lon})$ coordinates, H3 indices (`872830828ffffff`), knots, tonnage, and SSE log lines.

---

## 4. Target Directory Tree for the Extension

```text
marine-iot-cloud-optimizer/
├── api/
│   └── src/
│       ├── infrastructure/sse/
│       │   └── sse-stream.service.ts        # [NEW - Phase 6] Real-time event bus for UI terminal & map
│       └── modules/telemetry/
│           └── simulation.controller.ts     # [NEW - Phase 6] 1-click "Space-to-Sea" scenario generator
├── ml-spark/
│   └── src/clients/
│       └── currents_grid.py                 # [NEW - Phase 6] Bounding-box vector field endpoint for WebGL particles
└── web/                                     # [NEW - Phases 7–10] Interactive WebGL Frontend
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── index.css
        ├── types/
        │   └── marine.ts                    # Shared contracts for Patches, Vessels, Routes, Currents, Spark Clusters
        ├── lib/
        │   ├── api-client.ts                # Fetch wrapper with JWT + Demo Role Switcher support
        │   ├── use-sse-telemetry.ts         # React hook subscribing to GET /api/v1/telemetry/stream
        │   └── drift-interpolator.ts        # Math helper interpolating patch & vessel coords from T+0h to T+24h
        ├── components/
        │   ├── layout/
        │   │   ├── top-telemetry-ribbon.tsx # Live KPI counters + Instant Role Switcher (Commander vs. Captain)
        │   │   └── layer-toggle-dock.tsx    # Floating map layer switches (H3, Currents, Drift Cones, Spark Gyres)
        │   ├── map/
        │   │   ├── ocean-digital-twin.tsx   # Master MapLibre + deck.gl 3D viewport + HTML5 current particle canvas
        │   │   ├── h3-debris-layer.ts       # Extruded H3HexagonLayer with hover telemetry card
        │   │   ├── drift-cone-layer.ts      # 6h/12h/24h Lagrangian trajectory cones & uncertainty rings
        │   │   ├── vessel-routes-layer.ts   # OR-Tools interception arcs, vessel icons & heading vectors
        │   │   └── spark-hotspots-layer.ts  # Polygon/Scatter layer for Spark MLlib seasonal convergence zones
        │   ├── command-center/
        │   │   ├── simulation-console.tsx   # Interactive 5-step "Space-to-Sea" & Storm Chaos trigger panel
        │   │   ├── time-scrubber-bar.tsx    # T+0h to T+24h playback slider with 1x/5x/10x speed controls
        │   │   ├── spark-analytics-modal.tsx# Recharts visualizations of Parquet Data Lake & MLlib clusters
        │   │   └── live-cloud-terminal.tsx  # Collapsible SSE log stream (Kafka -> Spark -> Bayesian -> OR-Tools)
        │   └── vessel-helm/
        │       ├── captain-bridge-view.tsx  # Dedicated tactical helm for a selected cleanup vessel
        │       ├── current-assist-dial.tsx  # Compass showing vessel heading vs. ocean current vector & fuel saved
        │       └── waypoint-queue-card.tsx  # Ordered H3 interception manifest with [Harvest & Clear] action
        └── App.tsx
```

---

## 5. Phased Implementation Plan (Continuing from Phase 5)

---

### Phase 6: Backend Delta Upgrades for Real-Time UI & Simulation (`api/` & `ml-spark/`)

#### Goal
Extend the existing NestJS and FastAPI backends with live Server-Sent Events (SSE), a vector grid endpoint for ocean current particle rendering, and one-click simulation scenario triggers so the frontend can drive the entire cloud pipeline interactively.

#### Tasks
1. **Enable CORS & Swagger Exposure (`api/src/main.ts`):**
   * Enable CORS for `http://localhost:5173`, `http://localhost:8080`, and `*` in development so the browser can connect to REST and SSE endpoints.
2. **Real-Time SSE Telemetry Streamer (`api/src/infrastructure/sse/sse-stream.service.ts`):**
   * Create a global injectable `SseStreamService` using RxJS `Subject<MessageEvent>`.
   * Expose `@Sse('api/v1/telemetry/stream')` in `TelemetryController`.
   * Emit structured JSON events with `{ timestamp, stage: 'KAFKA_INGEST' | 'BAYESIAN_FUSION' | 'OPEN_METEO_DRIFT' | 'SPARK_BATCH' | 'ORTOOLS_ROUTE', level: 'INFO' | 'WARN' | 'SUCCESS', message, payload }` whenever:
     * A telemetry ping or batch sync is ingested.
     * A debris patch upgrades from `UNVERIFIED_ANOMALY` to `CONFIRMED_PATCH`.
     * Drift recalculation or OR-Tools route optimization completes.
3. **Interactive Cloud Scenario Simulator (`POST /api/v1/telemetry/simulate-scenario`):**
   * Add an endpoint in `api/src/modules/telemetry/` accepting `{ scenario: 'SATELLITE_SAR_SWEEP' | 'UAV_RECON_VERIFICATION' | 'EDGE_BURST_SYNC' | 'INJECT_STORM_CELL' | 'RESET_GYRE_DEMO', centerLat?: number, centerLon?: number }`:
     * **`SATELLITE_SAR_SWEEP`:** Generates 12 `SATELLITE_SAR` pings across the North Pacific Gyre ($30^\circ\text{N}-35^\circ\text{N}, 140^\circ\text{W}-148^\circ\text{W}$) with prior confidence $0.55$, persists them as `UNVERIFIED_ANOMALY` H3 patches, publishes to Kafka, and streams SSE logs.
     * **`UAV_RECON_VERIFICATION`:** Targets existing `UNVERIFIED_ANOMALY` H3 cells, injects `AERIAL_UAV` telemetry ($w = 0.85$), runs the existing Bayesian log-odds updater:
       $$P_{\text{new}} = \frac{P_{\text{prior}} \cdot w}{P_{\text{prior}} \cdot w + (1 - P_{\text{prior}})(1 - w)}$$
       promoting cells with $P_{\text{new}} \ge 0.80$ to `CONFIRMED_PATCH`, and triggers `/api/v1/ml/predict-drift` to populate `driftTrajectoryJson`.
     * **`EDGE_BURST_SYNC`:** Simulates a commercial scout vessel reconnecting after a 6-hour satellite blackout and burst-uploading 35 buffered optical/buoy telemetry packets in a single batch.
     * **`INJECT_STORM_CELL`:** Sets `seaStateWaveM` $= 5.8\text{ m}$ and amplifies current velocity within a $150\text{ km}$ radius of `(centerLat, centerLon)`, then automatically triggers OR-Tools route re-optimization so vessels visibly reroute around the storm.
4. **Ocean Current Vector Field Grid (`GET /api/v1/ml/currents-grid` in `ml-spark/`):**
   * Add a FastAPI endpoint (and proxy it at `GET /api/v1/trajectories/currents-grid` in NestJS) that returns a grid of ocean current vectors across the active gyre bounding box (`lat`, `lon`, `u_ms`, `v_ms`, `velocity_ms`, `direction_deg`, `wave_height_m`), backed by the cached Open-Meteo Marine API client.
5. **Startup Demo Seeder Check (`api/src/infrastructure/database/seed.ts`):**
   * Ensure running `npm run db:seed` populates 4 vessels (*RV Ocean Interceptor*, *ASV Pacific Vanguard*, *RV Gyre Harvester*, *ASV Albatross*), 20 initial debris patches (mix of `UNVERIFIED_ANOMALY` and `CONFIRMED_PATCH` with `6h/12h/24h` drift trajectories), and 2 active `interception_routes` so the UI loads into a rich, active ocean state immediately.

#### Verification Gate (Phase 6)
```bash
cd api && npm test && npm run build
cd ../ml-spark && pytest -v
```
*Success Criteria:* Existing backend tests continue to pass, `GET /api/v1/trajectories/currents-grid` returns valid vector arrays, and `POST /api/v1/telemetry/simulate-scenario` returns `201 Created` and emits SSE messages.

---

### Phase 7: Frontend Scaffold, API Client & Tactical HUD Layout (`web/`)

#### Goal
Initialize the `web/` application, configure the "Abyssal Mission Control" dark theme, connect TanStack Query + the live SSE hook to the NestJS backend, and build the top-level navigation and KPI ribbon.

#### Tasks
1. **Initialize `web/` Project:**
   * Create `web/package.json`, `vite.config.ts` (configuring `/api` proxy to `http://localhost:3000`), `tailwind.config.js`, and `tsconfig.json`.
   * Install dependencies: `react`, `react-dom`, `@tanstack/react-query`, `maplibre-gl`, `react-map-gl`, `@deck.gl/core`, `@deck.gl/react`, `@deck.gl/layers`, `@deck.gl/geo-layers`, `h3-js`, `recharts`, `lucide-react`, `clsx`, `tailwind-merge`.
2. **Type Contracts & API Client (`web/src/types/marine.ts` & `web/src/lib/api-client.ts`):**
   * Define strict TypeScript interfaces matching the backend Drizzle schemas (`Vessel`, `DebrisPatch`, `DriftWaypoint`, `InterceptionRoute`, `CurrentGridPoint`, `SparkHotspotCluster`, `SsePipelineEvent`).
   * Build `apiClient` with automatic JWT attachment and a graceful local-state fallback if a container is restarting.
3. **Top Telemetry KPI Ribbon & Instant Role Switcher (`web/src/components/layout/top-telemetry-ribbon.tsx`):**
   * Display live animated counters:
     * **Tracked H3 Cells:** Total patches split by `CONFIRMED_PATCH` (Crimson badge) vs. `UNVERIFIED_ANOMALY` (Amber badge).
     * **Floating Polymer Mass:** Total estimated metric tons ($\text{t}$) across the gyre.
     * **Current-Assist Fuel Savings:** Total liters of marine diesel saved (`fuelSavedByCurrentsLiters`) and efficiency boost $\%$.
     * **Cloud Pipeline Status:** Live green pulse indicator showing SSE connection state and Kafka events/sec.
   * **Instant Role Switcher Toggle:** Allow one-click switching between **[Fleet Commander HUD]** (global gyre view + simulation + Spark analytics) and **[Vessel Captain Bridge]** (ship-locked helm view) without login friction.

#### Verification Gate (Phase 7)
```bash
cd web && npm install
npx tsc --noEmit
```
*Success Criteria:* Zero TypeScript errors and clean dependency installation.

---

### Phase 8: 3D WebGL Ocean Digital Twin (`MapLibre GL` + `deck.gl` + `H3`)

#### Goal
Build the multi-layer 3D WebGL ocean map in `web/src/components/map/` that visualizes H3 plastic density hexagons, animated ocean current particles, Lagrangian drift cones, Spark MLlib hotspot hulls, and Google OR-Tools vessel interception routes.

#### Tasks
1. **Base Map & Camera Controller (`ocean-digital-twin.tsx`):**
   * Configure `MapLibre` with `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` centered on the North Pacific Subtropical Gyre (`latitude: 32.5, longitude: -144.5, zoom: 5.4, pitch: 42, bearing: -10`).
   * Add smooth `flyTo` camera transitions when a user clicks a vessel, a debris patch, or a Spark hotspot cluster.
2. **Layer 1 — 3D Extruded H3 Debris Hexagons (`h3-debris-layer.ts`):**
   * Use `@deck.gl/geo-layers` `H3HexagonLayer`:
     * `getHexagon: d => d.h3Index`
     * `extruded: true`, `elevationScale: 30`
     * `getElevation: d => d.polymerDensityKgKm2`
     * `getFillColor`: Amber `[245, 158, 11, 160]` for `UNVERIFIED_ANOMALY` ($< 0.80$ confidence); Crimson `[239, 68, 68, 220]` for `CONFIRMED_PATCH`; Cyan-Emerald `[16, 185, 129, 200]` for `INTERCEPT_ASSIGNED`.
3. **Layer 2 — Animated Ocean Current Particle Overlay (`ocean-digital-twin.tsx`):**
   * Render a synchronized HTML5 `<canvas>` / WebGL particle system overlaid on the map projection that spawns $1,200+$ bioluminescent cyan streamlines moving according to the $(u, v)$ velocity vectors from `/api/v1/trajectories/currents-grid`.
   * Color particles violet-red in high-wave storm sectors ($H_{\text{wave}} > 4.0\text{ m}$).
4. **Layer 3 — Lagrangian Drift Cones & Uncertainty Rings (`drift-cone-layer.ts`):**
   * For selected or all confirmed patches, render:
     * Dashed cyan-amber trajectory paths (`PathLayer`) connecting $T+0\text{h} \rightarrow T+6\text{h} \rightarrow T+12\text{h} \rightarrow T+24\text{h}$.
     * Expanding translucent uncertainty rings (`ScatterplotLayer`) at $6\text{h}$ ($5\text{ km}$ radius), $12\text{h}$ ($12\text{ km}$ radius), and $24\text{h}$ ($25\text{ km}$ radius).
     * Ghost H3 hexagon outlines (`H3HexagonLayer` with `wireframe: true, filled: false`) at the predicted $T+12\text{h}$ and $T+24\text{h}$ cells.
5. **Layer 4 — OR-Tools Vessel Interception Routes (`vessel-routes-layer.ts`):**
   * Render glowing emerald paths (`PathLayer` + directional waypoint markers) connecting each vessel's current position to the **predicted drifted coordinates** of its assigned H3 patches.
   * Render custom vessel markers with heading cones, callsign labels, and live load bars.
6. **Layer 5 — PySpark MLlib Seasonal Hotspot Polygons (`spark-hotspots-layer.ts`):**
   * Render translucent violet polygons/circles representing the macro-convergence zones returned by `/api/v1/trajectories/analytics/hotspots`.
7. **Interactive Tactical Tooltip & Layer Toggle Dock (`layer-toggle-dock.tsx`):**
   * Clicking or hovering any H3 cell or vessel displays a rich telemetry card (H3 index, Bayesian confidence $\%$, mass in $\text{kg}$, current speed $\text{m/s}$ & direction $\theta^\circ$, wave height $H_{\text{wave}}$, and sensor tier history).
   * Floating dock allowing users to toggle individual layers (3D H3 Hexagons, Current Particles, Drift Cones, OR-Tools Routes, Spark MLlib Gyres, Storm Cells) and 2D/3D pitch.

#### Verification Gate (Phase 8)
```bash
cd web && npx tsc --noEmit && npm run build
```
*Success Criteria:* All `deck.gl` and `maplibre-gl` layers compile cleanly with zero TypeScript or bundler errors.

---

### Phase 9: Interactive Simulation Console, 24h Time-Scrubber & Big Data Drawer (`web/`)

#### Goal
Build the interactive controls that let users trigger cloud workflows, scrub forward in time from $T+0\text{h}$ to $T+24\text{h}$ to watch patches drift and ships intercept them, and inspect live Kafka/Spark/OR-Tools telemetry.

#### Tasks
1. **"Space-to-Sea" Interactive Simulation Console (`web/src/components/command-center/simulation-console.tsx`):**
   * Left-docked glassmorphic drawer with 5 sequential interactive mission buttons:
     * **[Step 1: Satellite SAR Pass]** $\rightarrow$ Calls `simulate-scenario` (`SATELLITE_SAR_SWEEP`), animates a radar sweep across the map, and spawns amber unverified H3 hexagons.
     * **[Step 2: Launch UAV Recon]** $\rightarrow$ Calls `simulate-scenario` (`UAV_RECON_VERIFICATION`), updates Bayesian confidence scores, and animates confirmed hexagons turning crimson and extruding in 3D.
     * **[Step 3: Edge Burst Sync]** $\rightarrow$ Simulates disconnected commercial scout ship uploading 35 buffered telemetry packets into Kafka.
     * **[Step 4: Inject Storm Cell]** $\rightarrow$ Lets user spawn a $5.8\text{ m}$ wave storm cell in the gyre, coloring local currents violet and flagging hazard cells.
     * **[Step 5: Run OR-Tools Fleet Optimizer]** $\rightarrow$ Calls `POST /api/v1/trajectories/generate`, computes current-assisted moving-target routes, and draws glowing emerald interception trajectories on the map.
2. **Interactive 24-Hour Time-Scrubber & Drift Playback Bar (`time-scrubber-bar.tsx` & `drift-interpolator.ts`):**
   * Bottom-centered floating timeline control with:
     * Play / Pause button, Reset (`T+0h`), and Speed selector ($1\times, 5\times, 10\times$).
     * Continuous slider from `t = 0.0` hours to `t = 24.0` hours.
   * **Interpolation Math (`drift-interpolator.ts`):**
     * For any slider value $t \in [0, 24]$, linearly interpolate each debris patch's $(\text{lat}(t), \text{lon}(t))$ and corresponding H3 index between its $0\text{h}, 6\text{h}, 12\text{h}, \text{and } 24\text{h}$ Lagrangian drift waypoints.
     * Simultaneously interpolate each cleanup vessel's position along its assigned OR-Tools route polyline according to `cruiseSpeedKnots` and current alignment so the user visually sees the vessel and the drifting patch converge at the exact same coordinate and timestamp.
3. **Live Cloud & Big Data Telemetry Inspector (`live-cloud-terminal.tsx` & `spark-analytics-modal.tsx`):**
   * **Live Cloud Terminal:** Collapsible bottom console streaming real-time SSE events from `/api/v1/telemetry/stream` with filter pills (`ALL`, `KAFKA`, `BAYESIAN`, `OPEN-METEO`, `SPARK`, `OR-TOOLS`).
   * **PySpark Big Data Analytics Drawer:** Displays `Recharts` visualizations of the Parquet Data Lake (`BisectingKMeans` seasonal hotspot tonnage distribution, sensor tier breakdown, and current-assist fuel savings per vessel) plus a **[Trigger PySpark Batch Job]** button.

#### Verification Gate (Phase 9)
```bash
cd web && npx tsc --noEmit && npm run build
```
*Success Criteria:* Time-scrubber interpolation helper and all Command Center drawers compile cleanly and update React state without frame drops.

---

### Phase 10: Vessel Captain Bridge Helm & Full-Stack Docker Integration

#### Goal
Build the dedicated **Vessel Captain Bridge Helm** view, add the `web` container to `compose.yaml`, and verify the complete 7-container system end-to-end.

#### Tasks
1. **Vessel Captain Bridge Helm (`web/src/components/vessel-helm/`):**
   * When switched to **Vessel Captain Mode** (or when clicking **[Open Bridge Helm]** on any ship):
     * **Vessel Selector & Status Header (`captain-bridge-view.tsx`):** Select between active cleanup ships (*RV Ocean Interceptor*, *ASV Pacific Vanguard*, etc.), showing callsign, fuel level $\%$, storage bay tonnage bar (`currentLoadTons / maxCapacityTons`), and sea-state hazard badge.
     * **Current-Assist Navigation Dial (`current-assist-dial.tsx`):** Visual compass comparing vessel heading vector $\hat{u}$ against local Open-Meteo ocean current vector $\vec{v}_c$, displaying the live dot-product alignment bonus (e.g., `+18.4% Fuel Efficiency — Riding Kuroshio Extension Current`).
     * **Interception Waypoint Manifest (`waypoint-queue-card.tsx`):** Ordered queue of assigned H3 debris patches showing ETA, drifted interception coordinates, expected plastic yield ($\text{kg}$), and a **[Harvest & Mark Cleared]** button that calls `PATCH /api/v1/trajectories/:id/waypoints/:h3Index/complete`, increments the ship's onboard storage tonnage, and turns the H3 hexagon emerald on the map.
2. **Containerize `web/` & Update `compose.yaml`:**
   * Create `web/Dockerfile` (multi-stage Node 22 build $\rightarrow$ `nginx:alpine` serving static assets) and `web/nginx.conf` (proxying `/api/` with SSE buffering disabled `proxy_buffering off;` to `http://api:3000/api/`).
   * Add the `web` service to the root `compose.yaml` exposed on port `5173:80` (or `8080:80`) depending on `api`.

#### Verification Gate (Phase 10 — Final Full-Stack Sign-Off)
```bash
# 1. Verify frontend typecheck and production bundle
cd web && npm run build

# 2. Bring up the complete stack including the new web container
cd .. && docker compose up -d --build

# 3. Verify endpoints and UI availability
curl -f http://localhost:3000/api/v1/debris-patches
curl -f http://localhost:5173
```
*Success Criteria:*
1. `docker compose ps` shows `postgres`, `kafka`, `minio`, `spark-master`, `api`, `ml-spark`, and `web` running and healthy.
2. Opening `http://localhost:5173` loads the **3D WebGL Maritime Command Center** with live H3 hexagons, flowing ocean current particles, interactive simulation buttons, a working 24-hour drift time-scrubber, live SSE terminal logs, and the Vessel Captain Bridge Helm.