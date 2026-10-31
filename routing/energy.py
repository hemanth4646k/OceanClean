"""Vessel power and fuel, after ShipNetSim's resistance -> power -> fuel chain, simplified.

Calm-water resistance R = 1/2 rho C_T S v^2 gives effective power R v; dividing by the overall
propulsive efficiency gives brake power, so propulsion is P(v) = k v^3. A hotel load is always on.
Fuel is brake energy times the engine's specific fuel consumption. Constants describe a ~40 m
cleanup catamaran; they are plausible, not calibrated.
"""

from __future__ import annotations

from geo import KN_TO_MS

RHO_SEAWATER = 1025.0  # kg/m3
WETTED_AREA_M2 = 420.0
C_TOTAL = 0.0045  # total resistance coefficient
ETA_PROPULSIVE = 0.6  # hull x propeller x shaft
HOTEL_KW = 15.0
COLLECTOR_KW = 20.0  # booms and conveyor while collecting
SFC_G_PER_KWH = 215.0
DIESEL_KG_PER_L = 0.84
KWH_PER_L = DIESEL_KG_PER_L * 1000.0 / SFC_G_PER_KWH  # brake energy per litre burned
BATTERY_KWH = 300.0

CRUISE_KN = 6.0
COLLECT_KN = 2.0
LOITER_KN = 1.5
CRUISE_MS = CRUISE_KN * KN_TO_MS
COLLECT_RATE_KG_H = 2500.0
HOLD_CAPACITY_KG = 25_000.0


def propulsion_kw(speed_ms: float) -> float:
    resistance_n = 0.5 * RHO_SEAWATER * C_TOTAL * WETTED_AREA_M2 * speed_ms**2
    return resistance_n * speed_ms / ETA_PROPULSIVE / 1000.0


def transit_kw() -> float:
    return propulsion_kw(CRUISE_MS) + HOTEL_KW


def collect_kw() -> float:
    return propulsion_kw(COLLECT_KN * KN_TO_MS) + HOTEL_KW + COLLECTOR_KW


def fuel_l(power_kw: float, dt_s: float) -> float:
    return power_kw * dt_s / 3600.0 * SFC_G_PER_KWH / 1000.0 / DIESEL_KG_PER_L


def dwell_s(mass_kg: float) -> float:
    """Time to sweep up a patch."""
    return mass_kg / COLLECT_RATE_KG_H * 3600.0


def leg_energy_kwh(transit_s: float, dwell: float) -> float:
    """Energy of one chain leg: cruise to the intercept, then collect."""
    return (transit_kw() * transit_s + collect_kw() * dwell) / 3600.0
