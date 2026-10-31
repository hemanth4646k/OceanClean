import random
from datetime import datetime, timedelta, timezone

import pytest
from backfill import (
    LIVE_SEQ_START,
    Autopilot,
    burst,
    chunks,
    history,
    live_ready,
    parse_duration,
)
from debris import Patch
from fields import T0, still, uniform
from geo import distance_m, offset
from oceanclean_common.telemetry import Telemetry
from vessel import VesselState
from world import World

START = (35.0, -142.0)
SIM_START = datetime.fromtimestamp(T0, timezone.utc)


def vessel() -> VesselState:
    return VesselState("OC-01", *START, heading_deg=90.0, speed_kn=0.0)


def run(
    hours: float, tick_s: float, patches: list[Patch], u: float = 0.0, v: float = 0.0
) -> tuple[World, VesselState, list[Telemetry]]:
    w, ves = World(patches), vessel()
    pilot = Autopilot(uniform(u, v) if (u, v) != (0.0, 0.0) else still())
    n = round(hours * 3600 / tick_s)
    events = list(history(w, ves, pilot, T0 - hours * 3600, n, tick_s, random.Random(1)))
    return w, ves, events


def test_parse_duration() -> None:
    assert parse_duration("30d") == 30 * 86400
    assert parse_duration("12h") == 12 * 3600
    assert parse_duration(" 90m ") == 5400
    assert parse_duration("1.5h") == 5400
    with pytest.raises(ValueError):
        parse_duration("30 days")


def test_history_ends_at_sim_start_with_contiguous_seqs_below_the_live_range() -> None:
    _, ves, events = run(2, 1.0, [])
    assert len(events) == 7200
    assert [e.seq for e in events] == list(range(1, 7201))
    assert events[0].event_ts == SIM_START - timedelta(hours=2) + timedelta(seconds=1)
    assert events[-1].event_ts == SIM_START
    assert all(not e.buffered for e in events)
    assert ves.seq == 7200 < LIVE_SEQ_START


def test_the_autopilot_plans_routes_and_the_vessel_collects() -> None:
    a = Patch("A", *offset(*START, 15_000, 0), 1500.0)
    b = Patch("B", *offset(*START, 15_000, 15_000), 1500.0)
    w, _, events = run(12, 1.0, [a, b])
    assert a.mass_kg == 0 and b.mass_kg == 0
    assert w.collected_kg == pytest.approx(3000.0, abs=2.0)  # collect() drops a last < 1 kg
    assert max(e.hold_fill_pct for e in events) > 0
    assert max(e.debris_density for e in events) > 0


def test_one_second_and_one_minute_ticks_tell_the_same_story() -> None:
    def far() -> list[Patch]:
        return [Patch("A", *offset(*START, 40_000, 10_000), 2000.0)]

    w1, v1, e1 = run(6, 1.0, far(), u=0.1, v=0.05)
    w60, v60, e60 = run(6, 60.0, far(), u=0.1, v=0.05)
    assert len(e1) == 60 * len(e60)
    assert e1[-1].event_ts == e60[-1].event_ts
    assert distance_m(v1.lat, v1.lon, v60.lat, v60.lon) < 500
    assert v1.fuel_l == pytest.approx(v60.fuel_l, rel=0.01)
    assert w1.patches[0].mass_kg == pytest.approx(w60.patches[0].mass_kg, abs=50)


def test_live_ready_needs_a_post_m6_live_run_an_hour_past_sim_start() -> None:
    ahead = SIM_START + timedelta(hours=2)
    assert live_ready(None, SIM_START) is not None
    assert "reset_sim" in (live_ready((53_523, ahead), SIM_START) or "")
    assert live_ready((LIVE_SEQ_START + 5, SIM_START + timedelta(minutes=5)), SIM_START)
    assert live_ready((LIVE_SEQ_START + 5, ahead), SIM_START) is None


def test_chunks_split_events_into_post_sized_json_batches() -> None:
    _, _, events = run(1, 1.0, [])
    batches = list(chunks(events, len(events), size=1000))
    assert [len(b) for b in batches] == [1000] * 3 + [600]
    assert Telemetry.model_validate_json(batches[-1][-1]) == events[-1]


def test_burst_retries_a_failed_post_and_keeps_the_order() -> None:
    got: list[str] = []
    fails = iter([True, False, False, True])

    def post(batch: list[str]) -> bool:
        if next(fails, False):
            return False
        got.extend(batch)
        return True

    sent = burst([["a", "b"], ["c"], ["d", "e"]], post, retry_s=0.0)
    assert sent == 5
    assert got == ["a", "b", "c", "d", "e"]
