# 03 (M2) Batch: currents + microplastics → lake → hotspots
Status: done
Blocked by: 02
Estimate: 4 h

## Do
- `batch/fetch_currents.py`: ERDDAP `scud_pac` griddap .nc, monthly chunks, history box 20–45°N 180–230°E (0–360), ~2 years; mission box last ~45 days. Writes bronze `raw/currents/` on MinIO + `data/cache/`. On API failure: use cache, log `source=cache`, record fetch metadata (source, fetched_at) in PostGIS `data_sources`.
- `batch/fetch_microplastics.py`: NCEI ArcGIS FeatureServer query (gyre envelope, paged) → bronze JSON + cache.
- PySpark ETL: NetCDF → rows (time, lat, lon[-180..180], u, v) → silver `currents/` partitioned by `date`; gold `climatology/` (month, cell mean u/v); gold `convergence/` (divergence via neighbour differences, persistent negative-divergence ranking); gold `hotspot_validation/` (cell join with microplastics, concentration ratio convergent vs rest).
- Export the mission-window grid as a compact JSON/NPZ the API and simulator load.

## Done when
- Row counts printed (target ~29M vectors).
- Validation ratio computed and saved.
- Works with the network off (cache path).

## Verified facts (2026-10-31, from the planning session)

**SCUD currents (ERDDAP griddap)**
- Dataset `scud_pac`, server `https://upwell.pfeg.noaa.gov/erddap`. `coastwatch.pfeg.noaa.gov` returned 503 that day; don't depend on it.
- Coverage: 2012-03-17 → 2026-09-18 (daily), lat −70.125..61.875, **lon 119.875..291.875 (0–360)**. Vars `u`, `v` (m/s, ~15 m depth), dims [time][latitude][longitude], ¼°.
- Working subset URL (needs **`curl -L`**: plain request returns 302 with an empty body):
  `https://upwell.pfeg.noaa.gov/erddap/griddap/scud_pac.nc?u[(last)][(30):(40)][(210):(225)],v[(last)][(30):(40)][(210):(225)]` (URL-encode `[` `]`). 1 day of a 10×15° box = 27.5 KB NetCDF. Use `(YYYY-MM-DD)` instead of `(last)` for date ranges.
- Size estimate: the history box 20–45°N × 180–230°E is ~20k cells/day (~230 KB/day); 2 years ≈ 170 MB raw. Fetch in monthly chunks; fall back to 1 year if slow.
- Convert lon to −180..180 in the ETL (`lon - 360` where lon > 180).
- `netCDF4` and `pyarrow` are already installed in the `oceanclean-spark` image. The `oceanclean-py` image has neither; add them if fetchers run there.

**NCEI Marine Microplastics (ArcGIS FeatureServer, no auth)**
- Query endpoint: `https://services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/Marine_Microplastics_WGS84/FeatureServer/0/query`
- Gyre envelope: `geometry=-180,20,-130,45&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects` → **2,315 records** (22,530 total). Page with `resultOffset`/`resultRecordCount`, `outFields=*`, `f=json`.
- Useful fields: `Latitude__degree_`, `Longitude_degree_`, `Medium` (filter `Ocean water`), `Sampling_Method` (mostly `Neuston net`), `Microplastics_measurement`, `Unit` (e.g. `pieces/m3`; **units vary, so normalise or filter to one unit**), `Concentration_class_text`, `Date_m_d_yyyy` (epoch ms), `Short_Reference`, `DOI`, `ORGANIZATION`.

## Comments

2026-10-31: Done. Verified against the running stack, online and offline.

- **Row counts:** silver/currents holds 14,884,052 grid vectors (29,768,104 u/v values, so the ticket's "~29M" counts u and v separately) over 734 days, 2024-09-01..2026-09-18. SCUD skips some days. gold/climatology has 243,336 rows; gold/convergence has 1,247 1° cells, 312 of them hotspots. The full ETL takes about 1m45s in `local[2]`.
- **Validation (saved in gold/hotspot_validation and gold/exports/hotspots.json):** of 2,310 `pieces/m3` samples, 576 fall in hotspot cells and 1,707 in the rest; 27 fall outside analysed cells. The median concentration is 0.0516 in hotspot cells vs 0.0132 elsewhere, **3.90×**. The ratio of means is only 1.15×, because the tails dominate it. ADR-0006 fixes the rules; they were set before the full-history result.
- **Network off:** with both API hosts pointed at 127.0.0.1 (`--add-host`), the fetchers fell back to `data/cache`, wrote `source=cache` plus the original `fetched_at` to `data_sources`, and re-uploaded bronze. The ETL then produced identical numbers. An online re-run fetches only the open month, about 12 s; the first full download took about 25 min (~1 min/month from the PacIOOS mirror ERDDAP redirects to).
- 26 new tests: 14 fetcher (py image), 12 Spark fixture tests (convergence on analytic fields, cell ranking, validation ratio, NetCDF → silver, grid export).

Decisions (see ADR-0006):
- The mission window is cut from the history in the ETL, not fetched separately: the last 45 SCUD days in the mission box, 2026-08-02..2026-09-18, a (45, 40, 60) cube with 0 NaN.
- Lake keys use `bronze/`, `silver/`, `gold/` (constants in `oceanclean_common.regions`), not `raw/`. The bronze currents have a `manifest.json` that the ETL reads, so stale months never leak in. Silver uses dynamic partition overwrite, so older dates stay.
- Cached closed months are reused without calling ERDDAP; the open month is always re-fetched. `data/cache/currents/last_day.txt` keeps the true end date for offline runs.
- Fetchers run in the py image (httpx, minio, psycopg; no NetCDF parsing, only a magic-byte check). The ETL runs in the Spark image, which already ships hadoop-aws and the AWS SDK for s3a.
- Exports: `gold/exports/mission_currents.npz` (time as epoch s, lat, lon, float32 u/v [t, lat, lon]) and `gold/exports/hotspots.json` (hotspot cells with microplastics counts and medians, plus the validation summary).

For ticket 04:
- **Sim time vs data time.** `SIM_START=2026-09-01` plus 30 days runs past the last SCUD day (2026-09-18). Routing and the simulator must map sim time onto the mission window, e.g. data time = window start + (sim time − SIM_START), clamped or looped.
- Hotspots are spread across the whole box, not one compact patch. The top-ranked cell (21.5N, 156.5W) sits beside the Hawaiian islands, where coastal effects are likely. To seed patches in the mission box, filter `hotspots.json` to `MISSION_BOX` and weight by `mp_median`.
- The mission grid's time axis is uneven: 45 SCUD days over 48 calendar days. Interpolate on the `time` values, not on index × 86400.
- `mp_median` is null for hotspot cells without samples (most of them). Weighting by it needs a fallback, e.g. a base weight plus a bonus for measured cells.
- Say "median" when presenting the 3.9× figure; the ratio of means is 1.15×.
- `infra/postgres/init.sql` gained `data_sources`. On an existing volume, re-apply it (CLAUDE.md Commands).
- MinIO keeps replaced objects in `.minio.sys/tmp/.trash` for a while (863 MB after several runs); MinIO empties it in the background.

2026-10-31: `/code-review` since 8799894 (both axes). Fixed in a follow-up commit:
- **Stale partial month (spec).** A month cached while still open (e.g. 2026-09, data to 09-18) would have been reused forever once it closed. The open month's cache file now carries a `.open` marker, and only marker-free closed months are reused. A successful full-month fetch clears the marker. Tests cover both cases.
- `source=cache` is now also set when a re-fetch of a closed month falls back to the cache, not only the open month.
- `computed_at` from Spark `collect()` is converted to UTC explicitly (it relied on the container TZ).
- ADR-0006 now records why batch reference data is rewritten idempotently despite ADR-0001's "append-only". CLAUDE.md lists ADRs 0001..0006.

Left open (judgement calls):
- The Compose mount `../data/cache:/app/data/cache` repeats `CACHE_DIR`'s container path, like the other mount paths noted in ticket 02.
- The API endpoints (`ERDDAP`, `QUERY_URL`) are code constants, not settings.
- ERDDAP's edge snapping adds a 179.875°E column and a 45.125°N row to silver, just outside the box. They are harmless: those cells never reach 8 sub-cells.
- `currents_etl.main` is long; it only orchestrates the pure, tested functions.
- `fetch_features`/`page_params` take a `box` parameter, but every caller passes `HISTORY_BOX`.
