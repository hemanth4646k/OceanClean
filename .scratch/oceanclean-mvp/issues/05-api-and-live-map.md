# 05 (M4) API + live map (core demo story)
Status: done
Blocked by: 04
Estimate: 4 h

## Do
- `api/`: FastAPI REST `/vessel`, `/routes/active`, `/routes/pending`, `/patches`, `/currents/grid`, `/hotspots`, `/sim/clock`; WebSocket `/ws` broadcasting state, patches, route proposals, alerts (polls PostGIS / LISTEN-NOTIFY).
- `web/`: Vite React TS strict, Tailwind dark, shadcn/ui. Leaflet with offline dark canvas: coastline GeoJSON + graticule. Canvas particle layer from the u/v grid. Layers: particles, debris heatmap, hotspot overlay, vessel wake, patches, ghosts + drift lines, route. Layer toggle panel (demo1 style).
- Sim clock control (play/pause/speed) via API → simulator.

## Done when
- Browser shows particles flowing, patches drifting, vessel following an accepted route toward ghosts, patches disappearing on collection.

## Comments

2026-10-31: Done. Verified against the running stack at `SIM_RATE=3600` (from `.env`), both through the Vite dev server and the `web` nginx container. Headless Chrome screenshots showed every layer.

- **Done-when.** Current particles flow through the mission grid. Patches drift hourly with the surveys. The stale route 1 was accepted from the UI path (`POST /api/routes/1/accept`); the simulator picked it up within one poll and steamed at 6 kn. The gate proposed route 2 (`deviation`). Accepting it superseded route 1, and the vessel collected P30: mass 0, hold 0 → 71 %. P30 then faded to a grey dot, its heat glow went, and a toast reported it. Route 3 was proposed next.
- **API (`api/`, port 8002).** REST `/vessel` (state + wake), `/routes/active|pending`, `POST /routes/{id}/accept|reject`, `/patches`, `/currents/grid?t=` (u/v slice at sim time, `CurrentField.grid_at`), `/hotspots`, `GET|POST /sim/clock`, `/config`. `/ws` polls PostGIS each second (`store.snapshot`). It sends the full snapshot on connect, then only changed parts, plus alerts: proposal, route active, patch collected (`live.changes`). Accept supersedes the old active route in one transaction, `FOR UPDATE`, and sets `decided_at`.
- **Sim clock control.** New `sim_clock` table: the simulator reports and adopts the operator's rate/pause every second (ADR-0003 addendum). Pause froze `sim_now`; resume continued without a jump.
- **Web (`web/`, port 8080; dev 5173).** Vite + React 19 + TS strict, Tailwind v4, shadcn/ui (base-nova), react-leaflet. Offline base map: Natural Earth 110m land polygons + a canvas graticule. Canvas panes for current particles, debris heat and graticule. SVG layers: hotspot cells, patches, ghosts + drift lines, route lines, vessel + wake. Layer toggles, particle speed, clock bar (play/pause, 1 min/s … 2 h/s, mission day), stats bar, toasts.
- **Tests.** `grid_at` (2), `live` (8: wake, diffs, alerts), `store` against PostGIS on temp copies of `routes`/`sim_clock` (4), `parse_utc`, the API vessel columns = telemetry contract. 111 unit + 20 Spark pass, ruff clean, `tsc -b` clean.

Decisions:

- **Map projection.** Leaflet's default Web Mercator instead of spec.md's "CRS simple": without tiles both are a dark canvas, and Mercator keeps particle directions conformal at 30–40°N. spec.md updated.
- **Wake.** Kept in API memory (48 sim-h, 2000 points) and extended client-side; an API restart starts it fresh. The lake has the full track.
- **Collected patches** fade to grey rather than vanish (spec story 4: "Patches fade as they're collected").

Review (`/code-review` since 91194bf, both axes). Fixed before commit:

- `/currents/grid?t=` accepted naive datetimes (read in container time). Now 422. `settings.parse_utc` is shared and rejects naive input.
- The `Minio(...)` construction was repeated in api, simulator and batch; it is now `oceanclean_common.lake.minio_client` (closes a ticket-04 open item).
- The API's clock body was renamed `ClockUpdate` (it clashed with the simulator's `ClockControl`).
- A contract test pins the API's vessel columns to `Telemetry`.
- The Vite proxy has no env fallback.
- CLAUDE.md commands and ports were updated.

Left open (judgement calls):

- The TS types in `web/src/lib/types.ts` are hand-kept copies of the API shapes, with no contract test.
- Route status strings are not an enum (as in ticket 04).
- The wake logic exists in both API and client (snapshot vs incremental).
- Accept/reject and active/pending endpoints are near-duplicates.
- nginx runs as root (stock image).

For ticket 06:

- `RouteCard` (Accept/Reject in the sidebar) and `StatsBar` are stand-ins: replace them with the demo2 modal and the telemetry panel.
- **Pending routes never expire yet.** The gate proposes nothing while one is `pending`, so an unanswered proposal blocks routing forever (route 1 sat pending for 50 sim-days). M5's 30 s timeout must set `expired`.
- **Pause while pending** is `POST /sim/clock {"paused": true}`; the simulator adopts it within a second. Resume on the decision or the timeout.
- `/ws` alerts have `kind`/`level`/`text`/`ts`; the anomaly alerts can use the same message.
