import math

import pytest
from drift import Track, predict_track, rk2_step
from fields import CENTER, T0, angle_deg, rotational, uniform
from geo import displacement, distance_m

DAY = 86400.0


def test_uniform_field_moves_a_patch_by_u_t_and_v_t() -> None:
    f = uniform(0.12, -0.05)
    track = predict_track(f, T0, 35.0, -142.0, T0 + DAY)
    assert len(track.points) == 25
    east, north = displacement(35.0, -142.0, *track.points[-1])
    assert east == pytest.approx(0.12 * DAY, rel=1e-3)
    assert north == pytest.approx(-0.05 * DAY, rel=1e-3)


def test_rotational_field_keeps_radius_and_turns_by_omega_t() -> None:
    period = 4 * DAY
    f = rotational(2 * math.pi / period)
    start = (CENTER[0], CENTER[1] + 0.5)  # ~45 km east of the centre
    r0 = distance_m(*CENTER, *start)
    track = predict_track(f, T0, *start, T0 + period / 4)
    end = track.points[-1]
    assert distance_m(*CENTER, *end) == pytest.approx(r0, rel=0.01)
    assert angle_deg(*end) == pytest.approx(90.0, abs=1.0)


def test_rk2_beats_euler_on_rotation() -> None:
    omega = 2 * math.pi / DAY
    f = rotational(omega)
    lat, lon = CENTER[0], CENTER[1] + 0.5
    r0 = distance_m(*CENTER, lat, lon)
    for k in range(6):  # a quarter turn in 1 h steps
        lat, lon = rk2_step(f, T0 + k * 3600, lat, lon, 3600)
    # Euler would spiral out by a factor sqrt(1 + (omega dt)^2)^6, about 3.3% here.
    assert distance_m(*CENTER, lat, lon) == pytest.approx(r0, rel=0.005)


def test_track_interpolates_between_steps_and_holds_its_ends() -> None:
    tr = Track(100.0, 10.0, ((0.0, 0.0), (1.0, 2.0)))
    assert tr.at(105.0) == (0.5, 1.0)
    assert tr.at(0.0) == (0.0, 0.0)
    assert tr.at(1e9) == (1.0, 2.0)
    assert tr.t_end == 110.0
