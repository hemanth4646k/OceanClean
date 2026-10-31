# 0007 Route lifecycle, recalc gate details, and the simulated debris world

Status: accepted, 2026-10-31 (M3)

**Gate.** The spec's three triggers (no active route, a target collected, a re-predicted intercept > 2 km away) run in the telemetry `foreachBatch` after the live-state UPSERT, against PostGIS (`vessel_state`, `debris_patches`, `routes`). Two rules were added so the gate does not flood the operator every 2 s micro-batch:

- No proposal while one is `pending`. A partial unique index enforces at most one `pending` and one `active` route per vessel.
- At most one proposal per 30 sim-minutes (`MIN_INTERVAL_S`), measured from the latest route's `planned_at`. This throttles re-proposals after a reject or expiry.

Routing is advisory. A planner exception is logged and the sinks still commit. If no patch is reachable, the gate retries after 30 sim-minutes. The greedy step scores every live patch, with no nearest-N cut, so a heavy distant patch can still win.

**Route rows.** `waypoints` (start + one per target) are what the vessel steers for, and a Modify moves them. `targets` keep the optimizer's view: the patch as last surveyed (`now`), the predicted intercept (the ghost), the drift line, and transit, dwell, energy and score per leg. The gate re-checks `targets.predicted`, not the waypoints. Statuses: `pending → active | rejected | expired`, and `active → superseded` when a newer route is accepted. M5's API owns those transitions and the 30 s timeout. Decided 2026-10-31: the sim clock is **paused while a proposal is pending**, so the 30 s real-time timeout does not cost the vessel sim-hours of loitering (at `SIM_RATE=3600`, 30 s would be 30 sim-hours).

**Sim time → data time.** The mission window holds 45 SCUD days (2026-08-02..09-18). Sim time maps onto it as window start + (sim − `SIM_START`), looped over the window, and interpolation uses the real, uneven time axis. A 30-day run never wraps.

**Debris world (simulator).** 40 patches are seeded in mission-box hotspot cells. The weight is 1, plus a bonus capped at 3 × `mp_median / median(mp_median)` for measured cells. Each patch is ~3.5 t × √weight, and the RNG is seeded, so the world is reproducible. Patches drift by RK2 through the same field the optimizer uses, plus a windage term (Ornstein–Uhlenbeck, σ 3 cm/s, τ 12 h) that the optimizer does not model. That windage is what makes the 2 km gate fire. A headless 30-day run with instant accepts cleared 212 t in ~26 sim-days with 8 offloads; operator decision time stretches that towards day 30. The run produced 74 proposals (35 deviation, 38 collection, 1 no-route). Plans took 211 ms median and 394 ms max, against the SLA of 60 s.

**Route follower.** The simulator reads its active route straight from PostGIS every 3 real seconds; the spec allows "PostGIS/API". This is the vessel's uplink, not a UI consumer, so it does not go through the M4 REST/WebSocket layer. It steers for the waypoint with a crab angle against the current. Within 10 km it homes on the patch it can see. Inside the patch radius it collects at 2 kn. With no route it loiters on a 500 m circle around the point where it stopped, crabbing so the current does not carry it away.

**Edge behaviour.** Outages happen at 1 per ~30 sim-hours and last 20 min–2 h. During an outage, and on any failed POST, telemetry queues at the edge and is flushed in order with `buffered=true`. The queue is persisted in the sim state file. A survey missed while offline is skipped, because the next one supersedes it. The vessel keeps following its last known route while offline.
