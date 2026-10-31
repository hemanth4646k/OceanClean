import json
from datetime import datetime, timezone
from pathlib import Path

import sim_state
from vessel import VesselState

NEXT_TICK = datetime(2026, 9, 1, 4, 50, tzinfo=timezone.utc)


def vessel() -> VesselState:
    return VesselState("OC-01", lat=35.0, lon=-141.4, heading_deg=90.0, speed_kn=6.0, seq=291)


def test_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "oc.json"
    sim_state.save(p, NEXT_TICK, vessel(), {"mode": "loiter"})
    assert sim_state.load(p) == (NEXT_TICK, vessel(), {"mode": "loiter"})
    assert "next_tick" in json.loads(p.read_text())


def test_loads_state_written_with_legacy_clock_now_key(tmp_path: Path) -> None:
    p = tmp_path / "oc.json"
    v = vessel()
    p.write_text(json.dumps({"clock_now": NEXT_TICK.isoformat(), "vessel": v.__dict__}))
    assert sim_state.load(p) == (NEXT_TICK, v, None)


def test_missing_file_is_fresh_start(tmp_path: Path) -> None:
    assert sim_state.load(tmp_path / "none.json") is None
