"""Recalc gate (SRS 3.3): heavy route recompute only when the plan is stale.

Fires when there is no active route, an active target was collected, or a target's re-predicted
intercept point moved more than 2 km. Never while a proposal awaits the operator, and at most
once per MIN_INTERVAL_S of sim time, so rejected or expired proposals are not re-sent every
micro-batch.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from geo import distance_m
from intercept import Position

DEVIATION_M = 2000.0
MIN_INTERVAL_S = 1800.0


@dataclass(frozen=True)
class RouteRef:
    route_id: int
    status: str  # pending | active | rejected | expired | superseded
    planned_ts: float  # sim epoch seconds of the vessel state the plan started from
    targets: tuple[tuple[str, float, float], ...]  # (patch_id, predicted lat, predicted lon)


def recalc_reason(
    now: float,
    latest: RouteRef | None,
    active: RouteRef | None,
    live_patch_ids: Collection[str],
    repredict: Callable[[RouteRef], list[Position | None]],
) -> str | None:
    """Why a new route should be proposed now, or None. `latest` is the newest route row."""
    if latest is not None:
        if latest.status == "pending":
            return None
        if now - latest.planned_ts < MIN_INTERVAL_S:
            return None
    if active is None:
        return "no_route"
    if any(pid not in live_patch_ids for pid, _, _ in active.targets):
        return "target_collected"
    for (_, lat, lon), new in zip(active.targets, repredict(active), strict=True):
        if new is None or distance_m(lat, lon, *new) > DEVIATION_M:
            return "deviation"
    return None
