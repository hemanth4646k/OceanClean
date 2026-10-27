"""Ocean Current Vector Field Grid Generator for WebGL Particle Streamlines."""

import logging
from typing import Any

from src.clients.open_meteo import open_meteo_client
from src.drift.lagrangian import calculate_uv_components

logger = logging.getLogger(__name__)


async def generate_currents_grid(
    min_lat: float = 26.0,
    max_lat: float = 36.0,
    min_lon: float = -152.0,
    max_lon: float = -136.0,
    step_deg: float = 1.5,
) -> list[dict[str, Any]]:
    """Generates a regular grid of ocean current velocity vectors across the Gyre bounding box."""
    grid_points: list[dict[str, Any]] = []

    lat_steps = int((max_lat - min_lat) / step_deg) + 1
    lon_steps = int((max_lon - min_lon) / step_deg) + 1

    for i in range(lat_steps):
        lat = round(min_lat + i * step_deg, 2)
        for j in range(lon_steps):
            lon = round(min_lon + j * step_deg, 2)

            forecast = await open_meteo_client.get_marine_forecast(lat, lon)
            v_ms = forecast.current_velocity_ms
            d_deg = forecast.current_direction_deg
            wave_m = forecast.wave_height_m

            u_ms, v_ms = calculate_uv_components(v_ms, d_deg)

            grid_points.append({
                "lat": lat,
                "lon": lon,
                "u_ms": round(u_ms, 3),
                "v_ms": round(v_ms, 3),
                "velocity_ms": round(v_ms, 2),
                "direction_deg": round(d_deg, 1),
                "wave_height_m": round(wave_m, 2),
            })

    return grid_points
