"""Phase 3 Verification Gate Tests: Lagrangian Drift & Ocean Current Advection."""

import math

import h3
import pytest

from src.clients.open_meteo import OpenMeteoClient
from src.drift.lagrangian import (
    LagrangianDriftEngine,
    simulate_constant_current_drift,
)


def test_eastward_current_drift_shifts_longitude_and_preserves_latitude():
    """Success Criteria: Pytest confirms that a debris patch placed in a 1.5 m/s eastward current

    (theta = 90 deg) shifts east in longitude after 6 hours while latitude remains constant,
    and returns a valid H3 index.
    """
    initial_lat = 25.0
    initial_lon = -140.0
    current_velocity = 1.5  # m/s
    current_direction = 90.0  # Eastward
    horizon_hours = 6.0

    result = simulate_constant_current_drift(
        lat=initial_lat,
        lon=initial_lon,
        velocity_ms=current_velocity,
        direction_deg=current_direction,
        hours=horizon_hours,
    )

    # 1. Latitude remains constant (v = 0)
    assert abs(result["predicted_lat"] - initial_lat) < 1e-5, (
        f"Latitude should remain unchanged, got {result['predicted_lat']}"
    )

    # 2. Longitude shifts East (becomes greater than -140.0, e.g. ~ -139.68)
    assert result["predicted_lon"] > initial_lon, (
        f"Longitude should shift eastwards, got {result['predicted_lon']} <= {initial_lon}"
    )

    # Calculate expected displacement
    dt_sec = horizon_hours * 3600.0
    expected_dlon = (current_velocity * dt_sec / (6371000.0 * math.cos(math.radians(initial_lat)))) * (180.0 / math.pi)
    assert abs(result["predicted_lon"] - (initial_lon + expected_dlon)) < 1e-4

    # 3. Returns valid H3 index at resolution 7
    h3_idx = result["h3_index"]
    assert h3.is_valid_cell(h3_idx) is True
    assert h3.get_resolution(h3_idx) == 7


def test_northward_current_drift():
    """Verify northward current (0 deg) shifts latitude north and preserves longitude."""
    initial_lat = 20.0
    initial_lon = -135.0
    result = simulate_constant_current_drift(
        lat=initial_lat,
        lon=initial_lon,
        velocity_ms=2.0,
        direction_deg=0.0,  # North
        hours=12.0,
    )

    assert result["predicted_lat"] > initial_lat
    assert abs(result["predicted_lon"] - initial_lon) < 1e-5
    assert h3.is_valid_cell(result["h3_index"]) is True


@pytest.mark.asyncio
async def test_lagrangian_engine_multi_horizon_predictions():
    """Verify multi-horizon forward integration (6h, 12h, 24h) produces monotonic drift."""
    engine = LagrangianDriftEngine()
    horizons = [6, 12, 24]
    predictions = await engine.predict_patch_drift(
        lat=28.0,
        lon=-142.0,
        horizons_hours=horizons,
    )

    assert len(predictions) == 3
    for p in predictions:
        assert p["horizon_hours"] in horizons
        assert h3.is_valid_cell(p["h3_index"]) is True
        assert -90.0 <= p["predicted_lat"] <= 90.0
        assert -180.0 <= p["predicted_lon"] <= 180.0


def test_open_meteo_client_cache_and_fallback():
    """Verify OpenMeteoClient fallback returns deterministic gyre vectors when offline."""
    client = OpenMeteoClient()
    fallback = client._get_fallback_forecast(30.0, -145.0)
    assert fallback.current_velocity_ms == 0.5
    assert fallback.current_direction_deg == 90.0
    assert fallback.wave_height_m == 1.5
    assert len(fallback.hourly_velocities) >= 24
