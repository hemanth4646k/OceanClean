from datetime import datetime, timezone

import sim_state
from vessel import VesselState


def test_round_trip(tmp_path) -> None:
    p = tmp_path / "oc.json"
    now = datetime(2026, 9, 1, 4, 50, tzinfo=timezone.utc)
    v = VesselState("OC-01", lat=35.0, lon=-141.4, heading_deg=90.0, speed_kn=6.0, seq=291)
    sim_state.save(p, now, v)
    assert sim_state.load(p) == (now, v)


def test_missing_file_is_fresh_start(tmp_path) -> None:
    assert sim_state.load(tmp_path / "none.json") is None
