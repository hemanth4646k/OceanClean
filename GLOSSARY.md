# Glossary

- **Cleaner / vessel**: the single cleanup ship (`OC-01`).
- **Patch**: a synthetic debris cluster (position, mass kg, radius) seeded from hotspots and advected by currents.
- **Ghost**: a patch's predicted position at the planned intercept time.
- **Hotspot**: a grid cell with persistent negative divergence of surface currents (convergence), where floating debris accumulates.
- **Intercept**: the earliest point where the vessel can meet a drifting patch.
- **Recalc gate**: the rule that triggers route recomputation only on > 2 km predicted deviation, a collected target, or no active route.
- **Loiter**: the fail-safe low-power circling mode used when the operator doesn't answer within 30 s.
- **Sim clock**: compressed simulation time; all `event_ts` values are sim time.
- **Bronze / silver / gold**: raw / cleaned / aggregated lake layers.
- **Zone**: 5° lat/lon cell id derived at ingestion, part of the Kafka key.
