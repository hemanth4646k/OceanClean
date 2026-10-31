"""Route transitions against the Compose PostGIS, on a temp copy of `routes` (live rows untouched).

Skipped unless POSTGRES_* are set: CLAUDE.md Commands runs pytest with `--network
oceanclean_default --env-file .env.example` so these run against the stack.
"""

import os
from collections.abc import Iterator

import psycopg
import pytest
from oceanclean_common.settings import pg_dsn
from store import accept_route, reject_route, set_sim_clock, sim_clock

pytestmark = pytest.mark.skipif("POSTGRES_HOST" not in os.environ, reason="needs PostGIS")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_dsn(os.environ), autocommit=True) as c:
        # Temp tables shadow public ones for this session; LIKE copies checks and the
        # one-pending / one-active partial unique indexes.
        c.execute("CREATE TEMP TABLE routes (LIKE public.routes INCLUDING ALL)")
        c.execute("CREATE TEMP TABLE sim_clock (LIKE public.sim_clock INCLUDING ALL)")
        yield c


def add(conn: psycopg.Connection, route_id: int, status: str, vessel: str = "OC-T") -> None:
    conn.execute(
        "INSERT INTO routes (route_id, vessel_id, status, reason, planned_at, geom, waypoints,"
        " targets, energy_kwh, mass_kg, compute_ms) VALUES (%s, %s, %s, 'no_route', now(),"
        " ST_GeomFromText('LINESTRING(-142 35, -141 35)', 4326), '[]', '[]', 1, 1, 1)",
        [route_id, vessel, status],
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
    route = accept_route(conn, 2)
    assert route is not None and route["status"] == "active" and route["decided_at"]
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
    conn.execute(
        "INSERT INTO sim_clock (vessel_id, sim_now, rate, paused)"
        " VALUES ('OC-T', '2026-09-01T06:00:00Z', 60, false)"
    )
    clock = set_sim_clock(conn, "OC-T", paused=True)
    assert clock == {**clock, "rate": 60.0, "paused": True, "sim_now": "2026-09-01T06:00:00Z"}
    clock = set_sim_clock(conn, "OC-T", rate=600.0)
    assert clock is not None and (clock["rate"], clock["paused"]) == (600.0, True)
