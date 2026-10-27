"""Open-Meteo Marine API Client with H3 Resolution-5 In-Memory TTL Cache and Offline Fallback."""

import logging
import time

import h3
import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_BASE_URL = "https://marine-api.open-meteo.com/v1/marine"
CACHE_TTL_SECONDS = 1800.0  # 30 minutes


class MarineWeatherForecast:
    def __init__(
        self,
        current_velocity_ms: float,
        current_direction_deg: float,
        wave_height_m: float,
        hourly_velocities: list[float],
        hourly_directions: list[float],
        hourly_times: list[str],
        cached_at: float,
    ):
        self.current_velocity_ms = current_velocity_ms
        self.current_direction_deg = current_direction_deg
        self.wave_height_m = wave_height_m
        self.hourly_velocities = hourly_velocities
        self.hourly_directions = hourly_directions
        self.hourly_times = hourly_times
        self.cached_at = cached_at

    def is_expired(self) -> bool:
        return (time.time() - self.cached_at) > CACHE_TTL_SECONDS


class OpenMeteoClient:
    def __init__(self, timeout_sec: float = 5.0):
        self.timeout_sec = timeout_sec
        # Cache keyed by H3 resolution-5 index string
        self._cache: dict[str, MarineWeatherForecast] = {}

    def get_h3_res5_key(self, lat: float, lon: float) -> str:
        return h3.latlng_to_cell(lat, lon, 5)

    def _get_fallback_forecast(self, lat: float, lon: float) -> MarineWeatherForecast:
        """Deterministic gyre fallback when running in offline CI or if API is unreachable."""
        # Standard eastward subtropical gyre drift (0.5 m/s at 90 deg)
        hourly_v = [0.5] * 72
        hourly_d = [90.0] * 72
        hourly_t = [f"2026-10-27T{i%24:02d}:00:00Z" for i in range(72)]
        return MarineWeatherForecast(
            current_velocity_ms=0.5,
            current_direction_deg=90.0,
            wave_height_m=1.5,
            hourly_velocities=hourly_v,
            hourly_directions=hourly_d,
            hourly_times=hourly_t,
            cached_at=time.time(),
        )

    async def get_marine_forecast(
        self,
        lat: float,
        lon: float,
        client: httpx.AsyncClient | None = None,
    ) -> MarineWeatherForecast:
        cell_key = self.get_h3_res5_key(lat, lon)
        cached = self._cache.get(cell_key)
        if cached and not cached.is_expired():
            logger.debug("Cache hit for H3 cell %s (%.3f, %.3f)", cell_key, lat, lon)
            return cached

        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "current": "ocean_current_velocity,ocean_current_direction,wave_height",
            "hourly": "ocean_current_velocity,ocean_current_direction",
            "forecast_days": 3,
        }

        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_sec)
            should_close_client = True

        try:
            resp = await client.get(OPEN_METEO_BASE_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                current_block = data.get("current", {})
                hourly_block = data.get("hourly", {})

                # Open-Meteo returns ocean_current_velocity in km/h or m/s based on units
                units = data.get("current_units", {})
                vel_unit = units.get("ocean_current_velocity", "km/h")

                raw_vel = float(current_block.get("ocean_current_velocity") or 0.5)
                # Convert to m/s if in km/h
                current_vel_ms = (raw_vel / 3.6) if "km" in vel_unit else raw_vel
                current_dir = float(current_block.get("ocean_current_direction") or 90.0)
                wave_m = float(current_block.get("wave_height") or 1.5)

                raw_h_vels = hourly_block.get("ocean_current_velocity") or [raw_vel] * 24
                raw_h_dirs = hourly_block.get("ocean_current_direction") or [current_dir] * 24
                h_times = hourly_block.get("time") or []

                h_vels_ms = [
                    (float(v) / 3.6) if "km" in vel_unit else float(v)
                    for v in raw_h_vels
                ]
                h_dirs = [float(d) for d in raw_h_dirs]

                forecast = MarineWeatherForecast(
                    current_velocity_ms=current_vel_ms,
                    current_direction_deg=current_dir,
                    wave_height_m=wave_m,
                    hourly_velocities=h_vels_ms,
                    hourly_directions=h_dirs,
                    hourly_times=h_times,
                    cached_at=time.time(),
                )
                self._cache[cell_key] = forecast
                return forecast
            else:
                logger.warning(
                    "Open-Meteo API HTTP %d. Using deterministic ocean fallback.",
                    resp.status_code,
                )
                return self._get_fallback_forecast(lat, lon)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "Open-Meteo API unreachable (%s). Using deterministic ocean fallback.",
                exc,
            )
            return self._get_fallback_forecast(lat, lon)
        finally:
            if should_close_client:
                await client.aclose()


open_meteo_client = OpenMeteoClient()
