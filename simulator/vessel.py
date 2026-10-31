"""Vessel kinematics on a sphere (small-step equirectangular approximation)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from geo import EARTH_R_M, wrap_lon

FUEL_TANK_L = 12_000.0


def step_position(
    lat: float,
    lon: float,
    heading_deg: float,
    speed_ms: float,
    dt_s: float,
    u_ms: float = 0.0,
    v_ms: float = 0.0,
) -> tuple[float, float]:
    """Move by thrust along heading plus water current (u east, v north) for dt seconds."""
    h = math.radians(heading_deg)
    east = speed_ms * math.sin(h) + u_ms
    north = speed_ms * math.cos(h) + v_ms
    dlat = math.degrees(north * dt_s / EARTH_R_M)
    dlon = math.degrees(east * dt_s / (EARTH_R_M * math.cos(math.radians(lat))))
    return lat + dlat, wrap_lon(lon + dlon)


@dataclass
class VesselState:
    vessel_id: str
    lat: float
    lon: float
    heading_deg: float
    speed_kn: float
    battery_pct: float = 100.0
    fuel_l: float = FUEL_TANK_L
    hold_fill_pct: float = 0.0
    debris_density: float = 0.0
    seq: int = 0
