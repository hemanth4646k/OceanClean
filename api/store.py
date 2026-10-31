"""PostGIS reads for the API and the operator's route and clock actions, as JSON-ready dicts.

The API owns the route transitions (ADR-0007, ADR-0008): pending -> active | rejected | expired,
and the previous active route -> superseded in the same transaction as an accept or modify.
`decided_by` records who decided: operator, autopilot or timeout.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

VESSEL_COLS = (
    "vessel_id, event_ts, seq, lat, lon, heading_deg, speed_kn, battery_pct, fuel_l,"
    " debris_density, hold_fill_pct, buffered"
)
ROUTE_COLS = (
    "route_id, vessel_id, status, reason, planned_at, created_at, decided_at, energy_kwh,"
    " mass_kg, compute_ms, waypoints, targets, decided_by"
)
PATCH_COLS = "patch_id, survey_ts, lat, lon, mass_kg, radius_m"
CLOCK_COLS = "vessel_id, sim_now, rate, paused, hitl_hold, reported_at"
ALERT_COLS = "alert_id, ts, kind, level, text, detail"


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


def _activate(
    conn: psycopg.Connection, route_id: int, by: str, waypoints: list | None = None
) -> dict | None:
    """Pending -> active (optionally with new waypoints), superseding the active route."""
    with conn.transaction():
        row = conn.execute(
            "SELECT vessel_id, waypoints FROM routes"
            " WHERE route_id = %s AND status = 'pending' FOR UPDATE",
            [route_id],
        ).fetchone()
        if row is None:
            return None
        if waypoints is not None and len(waypoints) != len(row[1]):
            raise ValueError("waypoints must keep the route's length")
        # Supersede first: the one-active partial unique index rejects two active rows.
        conn.execute(
            "UPDATE routes SET status = 'superseded', decided_at = now()"
            " WHERE vessel_id = %s AND status = 'active'",
            [row[0]],
        )
        new = row[1] if waypoints is None else waypoints
        line = "LINESTRING(" + ", ".join(f"{w['lon']} {w['lat']}" for w in new) + ")"
        return _one(
            conn,
            "UPDATE routes SET status = 'active', decided_at = now(), decided_by = %s,"
            " waypoints = %s, geom = ST_GeomFromText(%s, 4326)"
            f" WHERE route_id = %s RETURNING {ROUTE_COLS}",
            [by, Jsonb(new), line, route_id],
        )


def accept_route(conn: psycopg.Connection, route_id: int, by: str = "operator") -> dict | None:
    """Activate a pending route, superseding the vessel's active one; None if not pending."""
    return _activate(conn, route_id, by)


def modify_route(
    conn: psycopg.Connection, route_id: int, moves: Mapping[str, tuple[float, float]]
) -> dict | None:
    """Accept a pending route with operator-moved target waypoints {patch_id: (lat, lon)}.

    Only waypoints move; `targets` keep the optimizer's predictions, which the gate re-checks.
    """
    row = conn.execute(
        "SELECT waypoints FROM routes WHERE route_id = %s AND status = 'pending'", [route_id]
    ).fetchone()
    if row is None:
        return None
    ids = {w.get("patch_id") for w in row[0] if w["kind"] == "target"}
    if not set(moves) <= ids:
        raise ValueError(f"not targets of route {route_id}: {sorted(set(moves) - ids)}")
    waypoints = [
        {**w, "lat": moves[w["patch_id"]][0], "lon": moves[w["patch_id"]][1]}
        if w.get("patch_id") in moves
        else w
        for w in row[0]
    ]
    return _activate(conn, route_id, "operator", waypoints)


def _close(conn: psycopg.Connection, route_id: int, status: str, by: str) -> dict | None:
    return _one(
        conn,
        f"UPDATE routes SET status = %s, decided_at = now(), decided_by = %s"
        f" WHERE route_id = %s AND status = 'pending' RETURNING {ROUTE_COLS}",
        [status, by, route_id],
    )


def reject_route(conn: psycopg.Connection, route_id: int, by: str = "operator") -> dict | None:
    """Reject a pending route; the vessel keeps its active route or loiters. None if not pending."""
    return _close(conn, route_id, "rejected", by)


def expire_route(conn: psycopg.Connection, route_id: int) -> dict | None:
    """Nobody decided within the timeout: as a reject, recorded as the timeout's."""
    return _close(conn, route_id, "expired", "timeout")


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


def set_hitl_hold(conn: psycopg.Connection, vessel_id: str, hold: bool) -> dict | None:
    """Hold (or release) the sim clock for a pending proposal; independent of the operator pause."""
    return _one(
        conn,
        f"UPDATE sim_clock SET hitl_hold = %s WHERE vessel_id = %s RETURNING {CLOCK_COLS}",
        [hold, vessel_id],
    )


def set_fuel_leak(conn: psycopg.Connection, vessel_id: str, hours: float) -> str | None:
    """Inject a fuel leak for `hours` of sim time from now; returns its end (sim time)."""
    row = conn.execute(
        "INSERT INTO sim_faults (vessel_id, fuel_leak_until)"
        " SELECT vessel_id, sim_now + %s * interval '1 hour' FROM sim_clock WHERE vessel_id = %s"
        " ON CONFLICT (vessel_id) DO UPDATE SET fuel_leak_until = excluded.fuel_leak_until"
        " RETURNING fuel_leak_until",
        [hours, vessel_id],
    ).fetchone()
    return None if row is None else iso(row[0])


def new_alerts(conn: psycopg.Connection, after_id: int) -> list[dict]:
    sql = f"SELECT {ALERT_COLS} FROM alerts WHERE alert_id > %s ORDER BY alert_id"
    return _all(conn, sql, [after_id])


def recent_alerts(conn: psycopg.Connection, n: int) -> list[dict]:
    """The newest `n` alerts, newest first (the Metrics tab's list)."""
    return _all(conn, f"SELECT {ALERT_COLS} FROM alerts ORDER BY alert_id DESC LIMIT %s", [n])


def last_alert_id(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT coalesce(max(alert_id), 0) FROM alerts").fetchone()[0]


def _all(conn: psycopg.Connection, sql: str, params: list) -> list[dict]:
    return [_json(r) for r in conn.cursor(row_factory=dict_row).execute(sql, params)]


def metrics_series(conn: psycopg.Connection, minutes: float, bucket_s: int) -> dict:
    """Stream query metrics over the last `minutes` of wall time, in `bucket_s` buckets, plus
    the latest micro-batch of each query and the lake's row counts."""
    series = _all(
        conn,
        "SELECT date_bin(%s * interval '1 s', ts, timestamptz '2000-01-01') AS t, query,"
        " sum(input_rows)::float8 / %s AS rows_per_s, avg(duration_ms) AS duration_ms,"
        " max(kafka_lag) AS kafka_lag"
        " FROM pipeline_metrics WHERE ts > now() - %s * interval '1 minute'"
        " GROUP BY 1, 2 ORDER BY 1, 2",
        [bucket_s, bucket_s, minutes],
    )
    latest = _all(
        conn,
        "SELECT DISTINCT ON (query) ts, query, batch_id, input_rows, input_rps, processed_rps,"
        " duration_ms, kafka_lag FROM pipeline_metrics ORDER BY query, ts DESC",
        [],
    )
    lake = _all(conn, "SELECT dataset, rows, updated_at FROM lake_counts ORDER BY dataset", [])
    return {"series": series, "latest": latest, "lake": lake}


def hourly_windows(conn: psycopg.Connection, vessel_id: str, hours: float) -> list[dict]:
    """Energy, debris, last fuel/battery and anomalies per sim hour (by window start), for the
    last `hours` sim hours of 5-minute windows."""
    return _all(
        conn,
        "SELECT date_trunc('hour', window_end - interval '5 min', 'UTC') AS hour,"
        " sum(energy_kwh) AS energy_kwh, sum(collected_kg) AS collected_kg,"
        " (array_agg(fuel_l ORDER BY window_end DESC))[1] AS fuel_l,"
        " (array_agg(battery_pct ORDER BY window_end DESC))[1] AS battery_pct,"
        " count(*) FILTER (WHERE anomaly) AS anomalies"
        " FROM telemetry_windows WHERE vessel_id = %s AND window_end >"
        " (SELECT max(window_end) FROM telemetry_windows WHERE vessel_id = %s)"
        " - %s * interval '1 hour'"
        " GROUP BY 1 ORDER BY 1",
        [vessel_id, vessel_id, hours],
    )


def decision_counts(conn: psycopg.Connection, vessel_id: str) -> list[dict]:
    """Decided routes by who decided and the outcome; routes decided before M5 recorded no
    decider, and only the operator decided then."""
    return _all(
        conn,
        "SELECT coalesce(decided_by, 'operator') AS by, status, count(*) AS n FROM routes"
        " WHERE vessel_id = %s AND status <> 'pending' GROUP BY 1, 2 ORDER BY 1, 2",
        [vessel_id],
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
