import math
from collections.abc import Callable

import pytest
from drift import predict_track
from energy import CRUISE_MS
from fields import T0, still, uniform
from geo import displacement, distance_m, offset
from intercept import Position, intercept, steer_heading

START = (35.0, -142.0)


def moving(
    origin: tuple[float, float], east_ms: float, north_ms: float
) -> Callable[[float], Position]:
    """Target trajectory with its own constant ground velocity, independent of the field."""
    return lambda t: offset(*origin, east_ms * (t - T0), north_ms * (t - T0))


def analytic_t(d: tuple[float, float], r: tuple[float, float], s: float) -> float:
    """Earliest t with |d + r t| = s t, r = target velocity relative to the water."""
    dr = d[0] * r[0] + d[1] * r[1]
    a = s * s - (r[0] ** 2 + r[1] ** 2)
    dd = d[0] ** 2 + d[1] ** 2
    return (dr + math.sqrt(dr * dr + a * dd)) / a


def test_patch_drifting_with_the_current_is_met_after_distance_over_speed() -> None:
    # The vessel and the patch share the current, so in the water frame the patch is still.
    f = uniform(0.3, 0.1)
    patch0 = offset(*START, 40_000.0, 25_000.0)
    track = predict_track(f, T0, *patch0, T0 + 7 * 86400)
    meet = intercept(f, T0, START, CRUISE_MS, track.at)
    assert meet is not None
    expected = math.hypot(40_000.0, 25_000.0) / CRUISE_MS
    assert meet.t - T0 == pytest.approx(expected, rel=0.005)


@pytest.mark.parametrize(
    ("current", "target_v"),
    [((0.0, 0.0), (0.5, 0.0)), ((0.4, -0.2), (0.0, 0.3)), ((-0.3, 0.0), (0.6, 0.6))],
)
def test_moving_target_matches_the_analytic_intercept_in_a_constant_current(
    current: tuple[float, float], target_v: tuple[float, float]
) -> None:
    f = uniform(*current)
    patch0 = offset(*START, 30_000.0, -50_000.0)
    meet = intercept(f, T0, START, CRUISE_MS, moving(patch0, *target_v))
    assert meet is not None
    r = (target_v[0] - current[0], target_v[1] - current[1])
    expected = analytic_t(displacement(*START, *patch0), r, CRUISE_MS)
    assert meet.t - T0 == pytest.approx(expected, rel=0.005)
    # The returned point is where the target is at that time.
    assert distance_m(meet.lat, meet.lon, *moving(patch0, *target_v)(meet.t)) < 1.0


def test_target_outrunning_the_vessel_is_not_reachable() -> None:
    patch0 = offset(*START, 20_000.0, 0.0)
    assert intercept(still(), T0, START, CRUISE_MS, moving(patch0, 4.0, 0.0)) is None


def test_target_beyond_the_horizon_is_not_reachable() -> None:
    far = offset(*START, 0.0, 400_000.0)  # ~36 h at 6 kn
    assert intercept(still(), T0, START, CRUISE_MS, lambda _t: far, horizon_s=86400) is None
    assert intercept(still(), T0, START, CRUISE_MS, lambda _t: far) is not None


def test_heading_points_through_the_water_not_at_the_target() -> None:
    f = uniform(1.0, 0.0)  # 1 m/s eastward set
    target = offset(*START, 0.0, 30_000.0)  # due north
    meet = intercept(f, T0, START, 2.0, lambda _t: target)
    assert meet is not None
    assert meet.heading_deg == pytest.approx(330.0, abs=0.5)


def test_steer_heading_crabs_into_the_cross_current() -> None:
    assert steer_heading(0.0, 2.0, 0.0, 0.0) == 0.0
    h = steer_heading(0.0, 2.0, 1.0, 0.0)
    assert h == pytest.approx(330.0)
    east = 2.0 * math.sin(math.radians(h)) + 1.0
    assert east == pytest.approx(0.0, abs=1e-9)
    # Cross-current stronger than the vessel: no heading holds the track; point at it.
    assert steer_heading(90.0, 1.0, 0.0, 3.0) == 90.0
