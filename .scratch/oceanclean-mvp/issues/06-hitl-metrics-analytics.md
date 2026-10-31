# 06 (M5) HITL modal, Metrics, Analytics, alerts
Status: open
Blocked by: 05
Estimate: 3 h

## Do
- Operator view: telemetry panel, AI Route Optimization modal (demo2 style) with Accept / Reject / Modify (drag waypoint), 30 s countdown → loiter.
- Admin Metrics tab (demo3 style): events/s, Kafka lag, micro-batch duration, lake row counts (Spark StreamingQueryListener → PostGIS `pipeline_metrics`), fuel/battery, debris removed vs energy (Recharts).
- Analytics tab: gold aggregates via REST (debris per kWh by day/zone, route acceptance rate, hotspot validation ratio).
- Streaming: a **separate** watermarked query (ADR-0005) with 5-min tumbling event-time windows; late rows may miss a window (acceptable, documented); z-score fuel-burn anomaly → `alerts` → WS toast.
