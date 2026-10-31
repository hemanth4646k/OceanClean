"""Energy per 5-minute window and the z-score fuel-burn anomaly (M5). Pure; no Spark.

The watermarked window query (ADR-0005) gives, per vessel and window, the state at the window's
last tick plus sums the power model needs. Energy used is measured from the previous window's
last tick: fuel burned (as brake energy) plus battery drawn. That equals the load the power
model predicts from speed and mode, so the relative residual is ~0 in normal running, and a
fuel leak (more fuel for the same power) stands out. Its z-score against recent residuals
raises an alert at onset.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from energy import BATTERY_KWH, COLLECTOR_KW, HOLD_CAPACITY_KG, HOTEL_KW, KWH_PER_L, propulsion_kw

HISTORY_N = 48  # recent normal windows (4 sim-hours) the z-score compares against
MIN_HISTORY = 6
STD_FLOOR = 0.02  # the simulator is noiseless; a floor keeps z finite and meaningful
Z_MIN = 4.0
REL_MIN = 0.2  # and at least 20 % more energy than the model: battery clamping adds up to ~8 %
K_V3 = propulsion_kw(1.0)  # propulsion kW = K_V3 * v^3 (v in m/s)


@dataclass(frozen=True)
class WindowAgg:
    """One closed event-time window from Spark: state at its last tick plus power-model sums."""

    vessel_id: str
    window_end: datetime
    last_ts: datetime
    n: int
    fuel_l: float
    battery_pct: float
    hold_fill_pct: float
    sum_v3: float  # sum of speed^3 (m/s) over the window's ticks
    n_collect: int  # ticks at collection speed (collector running)


@dataclass(frozen=True)
class Tail:
    """The previous window's last tick: where this window's measurement starts."""

    last_ts: datetime
    fuel_l: float
    battery_pct: float
    hold_fill_pct: float
    anomaly: bool


@dataclass(frozen=True)
class Scored:
    agg: WindowAgg
    energy_kwh: float
    expected_kwh: float
    collected_kg: float
    residual: float | None  # (measured - expected) / expected; None when not comparable
    z: float | None
    anomaly: bool
    onset: bool  # first anomalous window of a run: raise one alert


def expected_kwh(sum_v3: float, n: int, n_collect: int, tick_s: float) -> float:
    """Load the power model predicts over n ticks: propulsion + hotel, + collector if collecting."""
    return (K_V3 * sum_v3 + HOTEL_KW * n + COLLECTOR_KW * n_collect) * tick_s / 3600.0


def score(
    tail: Tail | None, windows: Sequence[WindowAgg], history: Sequence[float], tick_s: float
) -> list[Scored]:
    """Score one vessel's newly closed windows in event-time order, chaining from `tail`."""
    hist = list(history)[-HISTORY_N:]
    out = []
    for w in windows:
        expected = expected_kwh(w.sum_v3, w.n, w.n_collect, tick_s)
        if tail is None or w.last_ts <= tail.last_ts:  # no baseline, or the sim was reset
            out.append(Scored(w, 0.0, expected, 0.0, None, None, False, False))
        else:
            out.append(_measure(tail, w, expected, hist, tick_s))
            if out[-1].residual is not None and not out[-1].anomaly:
                hist = [*hist, out[-1].residual][-HISTORY_N:]
        s = out[-1]
        tail = Tail(w.last_ts, w.fuel_l, w.battery_pct, w.hold_fill_pct, s.anomaly)
    return out


def _measure(tail: Tail, w: WindowAgg, expected: float, hist: list[float], tick_s: float) -> Scored:
    burned = tail.fuel_l - w.fuel_l
    refuelled = burned < 0  # tank refilled at an offload: the fuel delta is not consumption
    energy = max(0.0, burned) * KWH_PER_L + (tail.battery_pct - w.battery_pct) / 100 * BATTERY_KWH
    collected = max(0.0, w.hold_fill_pct - tail.hold_fill_pct) / 100 * HOLD_CAPACITY_KG
    ticks = round((w.last_ts - tail.last_ts).total_seconds() / tick_s)
    dry = w.fuel_l <= 0  # adrift on an empty tank: the sim clamps fuel, so the load is unmeasured
    if refuelled or dry or ticks != w.n or expected <= 0:  # measured, not scored
        return Scored(w, max(0.0, energy), expected, collected, None, None, False, False)
    residual = (energy - expected) / expected
    z = None
    if len(hist) >= MIN_HISTORY:
        z = (residual - statistics.fmean(hist)) / max(statistics.pstdev(hist), STD_FLOOR)
    anomaly = z is not None and z >= Z_MIN and residual >= REL_MIN
    return Scored(
        w, energy, expected, collected, residual, z, anomaly, anomaly and not tail.anomaly
    )
