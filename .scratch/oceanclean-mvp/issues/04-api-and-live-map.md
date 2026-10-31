# 04 API + live map (core demo story)
Status: open
Blocked by: 03
Estimate: 4 h

## Do
- `api/`: FastAPI REST `/vessel`, `/routes/active`, `/routes/pending`, `/patches`, `/currents/grid`, `/hotspots`, `/sim/clock`; WebSocket `/ws` broadcasting state, patches, route proposals, alerts (polls PostGIS / LISTEN-NOTIFY).
- `web/`: Vite React TS strict, Tailwind dark, shadcn/ui. Leaflet with offline dark canvas: coastline GeoJSON + graticule. Canvas particle layer from the u/v grid. Layers: particles, debris heatmap, hotspot overlay, vessel wake, patches, ghosts + drift lines, route. Layer toggle panel (demo1 style).
- Sim clock control (play/pause/speed) via API → simulator.

## Done when
- Browser shows particles flowing, patches drifting, vessel following an accepted route toward ghosts, patches disappearing on collection.
