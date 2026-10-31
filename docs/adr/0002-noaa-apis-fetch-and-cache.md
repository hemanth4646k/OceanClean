# 0002 NOAA APIs with fetch-and-cache fallback

Status: accepted, 2026-10-31

Ocean currents: NOAA/PacIOOS SCUD (`scud_pac`) via ERDDAP griddap at upwell.pfeg.noaa.gov, NetCDF, daily ¼° u/v, no account. It is built for marine-debris trajectories. Copernicus was rejected because it needs an account. Debris observations: NOAA NCEI Marine Microplastics ArcGIS FeatureServer (no account, 2,315 open-ocean samples in the gyre box). Marine Debris Tracker was rejected because its data is mostly shoreline and has no usable API.

The demo must survive without internet, so every fetch tries the API, writes raw responses to bronze and a local cache, and falls back to the cache on failure. The source and fetch time are recorded and shown in the UI.
