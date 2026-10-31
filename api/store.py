"""PostGIS reads for the API and the operator's route and clock actions, as JSON-ready dicts.

The API owns the route transitions (ADR-0007): pending -> active | rejected, and the previous
active route -> superseded in the same transaction as an accept.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

VESSEL_COLS = (
    "vessel_id, event_ts, seq, lat, lon, heading_deg, speed_kn, battery_pct, fuel_l,"
    " debris_density, hold_fill_pct, buffered"
)
ROUTE_COLS = (
    "route_id, vessel_id, status, reason, planned_at, created_at, decided_at, energy_kwh,"
    " mass_kg, compute_ms, waypoints, targets"
)
PATCH_COLS = "patch_id, survey_ts, lat, lon, mass_kg, radius_m"
CLOCK_COLS = "vessel_id, sim_now, rate, paused, reported_at"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: iso(v) if isinstance(v, datetime) else v for k, v in row.items()}


def _one(conn: psycopg.Connection, sql: str, params: list) -> dict | None:
    return _json(conn.cursor(row_factory=dict_row).execute(sql, params).fetchone())


def vessel(conn: psycopg.Connection, vessel_id: str) -> dict | None:
    return _one(conn, f"SELECT {VESSEL_COLS} FROM vessel_state WHERE vessel_id = %s", [vessel_id])


def patches(conn: psycopg.Connection) -> list[dict]:
    """Every surveyed patch, collected ones (mass 0) included so the map can fade them."""
    cur = conn.cursor(row_factory=dict_row)
    return [
        _json(r) for r in cur.execute(f"SELECT {PATCH_COLS} FROM debris_patches ORDER BY patch_id")
    ]


def route(conn: psycopg.Connection, vessel_id: str, status: str) -> dict | None:
    return _one(
        conn,
        f"SELECT {ROUTE_COLS} FROM routes WHERE vessel_id = %s AND status = %s"
        " ORDER BY route_id DESC LIMIT 1",
        [vessel_id, status],
    )


def accept_route(conn: psycopg.Connection, route_id: int) -> dict | None:
    """Activate a pending route, superseding the vessel's active one; None if not pending."""
    with conn.transaction():
        row = conn.execute(
            "SELECT vessel_id FROM routes WHERE route_id = %s AND status = 'pending' FOR UPDATE",
            [route_id],
        ).fetchone()
        if row is None:
            return None
        # Supersede first: the one-active partial unique index rejects two active rows.
        conn.execute(
            "UPDATE routes SET status = 'superseded', decided_at = now()"
            " WHERE vessel_id = %s AND status = 'active'",
            [row[0]],
        )
        return _one(
            conn,
            f"UPDATE routes SET status = 'active', decided_at = now() WHERE route_id = %s"
            f" RETURNING {ROUTE_COLS}",
            [route_id],
        )


def reject_route(conn: psycopg.Connection, route_id: int) -> dict | None:
    """Reject a pending route; the vessel keeps its active route or loiters. None if not pending."""
    return _one(
        conn,
        f"UPDATE routes SET status = 'rejected', decided_at = now()"
        f" WHERE route_id = %s AND status = 'pending' RETURNING {ROUTE_COLS}",
        [route_id],
    )


def sim_clock(conn: psycopg.Connection, vessel_id: str) -> dict | None:
    return _one(conn, f"SELECT {CLOCK_COLS} FROM sim_clock WHERE vessel_id = %s", [vessel_id])


def set_sim_clock(
    conn: psycopg.Connection,
    vessel_id: str,
    rate: float | None = None,
    paused: bool | None = None,
) -> dict | None:
    """Set the simulator's rate and/or pause; None until the simulator has reported its clock."""
    return _one(
        conn,
        "UPDATE sim_clock SET rate = coalesce(%s::float8, rate),"
        " paused = coalesce(%s::boolean, paused)"
        f" WHERE vessel_id = %s RETURNING {CLOCK_COLS}",
        [rate, paused, vessel_id],
    )


def snapshot(conn: psycopg.Connection, vessel_id: str) -> dict:
    """Everything the live map shows that changes with the sim (see live.py)."""
    return {
        "vessel": vessel(conn, vessel_id),
        "patches": patches(conn),
        "routes": {
            "active": route(conn, vessel_id, "active"),
            "pending": route(conn, vessel_id, "pending"),
        },
        "clock": sim_clock(conn, vessel_id),
    }
