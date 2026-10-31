# 04 (M3) Routing library + debris world + dual write
Status: done
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

## Comments

2026-10-31: Done. Verified against the running stack at `SIM_RATE=60`.

- **Pending routes.** A debris survey of 40 patches reached `debris_patches`. Gate `no_route` then proposed route 1 as `pending` (P21 → P38 → P06, 20.3 t, 4.0 MWh) in 291 ms. Its geometry is a 4-point LineString in SRID 4326. Each target carries its now position, predicted ghost, drift line and per-leg energy/score.
- **Following.** After a manual `active` (stand-in for M5), the simulator picked the route up within one poll and steered at 6 kn toward the ghost. Seven sim-hours of following did not trigger the gate.
- **Deviation.** Nudging P21's surveyed position by ~5.5 km made the gate fire `deviation`. Route 2 was proposed in 473 ms while route 1 stayed active.
- **Lake.** `bronze/telemetry` holds Parquet partitioned by event-time `date/hour`, and Spark reads it back. 10 events that failed while ingestion was being recreated were queued and flushed with `buffered=true`, and reached bronze. `bronze/debris_survey` holds the hourly snapshots.
- **Tests.** 55 new unit tests (routing, simulator, contract, settings) and 3 new Spark tests; 95 unit + 20 Spark pass, ruff clean. They cover the done-when list: uniform and rotational advection, RK2 vs Euler, intercept vs the analytic constant-current solution (3 current/target cases, plus patch-with-current = d/s), gate fires / does not fire (and a vessel following its plan stays < 500 m from the predictions), and chain ordering.
- **Calibration.** A headless 30-sim-day run on the real mission grid with instant accepts cleared 212 t in 26.3 days: 8 offloads, 74 proposals (35 deviation, 38 collection). Plans took 211 ms median and 394 ms max, against the SLA of 60 s.

Decisions (ADR-0007):

- **Gate additions.** Nothing is proposed while a route is `pending`, and at most one proposal is made per 30 sim-min. Partial unique indexes enforce one `pending` and one `active` route per vessel. Routing errors are logged and never block the sinks.
- **Sim time → data time.** Sim time maps onto the 45-day mission window and loops; interpolation uses the real, uneven time axis.
- **Windage.** Patches get windage (σ 3 cm/s, τ 12 h) that the optimizer doesn't model. It is what makes deviations happen.
- **Seeding.** 40 patches are seeded in mission-box hotspots. Weight is 1, plus a bonus capped at 3 × `mp_median`/median.
- **Vessel model.** Diesel-electric with a 300 kWh battery: engine off while loitering or offloading, until a 20 % reserve. Refuel during the 6 h offload. Tank 12,000 L.
- **Survey contract.** `PatchSurvey` lives in `oceanclean_common/debris.py`, with Spark DDL and the `debris_patches` DDL tested to match. Ingestion has `POST /debris-survey` → topic `debris_survey` (1 partition, key `patch_id`).
- **Settings.** `SURVEY_URL`, `SURVEY_CHECKPOINT_DIR`.

For ticket 05 (and 06):

- **Route lifecycle.** Route statuses are `pending | active | rejected | expired | superseded`. The API owns the transitions: Accept sets `active` and the old active route to `superseded` in one transaction (the unique index rejects two `active` rows). It should also set `decided_at`.
- **Timeout vs sim rate.** The 30 s HITL timeout is real time. At `SIM_RATE=3600` it is 30 sim-hours of loitering, so pause the sim clock while the modal is open, or scale the timeout.
- **What to draw.** `routes.targets[*]` has `now`, `predicted` (ghost) and `drift` (25 points), which is all the map needs. `waypoints` are what Modify should edit; the gate keeps checking `targets.predicted`.
- **Stale sim state.** The `sim-state` volume still holds the M1 run: the vessel resumed at −132.8° (outside the mission box, 51 h from the first patch), with the old 2,000 L fuel default (it refuels at the first offload). A clean start (remove `oceanclean_sim-state`, truncate `vessel_state`, `routes`, `debris_patches`) was not done here, because it deletes data. Do it before the M6 rehearsal, or now if M4 wants the vessel inside the box.

Review (`/code-review` since de664b9, both axes). Fixed before commit:

- Test helpers had `noqa` instead of type hints.
- The greedy chain considered only the 12 nearest patches; now it scores all live patches. The calibration result was unchanged.
- Loiter drifted with the current; it now holds a 500 m circle with a crab angle.
- `SIM_START` parsing moved into `settings.sim_start`.
- Waypoint parsing moved to the simulator.
- A duplicated longitude wrap and a stale `__all__` were removed.
- The silver telemetry dedup job was added to ticket 07.

Left open (judgement calls):

- Mode and status strings are not enums.
- The `(patch_id, lat, lon)` tuple appears in several places without its own type.
- `route_record` returns a dict, not a dataclass.
- `telemetry_stream.py` now runs both queries and the field loader.
- The `Minio(...)` construction is repeated in `sim_main` and `batch/fetch_common`.
- Survey POSTs that fail are not retried, by design: the next snapshot supersedes them.
