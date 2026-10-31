"""Synthetic current fields on a mission-like 1/4-degree grid, for routing and simulator tests."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone

import numpy as np
from currents import CurrentField
from geo import displacement

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()
DATA_T0 = datetime(2026, 8, 2, tzinfo=timezone.utc).timestamp()
LAT = np.arange(30.0, 40.01, 0.25)
LON = np.arange(-150.0, -134.99, 0.25)
CENTER = (35.0, -142.0)


def field_of(fn: Callable[[float, float], tuple[float, float]], days: int = 3) -> CurrentField:
    """Steady field from fn(lat, lon) -> (u, v), sampled on the grid for `days` daily steps."""
    u = np.zeros((days, len(LAT), len(LON)))
    v = np.zeros_like(u)
    for i, la in enumerate(LAT):
        for j, lo in enumerate(LON):
            u[:, i, j], v[:, i, j] = fn(la, lo)
    time = DATA_T0 + 86400.0 * np.arange(days)
    return CurrentField.from_arrays(time, LAT, LON, u, v, T0)


def uniform(u: float, v: float) -> CurrentField:
    return field_of(lambda _la, _lo: (u, v))


def rotational(omega: float) -> CurrentField:
    """Solid-body rotation about CENTER, counter-clockwise for omega > 0 (rad/s)."""

    def fn(la: float, lo: float) -> tuple[float, float]:
        x, y = displacement(*CENTER, la, lo)
        return -omega * y, omega * x

    return field_of(fn)


def still() -> CurrentField:
    return uniform(0.0, 0.0)


def angle_deg(lat: float, lon: float) -> float:
    x, y = displacement(*CENTER, lat, lon)
    return math.degrees(math.atan2(y, x))
