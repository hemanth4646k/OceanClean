"""Operating areas and lake object keys shared by the batch layer, routing, API and simulator.

Longitudes are -180..180 everywhere; only the raw SCUD files and their ERDDAP queries use 0..360.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


# North Pacific gyre: currents history and microplastics envelope (20-45N, 180-130W).
HISTORY_BOX = Box(lat_min=20.0, lat_max=45.0, lon_min=-180.0, lon_max=-130.0)
# Where the cleaner operates (30-40N, 150-135W).
MISSION_BOX = Box(lat_min=30.0, lat_max=40.0, lon_min=-150.0, lon_max=-135.0)


def to_lon360(lon: float) -> float:
    """-180..180 -> 0..360 (SCUD's convention); -180 maps to 180 so a box stays contiguous."""
    return lon + 360.0 if lon < 0 else lon


# Lake layout on MinIO (ADR-0001): bronze = raw responses, silver = cleaned rows, gold = views.
BRONZE_CURRENTS = "bronze/currents/scud_pac"
CURRENTS_MANIFEST = f"{BRONZE_CURRENTS}/manifest.json"
BRONZE_MICROPLASTICS = "bronze/microplastics/ncei_gyre.json"
SILVER_CURRENTS = "silver/currents"
GOLD_CLIMATOLOGY = "gold/climatology"
GOLD_CONVERGENCE = "gold/convergence"
GOLD_HOTSPOT_VALIDATION = "gold/hotspot_validation"
# Small exports the API and simulator load without Spark.
EXPORT_MISSION_GRID = "gold/exports/mission_currents.npz"
EXPORT_HOTSPOTS = "gold/exports/hotspots.json"
# Speed-layer history (ADR-0005): raw ticks and surveys, append-only, partitioned by event time.
BRONZE_TELEMETRY = "bronze/telemetry"
BRONZE_DEBRIS_SURVEY = "bronze/debris_survey"
# Telemetry batch job (M5): deduplicated ticks with per-tick energy/debris, daily views, export.
SILVER_TELEMETRY = "silver/telemetry"
GOLD_TELEMETRY_DAILY = "gold/telemetry_daily"
GOLD_TELEMETRY_DAILY_ZONE = "gold/telemetry_daily_zone"
EXPORT_ANALYTICS = "gold/exports/analytics.json"
