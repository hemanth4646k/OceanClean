"""Route transitions against the Compose PostGIS, on a temp copy of `routes` (live rows untouched).

Skipped unless POSTGRES_* are set: CLAUDE.md Commands runs pytest with `--network
oceanclean_default --env-file .env.example` so these run against the stack.
"""

import os
from collections.abc import Iterator

import psycopg
import pytest
from oceanclean_common.settings import pg_dsn
from psycopg.types.json import Jsonb
from store import (
    accept_route,
    decision_counts,
    expire_route,
    hourly_windows,
    metrics_series,
    modify_route,
    new_alerts,
    recent_alerts,
    reject_route,
    set_fuel_leak,
    set_hitl_hold,
    set_sim_clock,
    sim_clock,
)

pytestmark = pytest.mark.skipif("POSTGRES_HOST" not in os.environ, reason="needs PostGIS")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_dsn(os.environ), autocommit=True) as c:
        # Temp tables shadow public ones for this session; LIKE copies checks and the
        # one-pending / one-active partial unique indexes.
        c.execute("CREATE TEMP TABLE routes (LIKE public.routes INCLUDING ALL)")
        for t in (
            "sim_clock",
            "sim_faults",
            "alerts",
            "pipeline_metrics",
            "lake_counts",
            "telemetry_windows",
        ):
            c.execute(f"CREATE TEMP TABLE {t} (LIKE public.{t} INCLUDING ALL)")
        yield c


WAYPOINTS = [
    {"kind": "start", "lat": 35.0, "lon": -142.0, "ts": "2026-09-01T00:00:00.000Z"},
    {"kind": "target", "patch_id": "P1", "lat": 35.0, "lon": -141.0, "ts": "x"},
    {"kind": "target", "patch_id": "P2", "lat": 35.5, "lon": -141.0, "ts": "x"},
]


def add(conn: psycopg.Connection, route_id: int, status: str, vessel: str = "OC-T") -> None:
    conn.execute(
        "INSERT INTO routes (route_id, vessel_id, status, reason, planned_at, geom, waypoints,"
        " targets, energy_kwh, mass_kg, compute_ms) VALUES (%s, %s, %s, 'no_route', now(),"
        " ST_GeomFromText('LINESTRING(-142 35, -141 35)', 4326), %s, '[]', 1, 1, 1)",
        [route_id, vessel, status, Jsonb(WAYPOINTS)],
    )


def add_clock(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO sim_clock (vessel_id, sim_now, rate, paused)"
        " VALUES ('OC-T', '2026-09-01T06:00:00Z', 60, false)"
    )


def statuses(conn: psycopg.Connection) -> dict[int, tuple[str, bool]]:
    rows = conn.execute("SELECT route_id, status, decided_at IS NOT NULL FROM routes")
    return {r[0]: (r[1], r[2]) for r in rows}


def test_accept_activates_the_proposal_and_supersedes_the_old_route(
    conn: psycopg.Connection,
) -> None:
    add(conn, 1, "active")
    add(conn, 2, "pending")
    add(conn, 3, "active", vessel="OC-OTHER")
    route = accept_route(conn, 2, "autopilot")
    assert route is not None and route["status"] == "active" and route["decided_at"]
    assert route["decided_by"] == "autopilot"
    assert statuses(conn) == {
        1: ("superseded", True),
        2: ("active", True),
        3: ("active", False),
    }


def test_only_a_pending_route_can_be_decided(conn: psycopg.Connection) -> None:
    add(conn, 1, "active")
    add(conn, 2, "rejected")
    assert accept_route(conn, 1) is None
    assert accept_route(conn, 2) is None
    assert reject_route(conn, 99) is None
    assert statuses(conn) == {1: ("active", False), 2: ("rejected", False)}


def test_reject_keeps_the_active_route(conn: psycopg.Connection) -> None:
    add(conn, 1, "active")
    add(conn, 2, "pending")
    route = reject_route(conn, 2)
    assert route is not None and route["status"] == "rejected"
    assert statuses(conn) == {1: ("active", False), 2: ("rejected", True)}


def test_clock_control_changes_only_what_is_given(conn: psycopg.Connection) -> None:
    assert sim_clock(conn, "OC-T") is None
    assert set_sim_clock(conn, "OC-T", paused=True) is None  # simulator has not reported yet
    add_clock(conn)
    clock = set_sim_clock(conn, "OC-T", paused=True)
    assert clock == {**clock, "rate": 60.0, "paused": True, "sim_now": "2026-09-01T06:00:00Z"}
    clock = set_sim_clock(conn, "OC-T", rate=600.0)
    assert clock is not None and (clock["rate"], clock["paused"]) == (600.0, True)


def test_timeout_expires_only_a_pending_route(conn: psycopg.Connection) -> None:
    add(conn, 1, "active")
    add(conn, 2, "pending")
    route = expire_route(conn, 2)
    assert route is not None and (route["status"], route["decided_by"]) == ("expired", "timeout")
    assert expire_route(conn, 1) is None
    assert statuses(conn)[1] == ("active", False)


def test_modify_moves_target_waypoints_and_activates_the_route(conn: psycopg.Connection) -> None:
    add(conn, 1, "active")
    add(conn, 2, "pending")
    route = modify_route(conn, 2, {"P2": (35.7, -140.5)})
    assert route is not None and (route["status"], route["decided_by"]) == ("active", "operator")
    moved = {w.get("patch_id"): (w["lat"], w["lon"]) for w in route["waypoints"]}
    assert moved["P2"] == (35.7, -140.5) and moved["P1"] == (35.0, -141.0)
    wkt = conn.execute("SELECT ST_AsText(geom) FROM routes WHERE route_id = 2").fetchone()
    assert wkt is not None and wkt[0] == "LINESTRING(-142 35,-141 35,-140.5 35.7)"
    assert statuses(conn)[1] == ("superseded", True)
    add(conn, 3, "pending")
    with pytest.raises(ValueError):
        modify_route(conn, 3, {"P9": (35.0, -140.0)})  # not a target of the route


def test_clock_hold_and_fuel_leak_are_set_from_the_sim_clock(conn: psycopg.Connection) -> None:
    assert set_fuel_leak(conn, "OC-T", 6.0) is None  # no sim clock yet
    add_clock(conn)
    clock = set_hitl_hold(conn, "OC-T", True)
    assert clock is not None and clock["hitl_hold"] and not clock["paused"]
    assert set_fuel_leak(conn, "OC-T", 6.0) == "2026-09-01T12:00:00Z"


def test_new_alerts_are_returned_after_an_id(conn: psycopg.Connection) -> None:
    for i in range(3):
        conn.execute(
            "INSERT INTO alerts (alert_id, vessel_id, ts, kind, level, text)"
            " VALUES (%s, 'OC-T', now() + %s * interval '1 min', 'fuel_anomaly', 'warn', 'x')",
            [i + 1, i],
        )
    assert [a["alert_id"] for a in new_alerts(conn, 1)] == [2, 3]


def test_metrics_series_buckets_rows_per_query_and_keeps_the_latest(
    conn: psycopg.Connection,
) -> None:
    rows = [  # (seconds ago, query, batch, input rows, duration ms, lag)
        (25, "telemetry", 1, 100, 900.0, 4),
        (21, "telemetry", 2, 300, 1100.0, 9),
        (12, "telemetry", 3, 50, 500.0, 0),
        (12, "windows", 7, 10, 300.0, None),
        (3600, "telemetry", 0, 999, 1.0, 0),  # older than the asked-for window
    ]
    for ago, q, b, n, d, lag in rows:
        conn.execute(
            "INSERT INTO pipeline_metrics (ts, query, batch_id, input_rows, duration_ms, kafka_lag)"
            " VALUES (date_bin('10 s', now(), timestamptz '2000-01-01') - %s * interval '1 s'"
            " + interval '5 s', %s, %s, %s, %s, %s)",
            [ago, q, b, n, d, lag],
        )
    got = metrics_series(conn, minutes=10, bucket_s=10)
    tel = [r for r in got["series"] if r["query"] == "telemetry"]
    assert [(r["rows_per_s"], r["duration_ms"], r["kafka_lag"]) for r in tel] == [
        (40.0, 1000.0, 9),
        (5.0, 500.0, 0),
    ]
    assert {r["query"]: r["batch_id"] for r in got["latest"]} == {"telemetry": 3, "windows": 7}


def test_hourly_windows_sum_energy_and_debris_in_sim_time(conn: psycopg.Connection) -> None:
    for k in range(14):  # 5-minute windows from 00:05 to 01:10
        conn.execute(
            "INSERT INTO telemetry_windows (vessel_id, window_end, last_ts, n, fuel_l,"
            " battery_pct, hold_fill_pct, energy_kwh, expected_kwh, collected_kg, anomaly)"
            " VALUES ('OC-T', timestamptz '2026-09-01T00:05:00Z' + %s * interval '5 min',"
            " now(), 5, %s, 90, 0, 2.0, 2.0, 10.0, %s)",
            [k, 1000.0 - k, k == 13],
        )
    got = hourly_windows(conn, "OC-T", hours=48)
    assert [
        (h["hour"], h["energy_kwh"], h["collected_kg"], h["fuel_l"], h["anomalies"]) for h in got
    ] == [
        # By window start: the window ending 01:00 covers 00:55-01:00.
        ("2026-09-01T00:00:00Z", 24.0, 120.0, 989.0, 0),
        ("2026-09-01T01:00:00Z", 4.0, 20.0, 987.0, 1),
    ]


def test_decision_counts_treat_unrecorded_deciders_as_the_operator(
    conn: psycopg.Connection,
) -> None:
    for rid, status, by in [
        (1, "superseded", None),
        (2, "active", "autopilot"),
        (3, "rejected", "autopilot"),
        (4, "expired", "timeout"),
        (5, "pending", None),
    ]:
        add(conn, rid, status)
        conn.execute("UPDATE routes SET decided_by = %s WHERE route_id = %s", [by, rid])
    got = decision_counts(conn, "OC-T")
    assert sorted((r["by"], r["status"], r["n"]) for r in got) == [
        ("autopilot", "active", 1),
        ("autopilot", "rejected", 1),
        ("operator", "superseded", 1),
        ("timeout", "expired", 1),
    ]


def test_recent_alerts_are_the_newest_first(conn: psycopg.Connection) -> None:
    for i in range(4):
        conn.execute(
            "INSERT INTO alerts (alert_id, vessel_id, ts, kind, level, text)"
            " VALUES (%s, 'OC-T', now() + %s * interval '1 min', 'fuel_anomaly', 'warn', 'x')",
            [i + 1, i],
        )
    assert [a["alert_id"] for a in recent_alerts(conn, 3)] == [4, 3, 2]
