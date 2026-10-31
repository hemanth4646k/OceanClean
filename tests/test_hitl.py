from datetime import datetime, timezone

from hitl import Step, acceptance_rates, decide, step

CREATED = "2026-10-31T13:00:00Z"
T_CREATED = datetime(2026, 10, 31, 13, 0, tzinfo=timezone.utc).timestamp()


def route(rid: int, reason: str, *targets: str) -> dict:
    return {"route_id": rid, "reason": reason, "targets": [{"patch_id": t} for t in targets]}


def test_nothing_to_decide_without_a_proposal() -> None:
    assert decide(None, autopilot=True, waited_s=0, timeout_s=30) is None


def test_autopilot_accepts_every_proposal_idle_or_mid_route() -> None:
    """A fresh plan after a collection replaces the rest of the old chain (ADR-0008, amended):
    rejecting it only made the gate re-propose the same situation every 30 sim-minutes."""
    for reason in ("no_route", "target_collected", "deviation"):
        pending = route(2, reason, "P3")
        assert decide(pending, autopilot=True, waited_s=0, timeout_s=30) == "accept"


def test_manual_mode_holds_the_clock_until_the_timeout_expires_the_proposal() -> None:
    pending = route(2, "deviation", "P3")
    assert decide(pending, autopilot=False, waited_s=29.9, timeout_s=30) == "hold"
    assert decide(pending, autopilot=False, waited_s=30, timeout_s=30) == "expire"


def snap(pending: dict | None, hold: bool = False) -> dict:
    live = [{"patch_id": "P3", "mass_kg": 900.0}, {"patch_id": "P1", "mass_kg": 0.0}]
    return {
        "routes": {"active": None, "pending": pending},
        "patches": live,
        "clock": {"hitl_hold": hold},
    }


def proposal() -> dict:
    return {**route(2, "deviation", "P3"), "created_at": CREATED}


def test_step_with_autopilot_decides_at_once_and_never_holds() -> None:
    got = step(snap(proposal()), autopilot=True, timeout_s=30, extra_s=0, now=T_CREATED + 1)
    assert got == Step("accept", None, False)


def test_step_in_manual_mode_holds_until_the_deadline_then_expires() -> None:
    s = snap(proposal())
    deadline = T_CREATED + 30
    assert step(s, False, 30, 0, now=T_CREATED + 10) == Step("hold", deadline, True)
    assert step(s, False, 30, 0, now=T_CREATED + 30) == Step("expire", deadline, False)


def test_step_extension_moves_the_deadline_for_a_modify_in_progress() -> None:
    got = step(snap(proposal()), False, 30, extra_s=60, now=T_CREATED + 40)
    assert got == Step("hold", T_CREATED + 90, True)


def test_step_releases_the_hold_when_nothing_is_pending() -> None:
    assert step(snap(None, hold=True), False, 30, 0, now=T_CREATED) == Step(None, None, False)


def test_acceptance_rates_count_timeouts_against_the_operator() -> None:
    counts = [
        {"by": "operator", "status": "superseded", "n": 3},
        {"by": "operator", "status": "rejected", "n": 1},
        {"by": "timeout", "status": "expired", "n": 2},
        {"by": "autopilot", "status": "active", "n": 1},
        {"by": "autopilot", "status": "rejected", "n": 1},
    ]
    assert acceptance_rates(counts) == {"operator": 0.5, "autopilot": 0.5, "overall": 0.5}
    assert acceptance_rates([]) == {"operator": None, "autopilot": None, "overall": None}
