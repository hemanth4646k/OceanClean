import json
import math

import pytest
from energy import CRUISE_MS
from fields import T0, still, uniform
from gate import DEVIATION_M
from geo import bearing_deg, displacement, distance_m, offset
from intercept import steer_heading
from planner import PatchObs, Plan, plan_chain, repredict, route_record

START = (35.0, -142.0)


def patch(pid: str, east_km: float, north_km: float, mass: float) -> PatchObs:
    lat, lon = offset(*START, east_km * 1000, north_km * 1000)
    return PatchObs(pid, T0, lat, lon, mass, 2000.0)


def ids(plan: Plan) -> list[str]:
    return [t.patch.patch_id for t in plan.targets]


def test_chain_is_greedy_by_mass_per_energy_from_each_predicted_position() -> None:
    patches = [
        patch("far-west", -50, 0, 2000),
        patch("near", 10, 0, 5000),
        patch("beyond", 30, 0, 5000),
        patch("light", 0, 5, 50),
    ]
    plan = plan_chain(still(), T0, START, patches)
    # "light" is closest, but 50 kg per its energy loses; from "near", "beyond" is 20 km away.
    assert ids(plan) == ["near", "beyond", "far-west"]
    t0, t1, t2 = plan.targets
    assert t1.start_t == t0.leave_t and t2.start_t == t1.leave_t
    assert t0.score > t1.score
    assert plan.mass_kg == 12000


def test_heavier_farther_patch_beats_a_light_near_one() -> None:
    plan = plan_chain(still(), T0, START, [patch("light", 5, 0, 100), patch("heavy", 0, 20, 8000)])
    assert ids(plan)[0] == "heavy"


def test_chain_stops_at_three_and_skips_collected_patches() -> None:
    patches = [patch(f"p{k}", 10 * k, 0, 1000) for k in range(1, 6)]
    patches[0] = PatchObs("p1", T0, patches[0].lat, patches[0].lon, 0.0, 2000.0)
    plan = plan_chain(still(), T0, START, patches)
    assert ids(plan) == ["p2", "p3", "p4"]


def test_repredicting_a_fresh_plan_returns_its_own_points() -> None:
    f = uniform(0.15, 0.08)
    patches = [patch("a", 40, 10, 3000), patch("b", 60, -30, 4000), patch("c", -20, 40, 2000)]
    plan = plan_chain(f, T0, START, patches)
    again = repredict(f, T0, START, ids(plan), {p.patch_id: p for p in patches})
    for tg, new in zip(plan.targets, again, strict=True):
        assert new is not None
        assert distance_m(tg.meet.lat, tg.meet.lon, new.lat, new.lon) < 50


def test_vessel_following_the_plan_does_not_drift_past_the_gate() -> None:
    f = uniform(0.2, -0.1)
    patches = [patch("a", 60, 20, 3000), patch("b", 90, -10, 3000)]
    plan = plan_chain(f, T0, START, patches)
    pos, t = START, T0
    first = plan.targets[0].meet
    for _ in range(6 * 6):  # six hours of 10-minute steps, crabbing toward the first intercept
        u, v = f.uv(t, *pos)
        h = steer_heading(bearing_deg(*displacement(*pos, first.lat, first.lon)), CRUISE_MS, u, v)
        pos = offset(*pos, *(600 * x for x in _velocity(h, u, v)))
        t += 600
    again = repredict(f, t, pos, ids(plan), {p.patch_id: p for p in patches})
    for tg, new in zip(plan.targets, again, strict=True):
        assert new is not None
        assert distance_m(tg.meet.lat, tg.meet.lon, new.lat, new.lon) < DEVIATION_M / 4


def _velocity(heading: float, u: float, v: float) -> tuple[float, float]:
    h = math.radians(heading)
    return CRUISE_MS * math.sin(h) + u, CRUISE_MS * math.cos(h) + v


def test_unreachable_patches_give_an_empty_plan() -> None:
    plan = plan_chain(still(), T0, START, [patch("far", 0, 3000, 5000)])
    assert plan.targets == ()


def test_route_record_is_json_with_a_lon_lat_linestring() -> None:
    plan = plan_chain(still(), T0, START, [patch("a", 10, 0, 1000), patch("b", 20, 0, 1000)])
    rec = route_record(plan)
    json.dumps(rec)
    assert rec["wkt"].startswith(f"LINESTRING({START[1]} {START[0]}, ")
    assert rec["wkt"].count(",") == 2
    wp = rec["waypoints"]
    assert [w["kind"] for w in wp] == ["start", "target", "target"]
    assert wp[0]["ts"] == "2026-09-01T00:00:00.000Z"
    tg = rec["targets"][0]
    assert tg["patch_id"] == "a"
    assert tg["drift"][-1] == [tg["predicted"]["lat"], tg["predicted"]["lon"]]
    assert rec["energy_kwh"] == pytest.approx(plan.energy_kwh)
