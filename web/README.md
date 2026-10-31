# OceanClean web

Live operator map: Vite + React + TypeScript (strict), Tailwind v4 (dark), shadcn/ui (base-nova), Leaflet via react-leaflet. No tiles: the base map is Natural Earth 110m land polygons (public domain, `src/assets/ne_110m_land.json`) plus a canvas graticule, so it works offline.

- `npm run dev`: dev server on :5173; proxies `/api` and `/ws` to the API on `localhost:8002` (override with `API_URL`).
- `npm run build`: type check + production build (`dist/`).
- In Compose, the `web` service builds this directory and serves it with nginx on :8080.

Layout: `src/lib/` (API types, REST, `/ws` feed hook), `src/map/` (Leaflet layers; canvas panes for current particles, debris heat and graticule), `src/components/` (panels).
