import pytest
from fields import DATA_T0, T0, still, uniform
from geo import displacement
from oceanclean_common.regions import MISSION_BOX
from oceanclean_common.settings import parse_utc
from replay import STEP_S, replay, seeds


def test_seeds_four_parcels_per_hotspot_cell_inside_the_box() -> None:
    hotspots = [
        {"rank": 1, "lat": 35.5, "lon": -142.5},
        {"rank": 2, "lat": 25.5, "lon": -160.5},  # outside the mission box
    ]
    got = seeds(hotspots, MISSION_BOX)
    assert [p[0] for p in got] == ["H1-0", "H1-1", "H1-2", "H1-3"]
    assert {(lat, lon) for _, lat, lon in got} == {
        (35.25, -142.75),
        (35.25, -142.25),
        (35.75, -142.75),
        (35.75, -142.25),
    }


def test_frames_span_the_data_window_from_sim_start() -> None:
    out = replay(still(), [("a", 35.0, -142.0)])  # 3 daily steps: a 2-day window
    frames = out["frames"]
    assert len(frames) == 2 * 86400 // STEP_S
    assert parse_utc(frames[0]["t"]).timestamp() == T0
    assert parse_utc(frames[0]["data_t"]).timestamp() == DATA_T0
    assert parse_utc(frames[-1]["data_t"]).timestamp() == DATA_T0 + 2 * 86400 - STEP_S
    assert out["parcels"][0]["track"] == [[35.0, -142.0]] * len(frames)


def test_parcels_drift_with_the_current() -> None:
    out = replay(uniform(0.1, 0.0), [("a", 35.0, -142.0)])
    track = out["parcels"][0]["track"]
    east, north = displacement(35.0, -142.0, *track[-1])
    assert east == pytest.approx(0.1 * (2 * 86400 - STEP_S), rel=0.01)
    assert north == pytest.approx(0.0, abs=50)
