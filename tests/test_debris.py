import random

import pytest
from debris import (
    Patch,
    collect,
    debris_density,
    drift_patches,
    hotspot_weight,
    seed_patches,
)
from energy import COLLECT_RATE_KG_H
from fields import T0, uniform
from geo import displacement, offset
from oceanclean_common.regions import MISSION_BOX

HOTSPOTS = [
    {"lat": 35.5, "lon": -139.5, "mp_median": 4.0},
    {"lat": 33.5, "lon": -141.5, "mp_median": None},
    {"lat": 21.5, "lon": -156.5, "mp_median": 9.0},  # outside the mission box
]


def test_hotspot_weight_has_a_base_and_a_capped_bonus_for_measured_cells() -> None:
    assert hotspot_weight(None, 2.0) == 1.0
    assert hotspot_weight(2.0, 2.0) == 2.0
    assert hotspot_weight(100.0, 2.0) == 4.0


def test_patches_are_seeded_only_in_mission_box_hotspot_cells() -> None:
    patches = seed_patches(HOTSPOTS, MISSION_BOX, 200, random.Random(1))
    assert len({p.patch_id for p in patches}) == 200
    cells = {(round(p.lat - 0.5) + 0.5, round(p.lon - 0.5) + 0.5) for p in patches}
    assert cells <= {(35.5, -139.5), (33.5, -141.5)}
    measured = sum(1 for p in patches if p.lat > 35)
    assert measured > 110  # weight 2 vs 1: about two thirds
    assert all(p.mass_kg > 0 for p in patches)


def test_seeding_without_mission_hotspots_fails_loudly() -> None:
    with pytest.raises(ValueError):
        seed_patches(HOTSPOTS[2:], MISSION_BOX, 5, random.Random(1))


def test_patches_drift_with_the_current_plus_bounded_windage() -> None:
    p = Patch("P01", 35.0, -142.0, 1000.0)
    gone = Patch("P02", 35.0, -142.0, 0.0)
    f = uniform(0.2, 0.0)
    rng = random.Random(3)
    for k in range(24 * 60):
        drift_patches([p, gone], f, T0 + 60 * k, 60, rng)
    east, north = displacement(35.0, -142.0, p.lat, p.lon)
    assert east == pytest.approx(0.2 * 86400, abs=6000)  # windage: a few km a day at most
    assert abs(north) < 6000
    assert (east, north) != pytest.approx((0.2 * 86400, 0.0), abs=1.0)
    assert (gone.lat, gone.lon) == (35.0, -142.0)


def test_collect_takes_from_the_patch_the_vessel_is_inside_up_to_hold_room() -> None:
    p = Patch("P01", 35.0, -142.0, 1000.0)
    lat, lon = offset(35.0, -142.0, 1500.0, 0.0)
    kg = collect([p], lat, lon, 3600, room_kg=1e9)
    assert kg == pytest.approx(min(COLLECT_RATE_KG_H, 1000.0))
    assert p.mass_kg == 0.0
    q = Patch("P02", 35.0, -142.0, 5000.0)
    assert collect([q], 35.0, -142.0, 3600, room_kg=100.0) == 100.0
    far = offset(35.0, -142.0, 2500.0, 0.0)
    assert collect([q], *far, 3600, room_kg=1e9) == 0.0


def test_debris_density_peaks_at_a_patch_and_ignores_collected_ones() -> None:
    p = Patch("P01", 35.0, -142.0, 4000.0)
    centre = debris_density([p], 35.0, -142.0)
    assert centre > debris_density([p], *offset(35.0, -142.0, 2000.0, 0.0)) > 0
    assert debris_density([p], *offset(35.0, -142.0, 20_000.0, 0.0)) == 0.0
    assert debris_density([Patch("P02", 35.0, -142.0, 0.0)], 35.0, -142.0) == 0.0
