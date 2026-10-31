# 06 (M5) HITL modal, Metrics, Analytics, alerts
Status: done
Blocked by: 05
Estimate: 3 h

Read the ticket 05 comment first: stand-in UI to replace, pending routes never expire yet, clock pause via `POST /sim/clock`.

## Do
- Operator view: telemetry panel, AI Route Optimization modal (demo2 style) with Accept / Reject / Modify (drag waypoint), 30 s countdown → loiter.
- Pause the sim clock while a route is `pending`, and resume it on the decision or the timeout (decided 2026-10-31, ADR-0007). The 30 s countdown is real time.
- Admin Metrics tab (demo3 style): events/s, Kafka lag, micro-batch duration, lake row counts (Spark StreamingQueryListener → PostGIS `pipeline_metrics`), fuel/battery, debris removed vs energy (Recharts).
- Analytics tab: gold aggregates via REST (debris per kWh by day/zone, route acceptance rate, hotspot validation ratio).
- Streaming: a **separate** watermarked query (ADR-0005) with 5-min tumbling event-time windows; late rows may miss a window (acceptable, documented); z-score fuel-burn anomaly → `alerts` → WS toast.

## Comments

2026-10-31 (first session) — In progress at the time; the plan below was completed in a second session (see the closing comment at the end).

User decisions (2026-10-31):

- **Autopilot is ON by default** for the simulation. It decides each proposal at once and never holds the clock. Turning it off shows the 30 s modal for the live HITL demo.
- **Autopilot rule.** When idle (no active route, or every target of it collected, so the vessel loiters) it accepts anything. Mid-route it accepts only `deviation` proposals (the vessel steers for the stored ghost and sees a patch only within 10 km, so an ignored deviation could strand it). Other mid-route proposals are rejected with `decided_by='autopilot'`, so the gate is not blocked.
- **Timeout** (manual mode, 30 s real time) → `expired`. The vessel keeps its active route, or loiters if it has none.
- **Energy is derived; the telemetry contract stays frozen.** Debris removed comes from hold deltas.
- **The silver + gold telemetry batch job moves into 06** (out of 07). Analytics reads gold.
- **No solar** for now.

Done (uncommitted):

- `routing/energy.py`: `KWH_PER_L` (exact inverse of `fuel_l`). `BATTERY_KWH` moved here from `simulator/fuel.py`.
- `simulator/fuel.py`: `burn(..., fuel_factor)` (leak = more fuel for the same power). `world.tick(..., fuel_factor)`.
- `simulator/sim_main.py`: `ClockControl.sync` now returns `paused OR hitl_hold` and `sim_faults.fuel_leak_until`. `LEAK_FACTOR = 1.5` applies while `next_tick < leak_until`. **The simulator image is not rebuilt yet.**
- `streaming/anomaly.py` (pure) + `tests/test_anomaly.py`.
  - `WindowAgg` (one closed window: state at its last tick, `sum_v3` = Σ speed_ms³, `n_collect` = ticks at `COLLECT_KN`).
  - `Tail` (the previous window's last tick).
  - `score(tail, windows, history, tick_s)`. Energy is measured **from the previous window's last tick**, so no interval falls between windows: max(0, fuel drop) × `KWH_PER_L` + battery drop × `BATTERY_KWH`. `expected_kwh` comes from the power model. Residual = (measured − expected)/expected.
  - The z-score uses the last 48 normal residuals (std floor 0.02). An anomaly needs z ≥ 4 and residual ≥ 0.2 (battery clamping adds up to ~8 %). `onset` = the first anomalous window of a run.
  - Refuels and gaps (ticks ≠ n) are measured but not scored. With no tail, or sim time going back (a reset), there is no baseline.
- `api/hitl.py` (pure) + `tests/test_hitl.py`: `decide(pending, active, live_patch_ids, autopilot, waited_s, timeout_s)` → `accept | reject | expire | hold | None`.
- `infra/postgres/init.sql` (**already applied to the running DB**):
  - `routes.decided_by` (operator | autopilot | timeout) and `sim_clock.hitl_hold`.
  - New tables `sim_faults`, `telemetry_windows` (PK vessel_id, window_end), `alerts` (UNIQUE vessel_id, kind, ts), `pipeline_metrics` and `lake_counts`.
- `api/store.py` + `tests/test_store.py` (temp tables):
  - `accept_route(conn, id, by)`, `reject_route(conn, id, by)` and `expire_route`.
  - `modify_route(conn, id, {patch_id: (lat, lon)})`. It moves target waypoints only and rebuilds `geom`; ValueError for non-targets.
  - `set_hitl_hold`, `set_fuel_leak(conn, vessel, hours)` (sim_now + hours) and `new_alerts(conn, after_id)`.
  - `decided_by` is added to `ROUTE_COLS`, `hitl_hold` to `CLOCK_COLS`.

Steps 1-3 done (2026-10-31, second session; verified on the stack). Step 3: `hitl.step` + `acceptance_rates` (pure, tested), store reads `metrics_series` / `hourly_windows` / `decision_counts` (PostGIS tests), hub applies HITL each poll and broadcasts `alerts` rows; endpoints `/hitl`, `/routes/{id}/modify|extend`, `/sim/fault`, `/metrics`, `/analytics`. On the stack: autopilot accepted idle proposals, manual mode froze `sim_now` and expired at the deadline (`timeout`), extend +60 s, modify 422/409/accept. Step 2: `batch/telemetry_etl.py` + Compose `telemetry-etl` (profile batch), lake paths in `regions.py`, Spark fixture tests. Step 1: `streaming/window_stream.py` (aggregation + watermarked chain; dedup -> window chaining works in 3.5 append mode, tested on a streaming memory sink), `streaming/stream_store.py` (psycopg writes; PostGIS tests), `streaming/pipeline_metrics.py` (listener). `to_utc` moved to `oceanclean_common.settings`. Spark tests now run through the bitnami entrypoint (no `--entrypoint python`), which gives the uid a passwd entry, so streaming/file writes work in tests. The scorer skips empty-tank windows (the stale run had run dry: the sim clamps fuel at 0 while adrift, so the hotel load goes unpaid).

Remaining (design already worked out):

1. **Streaming** (`streaming/`; new modules keep `telemetry_stream.py` from growing).
   - `window_aggregates(df)`: `groupBy(vessel_id, window(event_ts, "5 minutes"))`, then `count`, `max(event_ts)` as last_ts, `max_by(fuel_l|battery_pct|hold_fill_pct, event_ts)`, `sum(pow(speed_kn*KN_TO_MS, 3))` and `sum(speed_kn == COLLECT_KN)`; select `window.end`. Write a Spark fixture test for it first (pattern: `tests/test_stream_spark.py`).
   - The query is the third one, separate (ADR-0005): `parse_telemetry(read_kafka(..., startingOffsets="latest"))` → `withWatermark("event_ts", "10 minutes")` → `dropDuplicatesWithinWatermark(["vessel_id","seq"])` (verify that dedup → agg chaining works in 3.5 append mode) → `window_aggregates` → append → `foreachBatch`.
   - Why "latest": old-run events in Kafka would push the watermark past a reset run.
   - The `foreachBatch` writer, per vessel: load the tail (latest `telemetry_windows` row) and history (last 48 non-anomalous residuals) → `score` → insert windows `ON CONFLICT DO NOTHING` → insert an `alerts` row (kind `fuel_anomaly`, level `warn`) on onset.
   - New setting `WINDOW_CHECKPOINT_DIR=/checkpoints/windows` in `.env.example`. Name the queries (`.queryName`): telemetry, debris_survey, windows.
   - A `StreamingQueryListener` (python, PySpark 3.5 has it; implement onQueryStarted/Progress/Idle/Terminated) inserts `pipeline_metrics`: progress.timestamp, name, batchId, numInputRows, input/processedRowsPerSecond, durationMs.triggerExecution, and Kafka lag = `sources[i].metrics["maxOffsetsBehindLatest"]`.
   - The telemetry and survey writers add their bronze row counts to `lake_counts` (`bronze/telemetry`, `bronze/debris_survey`).
   - spark-stream `mem_limit` 2g → ~2.5g (it already uses 1.6 GB).
2. **Batch** `batch/telemetry_etl.py` + Compose service `telemetry-etl` (profile batch; mounts common, batch, routing).
   - bronze/telemetry → full dedup (vessel_id, seq) → `silver/telemetry` by date (overwrite).
   - Per-row deltas via a lag over seq per vessel: energy = max(0, Δfuel drop) × KWH_PER_L + battery drop × BATTERY_KWH; collected = max(0, Δhold) × HOLD_CAPACITY_KG/100.
   - A Spark `zone` expression must match `zone_of` (test it).
   - `gold/telemetry_daily` and `gold/telemetry_daily_zone` (energy, collected, kg/kWh, rows).
   - Export `gold/exports/analytics.json` for the API, and upsert silver/gold counts into `lake_counts`.
   - Spark fixture tests: dedup, deltas across a refuel, zone parity.
3. **API** (`api/api_app.py`).
   - Hub loop each poll: `hitl.decide(...)` with `live_patch_ids` = patches with mass > 0 and `waited_s` = now − created_at (+ any Modify extension). Apply it: accept/reject (by autopilot) / expire / `set_hitl_hold(True)` while holding; release the hold when nothing is pending.
   - Patch the snapshot before diffing, so autopilot decisions do not toast "proposal".
   - Autopilot state lives in hub memory, default from the new setting `AUTOPILOT=true` (and `HITL_TIMEOUT_S=30`) in `.env.example`.
   - Add a `hitl` part to `live.PARTS`: {autopilot, timeout_s, deadline}.
   - Broadcast new `alerts` rows (`new_alerts`, after the max id at startup).
   - Endpoints:
     - `GET/POST /hitl` {autopilot}.
     - `POST /routes/{id}/modify` {waypoints: {patch_id: [lat, lon]}} (422 on ValueError).
     - `POST /routes/{id}/extend` (gives a Modify in progress +60 s before the timeout).
     - `POST /sim/fault` {hours}.
     - `GET /metrics?minutes=` (pipeline_metrics series + latest per query, lake_counts, hourly `telemetry_windows` sums: energy, collected, last fuel/battery, anomalies).
     - `GET /analytics` (analytics.json + operator acceptance rate from `routes` by decided_by/status, with null decided_by = operator, + hotspot validation).
4. **Web.**
   - Install `recharts`. Tabs: Live map | Metrics | Analytics (header role switch Operator/Admin, spec: "header switch for Admin / Operator role").
   - An AI Route Optimization modal (demo2) shown when pending and autopilot is off: current vs proposed route (debris t, energy MWh, kg/kWh, chain), a 30 s countdown bar from `hitl.deadline`, and Accept / Modify / Reject. Modify makes the pending target waypoints draggable markers, then Confirm posts `/modify`.
   - Replace the stand-ins `RouteCard` (keep a compact summary) and `StatsBar` (telemetry panel).
   - An autopilot switch in the sidebar. The clock bar shows "held for decision" when `hitl_hold`.
   - The Metrics tab (demo3 style) shows:
     - tiles: events/s, Kafka lag, batch duration, lake rows;
     - charts: events/s and batch duration over wall time, fuel and battery, debris removed vs energy;
     - an "Inject fuel leak (6 h)" button. The leak only shows while the engine runs, not while loitering on battery.
   - The Analytics tab: debris per kWh by day and by zone, acceptance rate, validation ratio. Anomaly alerts arrive as WS toasts (`kind: fuel_anomaly`).
5. **`infra/reset_sim.sh`**:
   - Also truncate `telemetry_windows, alerts, pipeline_metrics, lake_counts, sim_faults`.
   - Delete the `/checkpoints/windows` dir in volume `oceanclean_spark-checkpoints` while spark-stream is stopped. Its watermark would otherwise drop the reset run's events.
   - Delete the lake prefixes `silver/telemetry/`, `gold/telemetry_daily*/` and `gold/exports/analytics.json`.
6. **Docs.**
   - ADR-0008: autopilot and HITL rules, `decided_by`, the clock hold, the timeout keeping the route, and energy derivation/anomaly.
   - ADR-0005 note: the windows query uses `latest` offsets.
   - Ticket 07: the silver/gold job moved here.
   - CLAUDE.md Status/Commands/Ports; GLOSSARY (Autopilot, Window).
7. **Verify on the stack.**
   - Rebuild py image; restart spark-stream; re-apply init.sql if changed; run `infra/reset_sim.sh` for a clean run (ask the user first: it deletes the sim run).
   - Check that autopilot accepts and ignores per the rule, that manual mode holds the clock and the timeout expires, that Modify works, and that an injected leak during transit raises a toast.
   - Check that the Metrics/Analytics tabs fill after `telemetry-etl`. Take headless Chrome screenshots (`google-chrome --headless=new --screenshot`).
   - Then `/code-review` since a879745 → status done + comment → commit.

2026-10-31 (second session) — **Done.** Every "Remaining" step 1-7 is implemented and verified on a clean run (`infra/reset_sim.sh`, run with the user's OK, at `SIM_RATE=3600`). 142 unit + 36 Spark tests pass; ruff, `tsc -b` and oxlint are clean.

Verified on the stack:

- **Autopilot** (default on). In ~5 sim days it accepted every idle proposal and every `deviation`, and rejected 12 mid-route `target_collected` proposals. It collected 3 patches and 28 t, through an offload and a refuel.
- **Manual mode.** The proposal toast arrived and `hitl_hold` froze `sim_now`. The route expired at its 30 s deadline (`decided_by=timeout`) with an `expired` toast, and the clock resumed. `/extend` added 60 s each time, capped at 180 s. `/modify` returned 422 on a bad id and 409 when not pending, and a valid modify activated the route with the target moved (`decided_by=operator`).
- **Fuel leak.** `POST /sim/fault` during transit gave one `fuel_anomaly` alert at onset ("Fuel burn 50% above the power model, z = 25"), delivered as a `/ws` toast. Normal windows score residual 0. One-off transitions reach −17 % (the hold filling mid-window) and +8 % (battery clamping), both far from the alert gate.
- **Metrics tab.** The listener writes `pipeline_metrics` for all three named queries, with Kafka lag. `lake_counts` holds the bronze counts from the stream and the silver/gold counts from `telemetry-etl`.
- **Analytics tab.** It fills after `telemetry-etl` (gold daily, day-zone rolled up to zones, acceptance per decider, validation 3.9×).
- **Screenshots** (headless Chrome) of the map, the demo2-style modal, Metrics and Analytics.

Also in this session:

- **`web/nginx.conf`** resolves `api` per request through Docker DNS. After the reset recreated the API container, nginx had kept the old IP and returned 502s.
- **Autopilot decisions raise no toast** (one every few real seconds at 1 h/s).
- **Tabs** live in the URL hash (`#metrics`, `#analytics`), which implies the Admin role.
- **spec.md**: timeout now means keep the route, or loiter if there is none (SRS §5.4).

Review (`/code-review` since a879745, both axes). Fixed before commit:

- a race on `Hub.extra_s` between the poll thread and `/extend` (now a lock);
- unbounded `/extend`, which could hold the clock forever (capped at 3 min);
- the Analytics zone chart read silver while its subtitle said gold (now rolled up from `gold/telemetry_daily_zone`, with a test);
- the Events/s tile used the still-filling bucket;
- duplicated alert queries in `store`.

Left open (judgement calls):

- **Hold latency.** The clock hold takes effect ~1-2 real s after a proposal (API poll + simulator sync), so the vessel moves on up to ~2 sim-h at 1 h/s. A fix would persist autopilot in PostGIS and let the stream set the hold when it inserts the pending route.
- **Modify drag is untested in a real browser.** Only the API path and the rendering are verified.
- **Energy formula in two engines.** It exists in Python (`anomaly`) and Spark (`telemetry_etl`), each tested against `KWH_PER_L`/`BATTERY_KWH`, with no cross-parity test.
- **`write_bytes`** is imported from `currents_etl` (pulls netCDF4); it could move to common.
- **Copied constants in the web.** `FUEL_TANK_L` and the "2 km" text copy simulator/gate constants, adding to the open TS-types contract item from ticket 05.
- **`decided_by` and `reason`** are bare strings, not enums (as with route statuses in tickets 04 and 05).

2026-10-31 (follow-up, from the user's manual check) — The leak test "did nothing" for the user. In fact it raised two `fuel_anomaly` alerts, but at 2 h/s a 6 sim-h leak lasts 3 real seconds, and toasts vanished after 6 s. Changes:

- **Warnings stay up.** Warning toasts (fuel anomaly, expiry) stay until clicked, and the feed keeps the 3 newest.
- **Metrics tab.** `/metrics` returns the 8 newest alerts. The tab shows a "Recent alerts" list, and the fault card shows the last anomaly. Metric lines now break where there were no batches (clock paused) instead of bridging the gap.
- **Automatic analytics.** A new Compose service `analytics` (no profile, so it starts with `up -d`) reruns `telemetry_etl.py` every `ANALYTICS_REFRESH_S` (180 s). Each run is a fresh JVM, so memory is free between runs. A run with no bronze yet (fresh volume, just after a reset) exits cleanly. `reset_sim.sh` stops the service so it cannot rebuild silver/gold from the old run. The manual `telemetry-etl` profile service remains for an immediate refresh.

