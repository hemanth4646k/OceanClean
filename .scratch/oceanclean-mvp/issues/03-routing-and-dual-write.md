# 03 Routing library + debris world + dual write
Status: open
Blocked by: 01, 02
Estimate: 4 h

## Do (TDD, pure functions first)
- `routing/`: bilinear+time interpolation, RK2 advection, intercept bisection (moving target, current-aided vessel), energy model, score, greedy 3-chain, deviation gate (2 km).
- `simulator/`: debris patches seeded from gold hotspots weighted by microplastics; advected each tick; collection within radius → hold fill; offload at 100%; route follower (reads active route from PostGIS/API); loiter; offline buffer (random disconnect → queue → flush with `buffered=true`); fuel model (ShipNetSim-style simplified).
- `debris_survey` topic every 60 sim-min → `debris_patches` table.
- Streaming: dual write (PostGIS UPSERT + bronze/silver Parquet ticks partitioned date/hour, append-only); gate in foreachBatch → write `routes` (LineString 4326, waypoints JSON, targets with predicted points, status pending).

## Done when
- Unit tests: advection on uniform/rotational fields, intercept vs analytic solution for constant current, gate fires/does not fire, chain ordering.
- Routes appear as `pending` in PostGIS; lake has tick Parquet.
