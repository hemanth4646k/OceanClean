"""PostGIS writes of the M5 speed-layer additions: scored windows, anomaly alerts, lake row
counts and query metrics. No Spark here, so tests run it against the Compose PostGIS."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

import psycopg
from anomaly import HISTORY_N, Scored, Tail, WindowAgg, score

TAIL_SQL = """
SELECT DISTINCT ON (vessel_id) vessel_id, last_ts, fuel_l, battery_pct, hold_fill_pct, anomaly
FROM telemetry_windows WHERE vessel_id = ANY(%s) ORDER BY vessel_id, window_end DESC
"""
HISTORY_SQL = """
SELECT residual FROM (
  SELECT residual, window_end FROM telemetry_windows
  WHERE vessel_id = %s AND residual IS NOT NULL AND NOT anomaly
  ORDER BY window_end DESC LIMIT %s
) recent ORDER BY window_end
"""
INSERT_WINDOW_SQL = """
INSERT INTO telemetry_windows (vessel_id, window_end, last_ts, n, fuel_l, battery_pct,
  hold_fill_pct, energy_kwh, expected_kwh, collected_kg, residual, z, anomaly)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (vessel_id, window_end) DO NOTHING
"""
INSERT_ALERT_SQL = """
INSERT INTO alerts (vessel_id, ts, kind, level, text, detail)
VALUES (%s, %s, 'fuel_anomaly', 'warn', %s, %s)
ON CONFLICT (vessel_id, kind, ts) DO NOTHING
"""
ADD_LAKE_ROWS_SQL = """
INSERT INTO lake_counts (dataset, rows, updated_at) VALUES (%s, %s, now())
ON CONFLICT (dataset) DO UPDATE SET rows = lake_counts.rows + EXCLUDED.rows, updated_at = now()
"""
INSERT_METRICS_SQL = """
INSERT INTO pipeline_metrics (ts, query, batch_id, input_rows, input_rps, processed_rps,
  duration_ms, kafka_lag) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def alert_text(s: Scored) -> str:
    pct = round(100 * (s.residual or 0.0))
    return f"Fuel burn {pct}% above the power model on {s.agg.vessel_id} (z = {s.z:.1f})"


def _window_params(s: Scored) -> tuple[object, ...]:
    a = s.agg
    return (
        a.vessel_id,
        a.window_end,
        a.last_ts,
        a.n,
        a.fuel_l,
        a.battery_pct,
        a.hold_fill_pct,
        s.energy_kwh,
        s.expected_kwh,
        s.collected_kg,
        s.residual,
        s.z,
        s.anomaly,
    )


def _store_scored(conn: psycopg.Connection, scored: Iterable[Scored]) -> int:
    n_alerts = 0
    for s in scored:
        conn.execute(INSERT_WINDOW_SQL, _window_params(s))
        if s.onset:
            detail = {"residual": s.residual, "z": s.z, "window_end": s.agg.window_end.isoformat()}
            cur = conn.execute(
                INSERT_ALERT_SQL,
                (s.agg.vessel_id, s.agg.last_ts, alert_text(s), json.dumps(detail)),
            )
            n_alerts += cur.rowcount
    return n_alerts


def store_windows(conn: psycopg.Connection, windows: Sequence[WindowAgg], tick_s: float) -> int:
    """Score newly closed windows against each vessel's stored tail and history, insert them,
    and raise one alert per anomaly onset. Returns the number of new alerts.

    A retried batch is harmless: its windows are not newer than the stored tail, so they score
    as "no baseline", and both inserts ignore rows that already exist.
    """
    by_vessel: dict[str, list[WindowAgg]] = {}
    for w in sorted(windows, key=lambda w: (w.vessel_id, w.window_end)):
        by_vessel.setdefault(w.vessel_id, []).append(w)
    tails = {r[0]: Tail(*r[1:]) for r in conn.execute(TAIL_SQL, (list(by_vessel),)).fetchall()}
    n_alerts = 0
    for vessel, ws in by_vessel.items():
        history = [r[0] for r in conn.execute(HISTORY_SQL, (vessel, HISTORY_N)).fetchall()]
        n_alerts += _store_scored(conn, score(tails.get(vessel), ws, history, tick_s))
    return n_alerts


def add_lake_rows(conn: psycopg.Connection, dataset: str, rows: int) -> None:
    """Count rows a stream appended to a lake dataset (a retried batch counts twice)."""
    conn.execute(ADD_LAKE_ROWS_SQL, (dataset, rows))


def insert_metrics(conn: psycopg.Connection, row: tuple[object, ...]) -> None:
    conn.execute(INSERT_METRICS_SQL, row)
