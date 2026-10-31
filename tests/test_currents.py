import io
from datetime import datetime, timezone

import numpy as np
import pytest
from currents import CurrentField
from fields import DATA_T0, LAT, LON, T0, field_of

DAY = 86400.0


def test_bilinear_is_exact_for_a_linear_field() -> None:
    f = field_of(lambda la, lo: (0.01 * la, -0.02 * lo))
    u, v = f.uv(T0, 33.37, -141.11)
    assert u == pytest.approx(0.3337)
    assert v == pytest.approx(2.8222)


def test_time_interpolates_on_the_uneven_time_axis_not_index() -> None:
    # Days 0, 1 and 3: SCUD skips days, so index * 86400 would put t = 2 d on the last step.
    time = np.array([DATA_T0, DATA_T0 + DAY, DATA_T0 + 3 * DAY])
    u = np.array([0.0, 1.0, 3.0])[:, None, None] * np.ones((3, len(LAT), len(LON)))
    f = CurrentField.from_arrays(time, LAT, LON, u, np.zeros_like(u), T0)
    assert f.uv(T0 + 2 * DAY, 35.0, -142.0)[0] == pytest.approx(2.0)
    assert f.uv(T0 + 0.5 * DAY, 35.0, -142.0)[0] == pytest.approx(0.5)


def test_sim_time_maps_onto_the_data_window_and_loops() -> None:
    f = field_of(lambda _a, _b: (0.0, 0.0), days=3)
    assert f.data_time(T0) == DATA_T0
    assert f.data_time(T0 + 5.0) == DATA_T0 + 5.0
    assert f.data_time(T0 + 2 * DAY + 5.0) == pytest.approx(DATA_T0 + 5.0)


def test_positions_off_the_grid_use_the_edge_and_gaps_are_still_water() -> None:
    f = field_of(lambda la, _lo: (la, 0.0))
    assert f.uv(T0, 50.0, -142.0)[0] == pytest.approx(LAT[-1])
    u = np.full((1, len(LAT), len(LON)), np.nan)
    g = CurrentField.from_arrays(np.array([DATA_T0]), LAT, LON, u, u, T0)
    assert g.uv(T0, 35.0, -142.0) == (0.0, 0.0)


def test_loads_the_batch_layer_npz_export() -> None:
    buf = io.BytesIO()
    u = np.ones((2, len(LAT), len(LON)), dtype=np.float32) * 0.1
    time = np.array([DATA_T0, DATA_T0 + DAY])
    np.savez_compressed(buf, time=time, lat=LAT, lon=LON, u=u, v=-u)
    f = CurrentField.from_npz(buf.getvalue(), datetime.fromtimestamp(T0, timezone.utc))
    assert f.uv(T0 + 3600, 35.0, -142.0) == pytest.approx((0.1, -0.1))


def test_grid_at_matches_point_interpolation_on_the_uneven_time_axis() -> None:
    time = np.array([DATA_T0, DATA_T0 + DAY, DATA_T0 + 3 * DAY])
    u = np.array([0.0, 1.0, 3.0])[:, None, None] * np.ones((3, len(LAT), len(LON)))
    f = CurrentField.from_arrays(time, LAT, LON, u, -u, T0)
    gu, gv = f.grid_at(T0 + 2 * DAY)
    assert gu.shape == (len(LAT), len(LON))
    assert gu[5, 7] == pytest.approx(f.uv(T0 + 2 * DAY, LAT[5], LON[7])[0])
    assert gv[5, 7] == pytest.approx(-2.0)


def test_grid_at_loops_over_the_data_window_like_uv() -> None:
    f = field_of(lambda la, lo: (0.01 * la, 0.0), days=3)
    a, _ = f.grid_at(T0 + 3600.0)
    b, _ = f.grid_at(T0 + 2 * DAY + 3600.0)
    np.testing.assert_allclose(a, b)
