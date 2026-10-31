from datetime import datetime, timedelta, timezone

import pytest
from anomaly import Tail, WindowAgg, expected_kwh, score
from energy import (
    BATTERY_KWH,
    COLLECT_KN,
    COLLECTOR_KW,
    CRUISE_MS,
    HOLD_CAPACITY_KG,
    HOTEL_KW,
    fuel_l,
    propulsion_kw,
    transit_kw,
)
from geo import KN_TO_MS

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
TICK = 60.0
TRANSIT_L = fuel_l(transit_kw(), TICK)  # litres per tick at cruise, battery full


def agg(k: int, fuel: float, n: int = 5, v_ms: float = CRUISE_MS, **over: object) -> WindowAgg:
    """Window k (5 ticks of 60 s) at constant speed."""
    end = T0 + timedelta(minutes=5 * (k + 1))
    base = {
        "vessel_id": "OC-01",
        "window_end": end,
        "last_ts": end - timedelta(seconds=TICK),
        "n": n,
        "fuel_l": fuel,
        "battery_pct": 100.0,
        "hold_fill_pct": 0.0,
        "sum_v3": n * v_ms**3,
        "n_collect": 0,
    }
    return WindowAgg(**{**base, **over})


def tail_of(w: WindowAgg, anomaly: bool = False) -> Tail:
    return Tail(w.last_ts, w.fuel_l, w.battery_pct, w.hold_fill_pct, anomaly)


def test_expected_energy_follows_the_power_model_per_tick() -> None:
    v = COLLECT_KN * KN_TO_MS
    kwh = expected_kwh(sum_v3=3 * v**3, n=3, n_collect=3, tick_s=TICK)
    assert kwh == pytest.approx(3 * (propulsion_kw(v) + HOTEL_KW + COLLECTOR_KW) * TICK / 3600)


def test_steady_transit_measures_its_model_energy_with_zero_residual() -> None:
    w0 = agg(0, 1000.0)
    w1 = agg(1, 1000.0 - 5 * TRANSIT_L)
    [s] = score(tail_of(w0), [w1], history=[0.0] * 10, tick_s=TICK)
    assert s.energy_kwh == pytest.approx(5 * transit_kw() * TICK / 3600)
    assert s.residual == pytest.approx(0.0, abs=1e-9)
    assert not s.anomaly


def test_battery_drawdown_and_collection_count_from_the_previous_window() -> None:
    w0 = agg(0, 1000.0, battery_pct=80.0, hold_fill_pct=10.0)
    w1 = agg(1, 1000.0, battery_pct=79.0, hold_fill_pct=12.0)
    [s] = score(tail_of(w0), [w1], history=[], tick_s=TICK)
    assert s.energy_kwh == pytest.approx(0.01 * BATTERY_KWH)
    assert s.collected_kg == pytest.approx(0.02 * HOLD_CAPACITY_KG)


def test_a_fuel_leak_is_an_anomaly_once_at_onset() -> None:
    w0 = agg(0, 1000.0)
    w1 = agg(1, 1000.0 - 7.5 * TRANSIT_L)  # 1.5x the fuel for the same power
    w2 = agg(2, 1000.0 - 15 * TRANSIT_L)
    s1, s2 = score(tail_of(w0), [w1, w2], history=[0.0] * 10, tick_s=TICK)
    assert s1.residual == pytest.approx(0.5) and s1.anomaly and s1.onset
    assert s2.anomaly and not s2.onset
    [s3] = score(tail_of(w2, anomaly=True), [agg(3, 900.0)], history=[0.0] * 10, tick_s=TICK)
    assert not s3.onset


def test_small_noise_from_battery_clamping_is_not_an_anomaly() -> None:
    w0 = agg(0, 1000.0)
    w1 = agg(1, 1000.0 - 5 * TRANSIT_L * 1.08)
    [s] = score(tail_of(w0), [w1], history=[0.0] * 10, tick_s=TICK)
    assert not s.anomaly


def test_refuel_and_gaps_are_measured_but_not_scored() -> None:
    w0 = agg(0, 100.0)
    refuel = agg(1, 12_000.0)
    [s] = score(tail_of(w0), [refuel], history=[0.0] * 10, tick_s=TICK)
    assert s.energy_kwh == 0.0 and s.residual is None and not s.anomaly
    gap = agg(3, 100.0 - 5 * TRANSIT_L)  # window 2 never arrived: 10 ticks, 5 rows
    [g] = score(tail_of(w0), [gap], history=[0.0] * 10, tick_s=TICK)
    assert g.energy_kwh == pytest.approx(5 * transit_kw() * TICK / 3600)
    assert g.residual is None


def test_an_empty_tank_is_not_scored() -> None:
    # Adrift with a dry tank, the simulator clamps fuel at 0: the load goes unmeasured.
    w0 = agg(0, 2 * TRANSIT_L)
    dry = agg(1, 0.0)
    [s] = score(tail_of(w0), [dry], history=[0.0] * 10, tick_s=TICK)
    assert s.residual is None and not s.anomaly
    [s] = score(tail_of(dry), [agg(2, 0.0)], history=[0.0] * 10, tick_s=TICK)
    assert s.residual is None and s.energy_kwh == 0.0


def test_first_window_and_a_sim_reset_have_no_baseline() -> None:
    w5 = agg(5, 900.0)
    [first] = score(None, [w5], history=[], tick_s=TICK)
    assert first.residual is None and first.energy_kwh == 0.0
    [after_reset] = score(tail_of(agg(9, 500.0)), [w5], history=[], tick_s=TICK)
    assert after_reset.residual is None and after_reset.energy_kwh == 0.0
