"""Edge-local persistence so a restarted simulator resumes its clock, seq, position and world.

Without this a restart would reuse seq numbers (dropped by dedup) and emit event times older
than the live state (rejected by the UPSERT guard), freezing the twin. The world (patches,
offline queue, mode) is kept too, so debris collected stays collected and queued events survive.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from vessel import VesselState


def save(path: Path, next_tick: datetime, v: VesselState, world: dict | None = None) -> None:
    tmp = path.with_suffix(".tmp")
    doc = {"next_tick": next_tick.isoformat(), "vessel": asdict(v), "world": world}
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written file


def load(path: Path) -> tuple[datetime, VesselState, dict | None] | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    # "clock_now" is the pre-M1.5 name for the same value (the next tick's sim time).
    next_tick = d["next_tick"] if "next_tick" in d else d["clock_now"]
    return datetime.fromisoformat(next_tick), VesselState(**d["vessel"]), d.get("world")
