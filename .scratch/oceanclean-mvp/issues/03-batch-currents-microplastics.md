# 03 (M2) Batch: currents + microplastics → lake → hotspots
Status: open
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
