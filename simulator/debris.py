"""Debris world: patches seeded on mission-box hotspots, drifting with currents plus windage.

Windage (leeway) is a slow random wind-driven drift the routing layer does not model, so real
patches wander off their predicted tracks and the 2 km recalc gate has something to catch.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from currents import CurrentField
from drift import rk2_step
from energy import COLLECT_RATE_KG_H
from geo import distance_m, offset
from oceanclean_common.regions import Box

PATCH_RADIUS_M = 2000.0
PATCH_MASS_KG = 3500.0  # median patch mass before the hotspot weighting
WINDAGE_SD_MS = 0.03  # spread of the wind-driven drift
WINDAGE_TAU_S = 12 * 3600.0  # how long a windage velocity persists
MEASURED_BONUS_CAP = 3.0


@dataclass
class Patch:
    patch_id: str
    lat: float
    lon: float
    mass_kg: float
    radius_m: float = PATCH_RADIUS_M
    wind_e: float = 0.0
    wind_n: float = 0.0


def hotspot_weight(mp_median: float | None, reference: float) -> float:
    """Base weight 1 for every hotspot, plus a capped bonus where microplastics were measured."""
    if mp_median is None or reference <= 0:
        return 1.0
    return 1.0 + min(mp_median / reference, MEASURED_BONUS_CAP)


def seed_patches(
    hotspots: Iterable[Mapping[str, object]], box: Box, n: int, rng: random.Random
) -> list[Patch]:
    """n patches in mission-box hotspot cells (1 degree, centre lat/lon), weighted by mp_median."""
    cells = [h for h in hotspots if box.contains(float(h["lat"]), float(h["lon"]))]
    if not cells:
        raise ValueError("no hotspot cells inside the mission box; run the batch ETL")
    medians = [None if h.get("mp_median") is None else float(h["mp_median"]) for h in cells]
    measured = [m for m in medians if m is not None]
    ref = statistics.median(measured) if measured else 0.0
    weights = [hotspot_weight(m, ref) for m in medians]
    pairs = list(zip(cells, weights, strict=True))
    patches = []
    for k in range(n):
        cell, w = rng.choices(pairs, weights)[0]
        lat = float(cell["lat"]) + rng.uniform(-0.5, 0.5)
        lon = float(cell["lon"]) + rng.uniform(-0.5, 0.5)
        mass = PATCH_MASS_KG * math.sqrt(w) * rng.lognormvariate(0.0, 0.4)
        patches.append(Patch(f"P{k + 1:02d}", lat, lon, round(mass, 1)))
    return patches


def drift_patches(
    patches: Iterable[Patch], field: CurrentField, t: float, dt: float, rng: random.Random
) -> None:
    """Advance live patches one tick: RK2 through the currents, then the windage offset."""
    a = math.exp(-dt / WINDAGE_TAU_S)
    kick = WINDAGE_SD_MS * math.sqrt(1 - a * a)
    for p in patches:
        if p.mass_kg <= 0:
            continue
        p.wind_e = a * p.wind_e + kick * rng.gauss(0.0, 1.0)
        p.wind_n = a * p.wind_n + kick * rng.gauss(0.0, 1.0)
        lat, lon = rk2_step(field, t, p.lat, p.lon, dt)
        p.lat, p.lon = offset(lat, lon, p.wind_e * dt, p.wind_n * dt)


def collect(patches: Iterable[Patch], lat: float, lon: float, dt: float, room_kg: float) -> float:
    """Sweep the nearest live patch the vessel is inside; returns kg taken into the hold."""
    inside = [(distance_m(lat, lon, p.lat, p.lon), p) for p in patches if p.mass_kg > 0]
    inside = [(d, p) for d, p in inside if d <= p.radius_m]
    if not inside or room_kg <= 0:
        return 0.0
    _, p = min(inside, key=lambda dp: dp[0])
    kg = min(COLLECT_RATE_KG_H * dt / 3600.0, p.mass_kg, room_kg)
    p.mass_kg = 0.0 if p.mass_kg - kg < 1.0 else p.mass_kg - kg
    return kg


def debris_density(patches: Iterable[Patch], lat: float, lon: float) -> float:
    """Surface debris in g/m2 at the vessel: each patch's mean density with a Gaussian falloff."""
    total = 0.0
    for p in patches:
        if p.mass_kg <= 0:
            continue
        d = distance_m(lat, lon, p.lat, p.lon)
        if d < 4 * p.radius_m:
            mean = p.mass_kg * 1000.0 / (math.pi * p.radius_m**2)
            total += mean * math.exp(-0.5 * (d / p.radius_m) ** 2)
    return total
