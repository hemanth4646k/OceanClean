# 0003 Compressed simulation clock drives event time

Status: accepted, 2026-10-31

The demo shows about 30 days of cleanup in minutes. The simulator owns a sim clock (adjustable rate, play/pause) and stamps `event_ts` in sim time. Spark windows, watermarks and dedup use event time only, so compressed time is consistent end to end. Watermark and window sizes are in sim time.

**Clock control (M4, 2026-10-31).** The operator's play/pause/speed goes API → PostGIS → simulator, the same way as routes: `POST /sim/clock` updates `rate`/`paused` in the `sim_clock` row, and once a second the simulator upserts its `sim_now` and adopts what the row says (rate 1–7200). The row outlives the simulator, so a speed or pause set before a restart still applies over `SIM_RATE`; `infra/reset_sim.sh` truncates it. A fresh `up -d` that seems frozen may be a stale `paused=true`: check `GET /sim/clock`. The UI extrapolates sim time between reports from `rate`.
