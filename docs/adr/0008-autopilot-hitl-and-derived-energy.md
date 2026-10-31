# 0008 Autopilot and the HITL decision, derived energy, and the fuel-burn anomaly

Status: accepted, 2026-10-31 (M5)

**Autopilot is on by default.** The simulation runs at up to 2 sim-hours per real second, and the gate can propose every 30 sim-minutes, so a human cannot keep up outside a live demo. The API hub (`api/hitl.py`, applied every poll) decides each proposal as soon as it appears:

- **Idle** (no active route, or every target of it collected, so the vessel loiters): accept any proposal.
- **Mid-route:** accept only `deviation` proposals. The vessel steers for the stored ghost and sees a patch only within 10 km, so ignoring a large deviation could strand it at an empty ghost. Other mid-route proposals (`target_collected` while targets remain) are rejected, which lets the gate propose again after its 30 sim-minute throttle.
- **Amended 2026-10-31 (M6, with the user): autopilot now accepts every proposal, mid-route `target_collected` included.** The rejection rule did not stop the gate; it only made it re-propose the same situation every 30 sim-minutes until the chain was done. In a live run 19 of 23 autopilot decisions were such rejections, so the Analytics tab showed "12-17 % accepted" for plans that were fine. A fresh greedy chain after a collection is the policy the ADR-0007 headless run (212 t in ~26 days) and the backfill's onboard autopilot (ADR-0009) already used. The two bullets above describe the old rule.
- Autopilot decisions raise no toast: at fast rates there would be one every few real seconds. The sidebar shows the active route and who decided it.

**Manual mode** (autopilot off, the live HITL demo) shows the AI Route Optimization modal:

- While a proposal is pending, the API sets `sim_clock.hitl_hold`. The simulator treats it like a pause (ADR-0007 decision), so the 30 s real-time countdown costs no sim time. The hold is separate from the operator's own pause, and the API releases it when nothing is pending.
- The countdown runs from the route's `created_at`. Modify (drag target waypoints, then confirm) adds 60 s per `/extend`, at most 3 min in all, so the clock cannot be held indefinitely. The hold takes effect within about 2 real seconds of the proposal (API poll, then simulator sync, 1 s each), which is up to ~2 sim-hours at 1 h/s: the vessel moves on that much before the clock stops.
- **Timeout → `expired`.** The vessel keeps its active route, or loiters if it has none. Keeping the route is safer than stopping: the active plan is still valid, just not improved.

**`routes.decided_by`** records `operator`, `autopilot` or `timeout`. Rows decided before M5 have none and count as `operator`. Analytics reports acceptance per decider, and an expiry counts against the operator.

**Energy is derived; the telemetry contract stays frozen.** The vessel reports fuel and battery levels, not power. Energy used between two ticks is `max(0, fuel drop) × KWH_PER_L + battery drop × BATTERY_KWH`, with `KWH_PER_L` the exact inverse of the power model's `fuel_l`. A refuel (fuel rising at an offload) counts as zero. Debris removed is the hold's growth × `HOLD_CAPACITY_KG`, and an offload counts as zero. The same rule runs in two places:

- the speed layer, per 5-minute window, measured from the previous window's last tick;
- the batch job, per tick in silver (`batch/telemetry_etl.py`), lagged over `seq` per vessel.

**Fuel-burn anomaly** (`streaming/anomaly.py`):

- Per closed window: residual = (measured − expected) / expected, where `expected` comes from the power model and the window's Σ v³, tick count and collection ticks.
- The z-score compares the residual with the last 48 normal residuals (std floor 0.02: the simulator is noiseless).
- An anomaly needs z ≥ 4 **and** residual ≥ 20 %. Battery clamping at 100 % adds up to ~8 %.
- One `alerts` row (`fuel_anomaly`, `warn`) at the onset of a run of anomalous windows; the API broadcasts new rows as toasts.
- Windows with a refuel, a gap (rows ≠ ticks), an empty tank (the simulator clamps fuel at 0 while adrift) or no previous window are measured but not scored.
- The demo fault: `POST /sim/fault` makes the engine burn 1.5× fuel for the same power for N sim-hours. It shows only while the engine runs, not while loitering on battery.

**Windows query offsets.** The watermarked query starts from `latest`, not `earliest` (ADR-0005 note). `infra/reset_sim.sh` deletes its checkpoint, because the old run's watermark is in later sim time and would drop the new run's events as late.
