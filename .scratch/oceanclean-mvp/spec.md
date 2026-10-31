# OceanClean MVP: spec

Status: approved (grilling session 2026-10-31). Demo: live demo + presentation, 2026-11-01, on the dev machine, fully offline-capable.

## Demo story (acceptance criteria for the whole MVP)

1. **There is a garbage patch.** A Spark convergence analysis over ~2 years of real NOAA surface currents shows persistent convergence hotspots in the North Pacific gyre. Validated against NOAA NCEI measured microplastics ("convergent cells have N× higher measured concentration").
2. **It drifts.** A time slider replays debris patches advected through a historical period by real daily currents, with flowing current particles underneath.
3. **Predictive dispatch.** The optimizer proposes an intercept route. The map shows each target patch now, a ghost at its predicted position at intercept time, and the dashed drift line between them. The operator Accepts, Rejects or Modifies it; with no answer in 30 s the proposal expires and the vessel keeps its current route, or loiters if it has none (SRS §5.4, ADR-0008). Autopilot (the simulation default) decides instead.
4. **Cleaned in ~1 month.** On a compressed sim clock, the single cleaner works through the patch cluster. Patches fade as they're collected; counters and a Recharts curve show debris removed vs energy used, ending around sim day 30.
5. **It is big data.** The Metrics tab shows pipeline health (events/s, Kafka lag, micro-batch duration, lake row counts). A 30-day telemetry backfill (the previous mission, logged at 1 Hz) bursts ~2.6M events through Kafka (ADR-0009). The Analytics tab reads gold aggregates.

## Scope decisions

- Single cleaner vessel (SRS §1.2). No fleet.
- Operating area: North Pacific gyre. History box 20–45°N, 180°–130°W; mission box ~30–40°N, 150–135°W.
- Lake: plain Parquet on MinIO, medallion layout (ADR-0001). No Iceberg.
- Spark 3.5.1 in one container, `local[2]`, image `bitnamilegacy/spark:3.5.1` (Java 17).
- Currents: NOAA SCUD (`scud_pac`) via ERDDAP griddap, fetch-and-cache with cache fallback (ADR-0002).
- Debris observations: NOAA NCEI Marine Microplastics ArcGIS FeatureServer, fetch-and-cache (ADR-0002).
- Simulation clock with compressed event time (ADR-0003).
- Own moving-target intercept optimizer; HALEM, windmar, ShipNetSim and LOTUSim/Plankton were evaluated and not integrated (ADR-0004). The fuel model follows the ShipNetSim approach (resistance → propulsive power → fuel), simplified.
- Auth: none; header switch for Admin / Operator role.
- Base map: offline dark canvas, Natural Earth 110m coastline GeoJSON plus graticule. No tiles.

## Telemetry contract (frozen)

```json
{
  "vessel_id": "OC-01",
  "event_ts": "2026-11-01T10:15:30.000Z",
  "seq": 1042,
  "lat": 35.12, "lon": -142.40,
  "heading_deg": 87.5, "speed_kn": 6.2,
  "battery_pct": 81.3, "fuel_l": 412.0,
  "debris_density": 0.63,
  "hold_fill_pct": 22.0,
  "buffered": false
}
```

- `event_ts`: ISO-8601 UTC, sim time. All windows and watermarks use it.
- Dedup key: `(vessel_id, seq)`: in-batch in streaming, full dedup in the batch silver job (ADR-0005).
- `buffered`: true for events replayed from the offline queue.
- Ingestion derives `zone` = 5° cell id (e.g. `N35W145`); Kafka key = `vessel_id|zone`.
- Longitude −180..180 everywhere outside the raw SCUD files (raw is 0–360).
- Defined once in `common/telemetry.py` (pydantic model + Spark `StructType`). PostGIS DDL in `infra/postgres/init.sql` must match.

## Components

| Dir | Responsibility |
|---|---|
| `infra/` | `docker-compose.yml`: kafka (KRaft, 3.7.2), postgis, minio, spark, ingestion, api, web, simulator |
| `common/` | telemetry contract, geo helpers, zone function |
| `simulator/` | sim clock, vessel physics + fuel model, debris world (patches advected by currents), offline buffer, route follower, loiter, `--fast-forward 30d` backfill |
| `ingestion/` | FastAPI `POST /telemetry` (single + batch) → Kafka `telemetry` (6 partitions); `debris_survey` topic |
| `streaming/` | Spark Structured Streaming, checkpoint on a local volume. Main query has **no watermark** (ADR-0005): `foreachBatch` writes every event, with in-batch dedup on `(vessel_id, seq)`, as a dual write (guarded PostGIS UPSERT + bronze Parquet). A separate windowed query (watermark, 5-min windows) feeds the z-score fuel anomaly. Recalc gate → routing |
| `batch/` | `fetch_currents.py`, `fetch_microplastics.py` (API → bronze + cache), PySpark ETL: currents grid (silver), climatology + divergence hotspots (gold), hotspot × microplastics join (gold), telemetry gold aggregates |
| `routing/` | pure Python: bilinear u/v interpolation, RK2 advection, intercept bisection, energy model, greedy 3-target chain, 2 km deviation gate |
| `api/` | FastAPI REST + WebSocket `/ws` (vessel state, route proposals, alerts, sim clock); operator actions `POST /routes/{id}/accept|reject|modify` |
| `web/` | React + TS strict + Tailwind + shadcn/ui + Leaflet (default Web Mercator, no tiles: dark canvas; changed from CRS simple in M4) + canvas particle layer + Recharts |

## Routing rules

- Patch prediction: RK2 on the time-interpolated SCUD grid, dt = 1 sim-hour.
- Vessel ground velocity = water velocity + thrust vector at cruise speed (6 kn).
- Intercept: earliest t in [0, 7 days] where the vessel can reach p(t); bisection on reachability.
- Energy: P(v) = k·v³ (+ hotel load); energy = ∫P dt. Score = patch mass / energy.
- Chain: greedy, best score first, up to 3 targets, recomputed from each target's predicted position.
- Gate: on every micro-batch, recompute when any active target's re-predicted intercept point has moved > 2 km, a target was collected, or there is no active route.
- HITL: new route → `routes.status='pending'`. Accept → `active`. Reject → keep the previous route or loiter. Modify → operator-moved waypoint, `active`. Timeout 30 s → `expired`: keep the active route, or loiter (low-power circle at the current position) if there is none. The sim clock is held while a proposal awaits the operator (ADR-0008).
- Hold at 100% → offload pause (6 sim-hours), hold → 0.

## Out of scope

Fleet, auth, real hardware, mobile layouts, Iceberg, 3D, live tiles.

## Milestones

See `issues/01..07` (02 = M1.5 review fixes; M2..M6 = issues 03..07). Cut order if late: time-slider replay → anomaly alert → Analytics tab.
