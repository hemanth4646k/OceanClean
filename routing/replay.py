"""Time-slider replay (spec story 2): debris parcels drifting through the mission window's real
daily SCUD currents, the same RK2 field the optimizer uses, sampled into frames for the map.

Frames are in sim time from SIM_START, which maps onto the window's first data day (ADR-0007),
so the map can fetch each frame's current grid with `/currents/grid?t=`. Each frame also carries
its data date: the real day of currents the parcels moved through.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from currents import CurrentField
from drift import predict_track
from oceanclean_common.regions import Box
from oceanclean_common.telemetry import format_ts

STEP_S = 6 * 3600.0
SPREAD_DEG = 0.25  # parcels per hotspot cell sit at its centre +/- this, in a 2 x 2 pattern


def seeds(hotspots: Iterable[Mapping[str, object]], box: Box) -> list[tuple[str, float, float]]:
    """(id, lat, lon): four parcels in every hotspot cell inside the box."""
    out = []
    cells = [h for h in hotspots if box.contains(float(h["lat"]), float(h["lon"]))]
    for h in cells:
        lat, lon = float(h["lat"]), float(h["lon"])
        for k, (a, b) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
            out.append((f"H{h['rank']}-{k}", lat + a * SPREAD_DEG, lon + b * SPREAD_DEG))
    return out


def _iso(t: float) -> str:
    return format_ts(datetime.fromtimestamp(t, timezone.utc))


def replay(
    field: CurrentField, parcels: Iterable[tuple[str, float, float]], step_s: float = STEP_S
) -> dict[str, object]:
    """Every parcel's position each step_s across the data window, as JSON-ready frames."""
    t0 = field.sim_start
    # Stop short of the window's end: data_time loops, so the end itself maps back to day 0.
    n = math.ceil((field.time[-1] - field.time[0]) / step_s)
    times = [t0 + k * step_s for k in range(n)]
    tracks = []
    for pid, lat, lon in parcels:
        track = predict_track(field, t0, lat, lon, times[-1])
        pts = (track.at(t) for t in times)
        tracks.append({"id": pid, "track": [[round(a, 4), round(b, 4)] for a, b in pts]})
    return {
        "step_s": step_s,
        "frames": [{"t": _iso(t), "data_t": _iso(field.data_time(t))} for t in times],
        "parcels": tracks,
    }
