"""Lagrangian Particle Drift and Vector Advection Engine for Ocean Plastic Debris."""

import logging
import math
from typing import Any

import h3

from src.clients.open_meteo import MarineWeatherForecast, open_meteo_client

logger = logging.getLogger(__name__)

EARTH_RADIUS_METERS = 6371000.0  # WGS84 mean earth radius
WINDAGE_DRIFT_FACTOR = 0.02       # 2% leeway windage for surface plastics


def advect_point(
    lat: float,
    lon: float,
    u_ms: float,
    v_ms: float,
    dt_seconds: float,
) -> tuple[float, float]:
    """Integrates spherical position forward in time given eastward (u) and northward (v) velocities."""
    lat_rad = math.radians(lat)
    cos_lat = math.cos(lat_rad)
    # Avoid division by zero near poles
    if abs(cos_lat) < 1e-7:
        cos_lat = 1e-7 if cos_lat >= 0 else -1e-7

    d_lat_deg = (v_ms * dt_seconds / EARTH_RADIUS_METERS) * (180.0 / math.pi)
    d_lon_deg = (u_ms * dt_seconds / (EARTH_RADIUS_METERS * cos_lat)) * (180.0 / math.pi)

    new_lat = lat + d_lat_deg
    new_lon = lon + d_lon_deg

    # Normalize longitude to [-180, 180]
    new_lon = ((new_lon + 180.0) % 360.0) - 180.0
    # Clamp latitude to [-89.9, 89.9]
    new_lat = max(-89.9, min(89.9, new_lat))

    return new_lat, new_lon


def calculate_uv_components(
    velocity_ms: float,
    direction_deg: float,
) -> tuple[float, float]:
    """Converts oceanographic current velocity and direction to Cartesian components.
    
    Marine standard: direction is the angle towards which the current is flowing,
    where 0 deg = North, 90 deg = East, 180 deg = South, 270 deg = West.
    """
    rad = math.radians(direction_deg)
    u = velocity_ms * math.sin(rad)  # Eastward velocity
    v = velocity_ms * math.cos(rad)  # Northward velocity
    return u, v


def simulate_constant_current_drift(
    lat: float,
    lon: float,
    velocity_ms: float,
    direction_deg: float,
    hours: float,
) -> dict[str, Any]:
    """Projects drift under constant velocity vector across specified hours."""
    dt_sec = hours * 3600.0
    u, v = calculate_uv_components(velocity_ms, direction_deg)
    new_lat, new_lon = advect_point(lat, lon, u, v, dt_sec)
    new_h3 = h3.latlng_to_cell(new_lat, new_lon, 7)

    return {
        "horizon_hours": hours,
        "predicted_lat": round(new_lat, 6),
        "predicted_lon": round(new_lon, 6),
        "h3_index": new_h3,
        "current_velocity_ms": velocity_ms,
        "current_direction_deg": direction_deg,
    }


class LagrangianDriftEngine:
    def __init__(self, meteo_client=None):
        self.meteo_client = meteo_client or open_meteo_client

    async def predict_patch_drift(
        self,
        lat: float,
        lon: float,
        horizons_hours: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Predicts patch drift across multiple time horizons using Open-Meteo hourly vectors."""
        if horizons_hours is None:
            horizons_hours = [6, 12, 24]
        forecast: MarineWeatherForecast = await self.meteo_client.get_marine_forecast(lat, lon)
        
        max_horizon = max(horizons_hours) if horizons_hours else 24
        hourly_vels = forecast.hourly_velocities
        hourly_dirs = forecast.hourly_directions

        # Step-by-step integration hour by hour
        current_lat, current_lon = lat, lon
        predictions: list[dict[str, Any]] = []

        total_available_hours = min(len(hourly_vels), len(hourly_dirs))
        
        # Track coordinates at each target horizon
        for h in range(1, max_horizon + 1):
            idx = min(h - 1, total_available_hours - 1) if total_available_hours > 0 else 0
            v_curr = hourly_vels[idx] if total_available_hours > 0 else forecast.current_velocity_ms
            d_curr = hourly_dirs[idx] if total_available_hours > 0 else forecast.current_direction_deg

            u, v = calculate_uv_components(v_curr, d_curr)
            # 1-hour time step
            current_lat, current_lon = advect_point(current_lat, current_lon, u, v, 3600.0)

            if h in horizons_hours:
                h3_cell = h3.latlng_to_cell(current_lat, current_lon, 7)
                predictions.append({
                    "horizon_hours": h,
                    "predicted_lat": round(current_lat, 6),
                    "predicted_lon": round(current_lon, 6),
                    "h3_index": h3_cell,
                    "current_velocity_ms": v_curr,
                    "current_direction_deg": d_curr,
                })

        return predictions


lagrangian_engine = LagrangianDriftEngine()
