"""Small-distance geometry on the sphere: local east/north metres, great-circle distance."""

from __future__ import annotations

import math

EARTH_R_M = 6_371_000.0
KN_TO_MS = 0.514444


def wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def offset(lat: float, lon: float, east_m: float, north_m: float) -> tuple[float, float]:
    """Point reached by moving east/north metres from (lat, lon) (equirectangular step)."""
    dlat = math.degrees(north_m / EARTH_R_M)
    dlon = math.degrees(east_m / (EARTH_R_M * math.cos(math.radians(lat + dlat / 2))))
    return lat + dlat, wrap_lon(lon + dlon)


def displacement(lat0: float, lon0: float, lat1: float, lon1: float) -> tuple[float, float]:
    """East/north metres from point 0 to point 1 in the tangent plane at their mean latitude."""
    dlon = wrap_lon(lon1 - lon0)
    east = math.radians(dlon) * EARTH_R_M * math.cos(math.radians((lat0 + lat1) / 2))
    return east, math.radians(lat1 - lat0) * EARTH_R_M


def distance_m(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    """Haversine great-circle distance."""
    p0, p1 = math.radians(lat0), math.radians(lat1)
    dp, dl = p1 - p0, math.radians(lon1 - lon0)
    a = math.sin(dp / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(east: float, north: float) -> float:
    """Compass bearing (0 = north, 90 = east) of an east/north vector."""
    return math.degrees(math.atan2(east, north)) % 360.0
