# 04 (M3) Routing library + debris world + dual write
Status: open
Blocked by: 02, 03
Estimate: 4 h

## Do (TDD, pure functions first)
- `routing/`: bilinear+time interpolation, RK2 advection, intercept bisection (moving target, current-aided vessel), energy model, score, greedy 3-chain, deviation gate (2 km).
- `simulator/`: debris patches seeded from gold hotspots weighted by microplastics; advected each tick; collection within radius → hold fill; offload at 100%; route follower (reads active route from PostGIS/API); loiter; offline buffer (random disconnect → queue → flush with `buffered=true`); fuel model (ShipNetSim-style simplified).
- `debris_survey` topic every 60 sim-min → `debris_patches` table.
- Streaming (ADR-0005, no watermark on this query): dual write in foreachBatch, guarded PostGIS UPSERT + **bronze** Parquet ticks partitioned date/hour, append-only. Silver (full dedup on vessel_id, seq) is a batch job, not streaming. Gate in foreachBatch → write `routes` (LineString 4326, waypoints JSON, targets with predicted points, status pending).

## Done when
- Unit tests: advection on uniform/rotational fields, intercept vs analytic solution for constant current, gate fires/does not fire, chain ordering.
- Routes appear as `pending` in PostGIS; lake has tick Parquet.
