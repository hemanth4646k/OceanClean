import random

import pytest
from currents import CurrentField
from debris import Patch
from energy import (
    CRUISE_KN,
    CRUISE_MS,
    HOLD_CAPACITY_KG,
    KWH_PER_L,
    LOITER_KN,
    fuel_l,
    transit_kw,
)
from fields import T0, still, uniform
from fuel import RESERVE_PCT, burn, power_split
from geo import distance_m, offset
from link import Link
from oceanclean_common.telemetry import Telemetry
from planner import PatchObs, plan_chain, route_record
from vessel import FUEL_TANK_L, VesselState
from world import OFFLOAD_S, RouteTargets, World, steer, tick, waypoint_targets

START = (35.0, -142.0)


def vessel(**kw: float) -> VesselState:
    return VesselState("OC-01", *START, heading_deg=0.0, speed_kn=0.0, **kw)


def run(
    w: World,
    v: VesselState,
    route: RouteTargets | None,
    hours: float,
    field: CurrentField | None = None,
    t: float = T0,
) -> float:
    """Tick for `hours` from sim time t; returns the end time."""
    f = field or still()
    rng = random.Random(0)
    for _ in range(int(hours * 60)):
        tick(w, v, t, 60.0, f, route, rng)
        t += 60.0
    return t


def test_no_route_means_loiter_in_a_small_circle() -> None:
    w, v = World([]), vessel()
    run(w, v, None, 2)
    assert w.mode == "loiter" and v.speed_kn == LOITER_KN
    assert distance_m(*START, v.lat, v.lon) < 1500


def test_loiter_holds_station_against_the_current() -> None:
    w, v = World([]), vessel()
    f = uniform(0.2, -0.1)  # would carry a drifting vessel ~4.8 km in 6 h
    t = T0
    for _ in range(6):
        t = run(w, v, None, 1, f, t)
        assert distance_m(*START, v.lat, v.lon) < 1200


def test_vessel_follows_the_route_collects_and_moves_on() -> None:
    a = Patch("A", *offset(*START, 20_000, 0), 2000.0)
    b = Patch("B", *offset(*START, 20_000, 20_000), 2000.0)
    obs = [PatchObs(p.patch_id, T0, p.lat, p.lon, p.mass_kg, p.radius_m) for p in (a, b)]
    f = uniform(0.1, 0.05)
    route = waypoint_targets(route_record(plan_chain(f, T0, START, obs))["waypoints"])
    assert [r[0] for r in route] == ["A", "B"]
    w, v = World([a, b]), vessel()
    t = run(w, v, route, 1, f)
    assert w.mode == "transit" and v.speed_kn == CRUISE_KN
    run(w, v, route, 9, f, t)
    assert a.mass_kg == 0 and b.mass_kg == 0
    assert w.collected_kg == pytest.approx(4000.0)
    assert v.hold_fill_pct == pytest.approx(4000.0 / HOLD_CAPACITY_KG * 100)
    assert w.mode == "loiter"


def test_full_hold_pauses_six_hours_then_empties_and_refuels() -> None:
    p = Patch("A", *START, HOLD_CAPACITY_KG)
    w, v = World([p]), vessel(hold_fill_pct=90.0, fuel_l=500.0)
    route = [("A", *START)]
    t = run(w, v, route, 1)
    assert w.mode == "offload" and v.hold_fill_pct == 100.0
    t = run(w, v, route, OFFLOAD_S / 3600 - 1, t=t)
    assert w.mode == "offload"
    run(w, v, route, 2, t=t)  # back to collecting the rest of the patch
    assert w.mode == "collect" and v.hold_fill_pct < 20.0 and v.fuel_l > 0.9 * FUEL_TANK_L


def test_empty_tank_leaves_the_vessel_adrift() -> None:
    w, v = World([Patch("A", *offset(*START, 50_000, 0), 1000.0)]), vessel(fuel_l=0.0)
    assert steer(w, v, T0, still(), [("A", *offset(*START, 50_000, 0))])[0] == "adrift"


def test_transit_burns_fuel_at_the_power_model_rate_and_charges_the_battery() -> None:
    v = vessel(battery_pct=50.0)
    burn(v, "transit", CRUISE_MS, 3600)
    engine_kw, _ = power_split("transit", CRUISE_MS, 50.0)
    assert engine_kw > transit_kw()
    assert v.fuel_l == pytest.approx(FUEL_TANK_L - fuel_l(engine_kw, 3600))
    assert v.battery_pct > 50.0


def test_loiter_runs_on_battery_until_the_reserve() -> None:
    v = vessel(battery_pct=60.0)
    burn(v, "loiter", LOITER_KN * 0.514444, 3600)
    assert v.fuel_l == FUEL_TANK_L and v.battery_pct < 60.0
    low = vessel(battery_pct=RESERVE_PCT - 1)
    burn(low, "loiter", LOITER_KN * 0.514444, 3600)
    assert low.fuel_l < FUEL_TANK_L and low.battery_pct > RESERVE_PCT - 1


def test_world_round_trips_through_its_json_form_including_the_queue() -> None:
    e = Telemetry(
        vessel_id="OC-01",
        event_ts="2026-09-01T00:01:00Z",
        seq=1,
        lat=35.0,
        lon=-142.0,
        heading_deg=0.0,
        speed_kn=6.0,
        battery_pct=90.0,
        fuel_l=1000.0,
        debris_density=0.0,
        hold_fill_pct=0.0,
        buffered=True,
    )
    w = World(
        [Patch("A", 35.0, -142.0, 10.0, wind_e=0.01)],
        mode="collect",
        offload_until=5.0,
        next_survey=7.0,
        collected_kg=3.0,
        link=Link(9.0, [e]),
    )
    assert World.from_dict(w.to_dict()) == w


def test_a_fuel_leak_loses_extra_fuel_but_delivers_the_same_power() -> None:
    v, leaking = vessel(battery_pct=50.0), vessel(battery_pct=50.0)
    burn(v, "transit", CRUISE_MS, 3600)
    burn(leaking, "transit", CRUISE_MS, 3600, fuel_factor=1.5)
    assert FUEL_TANK_L - leaking.fuel_l == pytest.approx(1.5 * (FUEL_TANK_L - v.fuel_l))
    assert leaking.battery_pct == v.battery_pct


def test_litres_to_kwh_inverts_the_fuel_model() -> None:
    assert fuel_l(100.0, 3600) * KWH_PER_L == pytest.approx(100.0)
