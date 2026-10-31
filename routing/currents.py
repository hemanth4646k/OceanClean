"""Surface-current field: bilinear in space, linear in time, on the exported mission grid.

Routing and the simulator both work in sim time (ADR-0003, epoch seconds). The mission window is
real SCUD data that ends before a 30-day sim run does, so sim time is mapped onto data time as
window start + (sim time - SIM_START), looped over the window.
"""

from __future__ import annotations

import io
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class CurrentField:
    time: tuple[float, ...]  # data epoch seconds, ascending; SCUD skips days, so uneven
    lat: np.ndarray  # ascending, regular spacing
    lon: np.ndarray  # ascending, regular spacing, -180..180
    u: np.ndarray  # [time, lat, lon] m/s east; gaps are 0
    v: np.ndarray  # [time, lat, lon] m/s north
    sim_start: float  # sim epoch seconds that maps onto time[0]

    @classmethod
    def from_arrays(
        cls,
        time: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        sim_start: float,
    ) -> CurrentField:
        clean = (np.nan_to_num(np.asarray(a, dtype=np.float64)) for a in (u, v))
        return cls(
            tuple(float(t) for t in time),
            np.asarray(lat, dtype=np.float64),
            np.asarray(lon, dtype=np.float64),
            *clean,
            float(sim_start),
        )

    @classmethod
    def from_npz(cls, data: bytes, sim_start: datetime) -> CurrentField:
        """The batch layer's gold/exports/mission_currents.npz."""
        z = np.load(io.BytesIO(data))
        return cls.from_arrays(z["time"], z["lat"], z["lon"], z["u"], z["v"], sim_start.timestamp())

    def data_time(self, t: float) -> float:
        span = self.time[-1] - self.time[0]
        if span <= 0:
            return self.time[0]
        return self.time[0] + (t - self.sim_start) % span

    def _bracket(self, t: float) -> tuple[int, int, float]:
        """Time steps k, k1 around sim time t and the weight of k1."""
        td = self.data_time(t)
        k = min(max(bisect_right(self.time, td) - 1, 0), len(self.time) - 1)
        k1 = min(k + 1, len(self.time) - 1)
        wt = 0.0 if k1 == k else (td - self.time[k]) / (self.time[k1] - self.time[k])
        return k, k1, wt

    def grid_at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """The whole (u, v) grid [lat, lon] at sim time t, for drawing current particles."""
        k, k1, wt = self._bracket(t)
        u = self.u[k] + (self.u[k1] - self.u[k]) * wt
        v = self.v[k] + (self.v[k1] - self.v[k]) * wt
        return u, v

    def uv(self, t: float, lat: float, lon: float) -> tuple[float, float]:
        """Current (u east, v north) in m/s at sim time t; positions off the grid use its edge."""
        k, k1, wt = self._bracket(t)
        i, wi = _cell(self.lat, lat)
        j, wj = _cell(self.lon, lon)
        out = []
        for g in (self.u, self.v):
            a = _bilinear(g[k], i, j, wi, wj)
            b = a if k1 == k else _bilinear(g[k1], i, j, wi, wj)
            out.append(a + (b - a) * wt)
        return out[0], out[1]


def _cell(axis: np.ndarray, x: float) -> tuple[int, float]:
    """Lower index and weight of x on a regular axis, clamped to the axis ends."""
    n = len(axis)
    if n == 1:
        return 0, 0.0
    f = (x - axis[0]) / (axis[1] - axis[0])
    f = min(max(f, 0.0), n - 1.0)
    i = min(int(f), n - 2)
    return i, f - i


def _bilinear(g: np.ndarray, i: int, j: int, wi: float, wj: float) -> float:
    if g.shape[0] == 1:
        i, wi = 0, 0.0
    if g.shape[1] == 1:
        j, wj = 0, 0.0
    i1, j1 = min(i + 1, g.shape[0] - 1), min(j + 1, g.shape[1] - 1)
    top = g[i, j] * (1 - wj) + g[i, j1] * wj
    bot = g[i1, j] * (1 - wj) + g[i1, j1] * wj
    return float(top * (1 - wi) + bot * wi)
