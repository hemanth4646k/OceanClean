"""Patch drift prediction: midpoint RK2 through the current field (dt = 1 sim-hour)."""

from __future__ import annotations

from dataclasses import dataclass

from currents import CurrentField
from geo import offset

DRIFT_DT_S = 3600.0


def rk2_step(
    field: CurrentField, t: float, lat: float, lon: float, dt: float
) -> tuple[float, float]:
    """One midpoint step: velocity at the half-step position and time moves the full step."""
    u0, v0 = field.uv(t, lat, lon)
    mlat, mlon = offset(lat, lon, u0 * dt / 2, v0 * dt / 2)
    u1, v1 = field.uv(t + dt / 2, mlat, mlon)
    return offset(lat, lon, u1 * dt, v1 * dt)


@dataclass(frozen=True)
class Track:
    """Predicted positions at t0, t0 + dt, ...; `at` interpolates and holds the ends."""

    t0: float
    dt: float
    points: tuple[tuple[float, float], ...]

    @property
    def t_end(self) -> float:
        return self.t0 + self.dt * (len(self.points) - 1)

    def at(self, t: float) -> tuple[float, float]:
        f = min(max((t - self.t0) / self.dt, 0.0), len(self.points) - 1.0)
        i = min(int(f), len(self.points) - 2) if len(self.points) > 1 else 0
        if len(self.points) == 1:
            return self.points[0]
        w = f - i
        (a_lat, a_lon), (b_lat, b_lon) = self.points[i], self.points[i + 1]
        return a_lat + (b_lat - a_lat) * w, a_lon + (b_lon - a_lon) * w


def predict_track(
    field: CurrentField, t0: float, lat: float, lon: float, until: float, dt: float = DRIFT_DT_S
) -> Track:
    points = [(lat, lon)]
    t = t0
    while t < until:
        lat, lon = rk2_step(field, t, lat, lon, dt)
        points.append((lat, lon))
        t += dt
    return Track(t0, dt, tuple(points))
