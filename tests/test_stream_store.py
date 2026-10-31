"""Window/alert/lake-count writes against the Compose PostGIS, on temp tables (live rows untouched).

Skipped unless POSTGRES_* are set (CLAUDE.md Commands passes the network and env file).
"""

import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from anomaly import MIN_HISTORY, WindowAgg
from energy import CRUISE_MS, fuel_l, transit_kw
from oceanclean_common.settings import pg_dsn
from stream_store import add_lake_rows, store_windows

pytestmark = pytest.mark.skipif("POSTGRES_HOST" not in os.environ, reason="needs PostGIS")

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
TICK = 60.0
TRANSIT_L = fuel_l(transit_kw(), TICK)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_dsn(os.environ), autocommit=True) as c:
        for t in ("telemetry_windows", "alerts", "lake_counts"):
            c.execute(f"CREATE TEMP TABLE {t} (LIKE public.{t} INCLUDING ALL)")
        # LIKE copies alert_id's default, which would advance the live sequence.
        c.execute("CREATE TEMP SEQUENCE alerts_test_seq")
        c.execute("ALTER TABLE alerts ALTER alert_id SET DEFAULT nextval('alerts_test_seq')")
        yield c


def window(k: int, fuel: float) -> WindowAgg:
    """Window k: 5 ticks at cruise, battery full, ending at T0 + 5(k+1) minutes."""
    end = T0 + timedelta(minutes=5 * (k + 1))
    return WindowAgg(
        "OC-T", end, end - timedelta(seconds=TICK), 5, fuel, 100.0, 0.0, 5 * CRUISE_MS**3, 0
    )


def run(n_normal: int, leak: int, start_k: int = 0, fuel0: float = 1000.0) -> list[WindowAgg]:
    """n_normal steady windows then `leak` windows burning 1.6x the model's fuel."""
    out, fuel = [], fuel0
    for k in range(start_k, start_k + n_normal + leak):
        fuel -= 5 * TRANSIT_L * (1.6 if k >= start_k + n_normal else 1.0)
        out.append(window(k, fuel))
    return out


def stored(conn: psycopg.Connection) -> list[tuple[object, ...]]:
    return conn.execute(
        "SELECT window_end, round(energy_kwh::numeric, 6), residual IS NULL, anomaly"
        " FROM telemetry_windows ORDER BY window_end"
    ).fetchall()


def alerts(conn: psycopg.Connection) -> list[tuple[object, ...]]:
    return conn.execute("SELECT vessel_id, ts, kind, level FROM alerts ORDER BY ts").fetchall()


def test_windows_chain_from_the_stored_tail_across_batches(conn: psycopg.Connection) -> None:
    ws = run(3, 0)
    assert store_windows(conn, ws[:1], TICK) == 0
    assert store_windows(conn, ws[1:], TICK) == 0
    rows = stored(conn)
    assert [r[2] for r in rows] == [True, False, False]  # only the very first has no baseline
    assert rows[1][1] == rows[2][1] > 0  # the second batch measured from the first's tail


def test_a_leak_raises_one_alert_at_onset_even_across_batches(conn: psycopg.Connection) -> None:
    ws = run(MIN_HISTORY + 2, 3)
    store_windows(conn, ws[:-1], TICK)
    assert store_windows(conn, ws[-1:], TICK) == 0  # still anomalous: no second alert
    onset = ws[MIN_HISTORY + 2]
    assert alerts(conn) == [("OC-T", onset.last_ts, "fuel_anomaly", "warn")]
    assert [r[3] for r in stored(conn)][-3:] == [True, True, True]


def test_a_retried_batch_changes_nothing(conn: psycopg.Connection) -> None:
    ws = run(MIN_HISTORY + 2, 1)
    store_windows(conn, ws, TICK)
    before = stored(conn), alerts(conn)
    assert store_windows(conn, ws, TICK) == 0
    assert (stored(conn), alerts(conn)) == before


def test_lake_rows_accumulate_per_dataset(conn: psycopg.Connection) -> None:
    add_lake_rows(conn, "bronze/telemetry", 5)
    add_lake_rows(conn, "bronze/telemetry", 7)
    add_lake_rows(conn, "bronze/debris_survey", 2)
    got = conn.execute("SELECT dataset, rows FROM lake_counts ORDER BY dataset").fetchall()
    assert got == [("bronze/debris_survey", 2), ("bronze/telemetry", 12)]
