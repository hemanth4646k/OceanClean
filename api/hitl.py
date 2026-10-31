"""Human-in-the-loop rules for route proposals (SRS 5.4, ADR-0007, M5).

Autopilot (the simulation default) accepts every proposal at once and never holds the clock.
Until 2026-10-31 it rejected mid-route `target_collected` proposals; the gate then re-proposed the
same situation every 30 sim-minutes, and the rejections made up ~85 % of its decisions (ADR-0008).

Manual mode holds the sim clock while a proposal is pending; after the timeout (real seconds)
the proposal expires and the vessel keeps its active route, or loiters if it has none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from oceanclean_common.settings import parse_utc

Action = Literal["accept", "expire", "hold"]


def decide(
    pending: dict | None, autopilot: bool, waited_s: float, timeout_s: float
) -> Action | None:
    if pending is None:
        return None
    if autopilot:
        return "accept"
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
    pending = snap["routes"]["pending"]
    deadline = None
    if pending is not None and not autopilot:
        deadline = parse_utc(pending["created_at"]).timestamp() + timeout_s + extra_s
    waited = 0.0 if deadline is None else now - (deadline - timeout_s)
    action = decide(pending, autopilot, waited, timeout_s)
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
