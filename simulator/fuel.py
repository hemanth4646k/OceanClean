"""Fuel and battery bookkeeping on top of routing's power model (energy.py).

Diesel-electric with a battery: underway the engine covers propulsion, hotel and battery charging;
loitering or alongside for offload the engine is off and the battery carries the load down to a
reserve, below which the engine starts again.
"""

from __future__ import annotations

from energy import BATTERY_KWH, COLLECTOR_KW, HOTEL_KW, fuel_l, propulsion_kw
from vessel import VesselState

CHARGE_KW = 25.0
RESERVE_PCT = 20.0
ELECTRIC_MODES = frozenset({"loiter", "offload"})


def power_split(mode: str, speed_ms: float, battery_pct: float) -> tuple[float, float]:
    """(engine kW, battery kW) for one mode; battery kW < 0 is charging."""
    load = propulsion_kw(speed_ms) + HOTEL_KW + (COLLECTOR_KW if mode == "collect" else 0.0)
    if mode in ELECTRIC_MODES and battery_pct > RESERVE_PCT:
        return 0.0, load
    charge = CHARGE_KW if battery_pct < 100.0 else 0.0
    return load + charge, -charge


def burn(v: VesselState, mode: str, speed_ms: float, dt: float, fuel_factor: float = 1.0) -> None:
    """fuel_factor > 1 is an injected fuel leak: more fuel lost for the same power (M5 demo)."""
    engine_kw, battery_kw = power_split(mode, speed_ms, v.battery_pct)
    v.fuel_l = max(0.0, v.fuel_l - fuel_l(engine_kw, dt) * fuel_factor)
    pct = v.battery_pct - battery_kw * dt / 3600.0 / BATTERY_KWH * 100.0
    v.battery_pct = min(100.0, max(0.0, pct))
