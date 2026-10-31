"""Edge-local persistence so a restarted simulator resumes its clock, seq and position.

Without this a restart would reuse seq numbers (dropped by dedup) and emit event times older
than the live state (rejected by the UPSERT guard), freezing the twin.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from vessel import VesselState


def save(path: Path, clock_now: datetime, v: VesselState) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"clock_now": clock_now.isoformat(), "vessel": asdict(v)}))
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written file


def load(path: Path) -> tuple[datetime, VesselState] | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return datetime.fromisoformat(d["clock_now"]), VesselState(**d["vessel"])
