from collections.abc import Callable

from fields import T0
from gate import DEVIATION_M, MIN_INTERVAL_S, RouteRef, recalc_reason
from geo import offset
from intercept import Position

P = (35.0, -142.0)
Q = (35.2, -141.8)
ROUTE = RouteRef(1, "active", T0, (("a", *P), ("b", *Q)))
NOW = T0 + 2 * MIN_INTERVAL_S
LIVE = {"a", "b", "c"}


def same(r: RouteRef) -> list[Position | None]:
    return [(lat, lon) for _, lat, lon in r.targets]


def shifted(metres: float) -> Callable[[RouteRef], list[Position | None]]:
    return lambda r: [P, offset(*Q, metres, 0.0)]


def test_fires_when_there_is_no_route_at_all() -> None:
    assert recalc_reason(NOW, None, None, LIVE, same) == "no_route"


def test_never_fires_while_a_proposal_awaits_the_operator() -> None:
    pending = RouteRef(2, "pending", T0, ROUTE.targets)
    assert recalc_reason(NOW, pending, None, LIVE, same) is None
    assert recalc_reason(NOW, pending, ROUTE, {"c"}, shifted(10_000)) is None


def test_waits_min_interval_after_the_last_proposal() -> None:
    rejected = RouteRef(2, "rejected", NOW - MIN_INTERVAL_S / 2, ROUTE.targets)
    assert recalc_reason(NOW, rejected, None, LIVE, same) is None
    later = NOW + MIN_INTERVAL_S
    assert recalc_reason(later, rejected, None, LIVE, same) == "no_route"


def test_fires_when_an_active_target_was_collected() -> None:
    assert recalc_reason(NOW, ROUTE, ROUTE, {"b", "c"}, same) == "target_collected"


def test_fires_on_deviation_beyond_two_km_only() -> None:
    assert recalc_reason(NOW, ROUTE, ROUTE, LIVE, same) is None
    assert recalc_reason(NOW, ROUTE, ROUTE, LIVE, shifted(DEVIATION_M * 0.75)) is None
    assert recalc_reason(NOW, ROUTE, ROUTE, LIVE, shifted(DEVIATION_M * 1.25)) == "deviation"


def test_target_no_longer_reachable_counts_as_deviation() -> None:
    assert recalc_reason(NOW, ROUTE, ROUTE, LIVE, lambda r: [P, None]) == "deviation"
