"""Live-view logic for the WebSocket: what changed between two polls, and the vessel's wake.

A snapshot is the JSON-ready state the API polls from PostGIS once a second: `vessel`,
`patches`, `routes` ({active, pending}) and `clock`, plus the hub's `hitl` state. Clients get
the full snapshot on connect, then only the parts that changed, plus alerts for proposals,
accepted routes and collections.
"""

from __future__ import annotations

from collections import deque

PARTS = ("vessel", "patches", "routes", "clock", "hitl")


class Wake:
    """Recent vessel positions in sim-time order, for the wake line on the map."""

    def __init__(self, max_age_s: float = 48 * 3600.0, max_points: int = 2000) -> None:
        self.max_age_s = max_age_s
        self._pts: deque[tuple[float, float, float]] = deque(maxlen=max_points)

    def add(self, t: float, lat: float, lon: float) -> None:
        if self._pts and t <= self._pts[-1][0]:
            if t == self._pts[-1][0]:
                return
            self._pts.clear()  # sim time went back: a clean sim start
        self._pts.append((t, lat, lon))
        while self._pts[0][0] < t - self.max_age_s:
            self._pts.popleft()

    def points(self) -> list[tuple[float, float]]:
        return [(lat, lon) for _, lat, lon in self._pts]


def changes(prev: dict | None, cur: dict) -> list[dict]:
    """Messages for the parts of `cur` that differ from `prev`, then any alerts."""
    msgs = [
        {"type": part, "data": cur[part]}
        for part in PARTS
        if prev is None or prev[part] != cur[part]
    ]
    if prev is not None:
        ts = (cur["clock"] or {}).get("sim_now")
        msgs += [{"type": "alert", "data": {**a, "ts": ts}} for a in _alerts(prev, cur)]
    return msgs


def _alerts(prev: dict, cur: dict) -> list[dict]:
    out = []
    pending, was_pending = cur["routes"]["pending"], prev["routes"]["pending"]
    if pending and (not was_pending or was_pending["route_id"] != pending["route_id"]):
        chain = " → ".join(t["patch_id"] for t in pending["targets"])
        text = (
            f"Route {pending['route_id']} proposed ({pending['reason']}): "
            f"{chain}, {pending['mass_kg'] / 1000:.1f} t"
        )
        out.append({"kind": "proposal", "level": "info", "text": text})
    active, was_active = cur["routes"]["active"], prev["routes"]["active"]
    by_autopilot = active is not None and active.get("decided_by") == "autopilot"
    new_active = active and (not was_active or was_active["route_id"] != active["route_id"])
    if new_active and not by_autopilot:  # autopilot decides often; the sidebar shows it
        out.append(
            {"kind": "active", "level": "info", "text": f"Route {active['route_id']} active"}
        )
    before = {p["patch_id"]: p["mass_kg"] for p in prev["patches"]}
    for p in cur["patches"]:
        mass = before.get(p["patch_id"], 0.0)
        if mass > 0 and p["mass_kg"] <= 0:
            text = f"Patch {p['patch_id']} collected ({mass / 1000:.1f} t at last survey)"
            out.append({"kind": "collected", "level": "success", "text": text})
    return out
