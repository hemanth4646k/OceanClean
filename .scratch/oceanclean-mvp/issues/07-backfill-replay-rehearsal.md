# 07 (M6) Backfill burst, time-slider replay, rehearsal
Status: done
Blocked by: 06
Estimate: 2 h

## Do
- Simulator `--fast-forward 30d`: ~2.6M ticks burst through ingestion/Kafka; then the `telemetry-etl` job (from 06).
- ~~Silver telemetry batch job~~: moved into 06 and done there (`batch/telemetry_etl.py`, Compose `telemetry-etl`: silver/telemetry, gold/telemetry_daily(_zone), `gold/exports/analytics.json`). Here: run it after the backfill and check the Analytics tab fills.
- Time slider: replay patch drift over a historical window from silver currents.
- Clean-start rehearsal with network off; fix anything flaky. Record 2-min backup video. Update CLAUDE.md Commands + Status.

## Comments

2026-10-31 — Code done; network-off rehearsal and video left to the user.

- **Backfill at 1 Hz (decided with the user, ADR-0009).** At the live 60 s tick, 30 days is only 43,200 events, and the "~2.6M" claim needs 1 Hz. `sim_main.py --fast-forward 30d --tick 1` (Compose `backfill`, profile `batch`) simulates the previous mission, [SIM_START − 30 d, SIM_START). It has its own debris world and an onboard instant-accept autopilot (same gate and planner), sends no surveys, and leaves the live state file alone. The vessel steps at 1 s and patches drift every 60 s; a test checks that 1 s and 60 s ticks agree. History seqs are 1..n; live runs now start at 10,000,001. The backfill refuses to start while the live run is from before M6 or under an hour past SIM_START, so the UPSERT guard and the windows' watermark keep history out of live state and windows.
- **Measured.** A clean start (`reset_sim.sh`) then the backfill sent 2,592,000 events in 210 s (~12k/s, all acked). The Metrics tab shows the burst (~10–26k rows/s for 4 min, Kafka lag back to 0). There were no history windows and no alerts. Bronze reached 2.61M rows. `telemetry-etl` took 45 s and the Analytics tab shows 2 Aug – 17 Sep. Daily energy is ~1–1.5 MWh at both tick sizes.
- **Silver segments.** A tick is measured only when it directly follows the previous seq, so the jump from history to live (a new mission and a full tank) does not count as one tick's consumption. Trade-off: if the offline queue ever overflows (100k events dropped), the dropped span counts as zero, where before it was one lumped delta.
- **Time slider.** `/replay` puts 4 parcels in each of the 30 mission-box hotspot cells and drifts them by RK2 through the mission window's 45 days of real SCUD daily currents. That is the gold `mission_currents.npz`, built from silver currents. The ticket's "patch drift from silver currents" is met through that export. The parcels are weightless with no windage, unlike the sim's patches. The API computes the replay at startup (~3.5 s, 460 KB, 188 frames of 6 h). The map hides the live overlays and shows the parcels with 7-day trails over each frame's current particles (`/currents/grid?t=`). It plays the window in ~27 s, with a scrub slider.
- **Offline check.** Only `batch/fetch_*.py` call the internet, and they fall back to `data/cache`. The web bundle has no CDN references. Don't prune the Docker build cache before the demo: a rebuild would then need the network for pip and npm.

Review (`/code-review` since f7ff0c5, both axes). Fixed: ADR said "waits" where the code refuses; a misleading `Lake.warm` docstring; `survey`/`surveys` name clash (now `observe`); an implicit route id; duplicated vessel and world setup (`fresh_start`); a hard-coded "45 days" in the UI; `useReplay` without a return type; the history's looped currents now documented in ADR-0009. Left as judgement calls: `history()` repeats `tick()`'s steps on purpose (different drift cadence); the date formatter copied from `ClockBar`; bare tuples for (seq, ts) and parcels.

2026-10-31 (follow-up, with the user) — **Autopilot accepts every proposal.** The Analytics tab showed "12 % autopilot acceptance". Mid-route, autopilot rejected `target_collected` proposals, and the gate then re-proposed the same situation every 30 sim-minutes until the chain was done: 19 of 23 decisions in a live run. Autopilot now accepts all proposals, the policy of the ADR-0007 headless run and the backfill's onboard autopilot. ADR-0008 is amended; the dead reject path in the API hub is gone. Rows from earlier runs keep their old decisions until `reset_sim.sh`.
- **Modify drag verified in a real browser** (ticket 06 had it open). Headless Chrome driven over DevTools ran Modify, a mouse drag of the first handle and Confirm. Route 33 became `active`, `decided_by='operator'`, with P21's waypoint moved by the dragged distance; the bar showed "1 moved · 81 s left" with the clock held. Cosmetic issue only: ghost labels can overlap near the vessel.
- **Left as is:** the 1–2 s hold latency (fixing it touches stream, API and simulator) and the code-tidiness items of tickets 04–06 (enums, TS contract test, duplicated helpers, nginx as root, energy parity test). None of them shows in the demo.

2026-10-31 (closing, with the user) — **Closed.** All code is done and verified. The network-off clean-start rehearsal and the 2-min backup video are presentation prep, not software work, so they no longer block this ticket; the user will do them before the demo.
