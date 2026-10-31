# 06 (M5) HITL modal, Metrics, Analytics, alerts
Status: open
Blocked by: 05
Estimate: 3 h

Read the ticket 05 comment first: stand-in UI to replace, pending routes never expire yet, clock pause via `POST /sim/clock`.

## Do
- Operator view: telemetry panel, AI Route Optimization modal (demo2 style) with Accept / Reject / Modify (drag waypoint), 30 s countdown → loiter.
- Pause the sim clock while a route is `pending`, and resume it on the decision or the timeout (decided 2026-10-31, ADR-0007). The 30 s countdown is real time.
- Admin Metrics tab (demo3 style): events/s, Kafka lag, micro-batch duration, lake row counts (Spark StreamingQueryListener → PostGIS `pipeline_metrics`), fuel/battery, debris removed vs energy (Recharts).
- Analytics tab: gold aggregates via REST (debris per kWh by day/zone, route acceptance rate, hotspot validation ratio).
- Streaming: a **separate** watermarked query (ADR-0005) with 5-min tumbling event-time windows; late rows may miss a window (acceptable, documented); z-score fuel-burn anomaly → `alerts` → WS toast.
