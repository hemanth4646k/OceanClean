"""Human-in-the-loop rules for route proposals (SRS 5.4, ADR-0007, M5).

Autopilot (the simulation default) decides at once and never holds the clock. When the vessel
is idle (no active route, or every target of it collected) it accepts any proposal. Mid-route
it accepts only `deviation` proposals, which correct the plan it follows; the vessel steers for
the stored ghost and only sees a patch within 10 km, so ignoring a large deviation could strand
it at an empty ghost. Other mid-route proposals are rejected so the gate can propose again.

Manual mode holds the sim clock while a proposal is pending; after the timeout (real seconds)
the proposal expires and the vessel keeps its active route, or loiters if it has none.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from oceanclean_common.settings import parse_utc

Action = Literal["accept", "reject", "expire", "hold"]


def mid_route(active: dict | None, live_patch_ids: Collection[str]) -> bool:
    return active is not None and any(t["patch_id"] in live_patch_ids for t in active["targets"])


def decide(
    pending: dict | None,
    active: dict | None,
    live_patch_ids: Collection[str],
    autopilot: bool,
    waited_s: float,
    timeout_s: float,
) -> Action | None:
    if pending is None:
        return None
    if autopilot:
        if not mid_route(active, live_patch_ids) or pending["reason"] == "deviation":
            return "accept"
        return "reject"
    return "expire" if waited_s >= timeout_s else "hold"


@dataclass(frozen=True)
class Step:
    action: Action | None
    deadline: float | None  # epoch seconds (wall clock) when a held proposal expires
    hold: bool  # whether the sim clock should be held for a decision


def step(snap: dict, autopilot: bool, timeout_s: float, extra_s: float, now: float) -> Step:
    """What the API does about the snapshot's proposal at wall time `now` (epoch seconds).

    The countdown runs from the route's created_at; `extra_s` extends it while the operator
    modifies the route.
    """
    pending, active = snap["routes"]["pending"], snap["routes"]["active"]
    live = {p["patch_id"] for p in snap["patches"] if p["mass_kg"] > 0}
    deadline = None
    if pending is not None and not autopilot:
        deadline = parse_utc(pending["created_at"]).timestamp() + timeout_s + extra_s
    waited = 0.0 if deadline is None else now - (deadline - timeout_s)
    action = decide(pending, active, live, autopilot, waited, timeout_s)
    return Step(action, deadline, action == "hold")


ACCEPTED = frozenset({"active", "superseded"})


def acceptance_rates(counts: list[dict]) -> dict[str, float | None]:
    """Share of decided proposals accepted, from store.decision_counts rows. A timeout is the
    operator not accepting, so it counts against the operator's rate."""

    def rate(deciders: set[str]) -> float | None:
        rows = [c for c in counts if c["by"] in deciders]
        total = sum(c["n"] for c in rows)
        return sum(c["n"] for c in rows if c["status"] in ACCEPTED) / total if total else None

    return {
        "operator": rate({"operator", "timeout"}),
        "autopilot": rate({"autopilot"}),
        "overall": rate({"operator", "timeout", "autopilot"}),
    }
