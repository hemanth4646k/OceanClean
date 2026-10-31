"""Moving-target intercept for a current-aided vessel (SRS 3.3, ADR-0004).

The vessel's ground velocity is the water velocity plus its thrust vector at cruise speed. A
target point p(t) is reachable at time t when the water-frame distance (ground displacement minus
the current's drift over the leg) is at most speed * (t - t0). The intercept is the earliest such
t in [t0, t0 + horizon]: an hourly scan finds the first reachable step, bisection refines it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from currents import CurrentField
from geo import bearing_deg, displacement, wrap_lon

HORIZON_S = 7 * 86400.0
SCAN_S = 3600.0
TOL_S = 30.0
PATH_SAMPLES = 5  # current samples along the leg used to estimate its mean drift

Position = tuple[float, float]


@dataclass(frozen=True)
class Intercept:
    t: float  # sim epoch seconds
    lat: float
    lon: float
    heading_deg: float  # thrust heading that makes good the straight track to the point


def water_vector(
    field: CurrentField, t0: float, start: Position, t: float, end: Position
) -> tuple[float, float]:
    """East/north metres the vessel must cover through the water to be at `end` at time t.

    The current's drift is its mean over a few points along the straight leg, each sampled at the
    time the vessel passes it; exact for a uniform steady current.
    """
    east, north = displacement(*start, *end)
    dt = t - t0
    if dt <= 0:
        return east, north
    dlon = wrap_lon(end[1] - start[1])
    su = sv = 0.0
    for k in range(PATH_SAMPLES):
        f = (k + 0.5) / PATH_SAMPLES
        u, v = field.uv(t0 + f * dt, start[0] + f * (end[0] - start[0]), start[1] + f * dlon)
        su += u
        sv += v
    return east - su / PATH_SAMPLES * dt, north - sv / PATH_SAMPLES * dt


def reachable(
    field: CurrentField, t0: float, start: Position, speed_ms: float, t: float, end: Position
) -> bool:
    east, north = water_vector(field, t0, start, t, end)
    return math.hypot(east, north) <= speed_ms * (t - t0)


def intercept(
    field: CurrentField,
    t0: float,
    start: Position,
    speed_ms: float,
    target: Callable[[float], Position],
    horizon_s: float = HORIZON_S,
) -> Intercept | None:
    """Earliest meeting with a moving target, or None if it cannot be reached within the horizon."""

    def ok(t: float) -> bool:
        return reachable(field, t0, start, speed_ms, t, target(t))

    lo, hi = t0, None
    t = t0
    while t < t0 + horizon_s:
        t = min(t + SCAN_S, t0 + horizon_s)
        if ok(t):
            hi = t
            break
        lo = t
    if hi is None:
        return None
    while hi - lo > TOL_S:
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    end = target(hi)
    east, north = water_vector(field, t0, start, hi, end)
    return Intercept(hi, end[0], end[1], bearing_deg(east, north))


def steer_heading(bearing: float, speed_ms: float, u: float, v: float) -> float:
    """Heading whose thrust plus the current makes good the given ground bearing (crab angle).

    When the cross-current exceeds the vessel's speed no heading holds the track; point at it.
    """
    b = math.radians(bearing)
    cross = u * math.cos(b) - v * math.sin(b)  # current component to the right of the track
    if speed_ms <= 0 or abs(cross) >= speed_ms:
        return bearing % 360.0
    return (bearing - math.degrees(math.asin(cross / speed_ms))) % 360.0
