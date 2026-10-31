"""Recalc gate + optimizer in the streaming driver (ADR-0004): PostGIS in, `routes` out.

Runs after each micro-batch's live-state UPSERT. Reads the vessel's live state, the latest debris
survey and its routes; if the gate fires, plans a new chain and inserts it as `pending` for the
operator. Pure logic lives in routing/; this module is only the database glue.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import psycopg
from currents import CurrentField
from gate import MIN_INTERVAL_S, RouteRef, recalc_reason
from intercept import Position
from planner import PatchObs, plan_chain, predicted_targets, repredict, route_record

log = logging.getLogger("telemetry_stream")

INSERT_ROUTE = """
INSERT INTO routes (vessel_id, status, reason, planned_at, geom, waypoints, targets,
                    energy_kwh, mass_kg, compute_ms)
VALUES (%s, 'pending', %s, to_timestamp(%s), ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s)
ON CONFLICT (vessel_id) WHERE status = 'pending' DO NOTHING
RETURNING route_id
"""

ROUTE_COLS = "route_id, status, extract(epoch FROM planned_at), targets"


def route_ref(row: tuple | None) -> RouteRef | None:
    if row is None:
        return None
    route_id, status, planned, targets = row
    return RouteRef(route_id, status, float(planned), predicted_targets(targets))


class Router:
    def __init__(self, load_field: Callable[[], CurrentField | None]) -> None:
        self._load = load_field
        self._field: CurrentField | None = None
        self._next_load = 0.0  # wall clock; retry a missing export at most once a minute
        self._idle_until: dict[str, float] = {}  # sim time; after a plan found nothing reachable

    def field(self) -> CurrentField | None:
        if self._field is None and time.monotonic() >= self._next_load:
            self._field = self._load()
            self._next_load = time.monotonic() + 60
            if self._field is None:
                log.warning("routing paused: mission currents export missing (run the batch)")
        return self._field

    def step(self, conn: psycopg.Connection, vessel_id: str) -> None:
        field = self.field()
        if field is None:
            return
        state = conn.execute(
            "SELECT extract(epoch FROM event_ts), lat, lon FROM vessel_state WHERE vessel_id = %s",
            [vessel_id],
        ).fetchone()
        if state is None:
            return
        now, pos = float(state[0]), (state[1], state[2])
        patches = {
            r[0]: PatchObs(r[0], float(r[1]), r[2], r[3], r[4], r[5])
            for r in conn.execute(
                "SELECT patch_id, extract(epoch FROM survey_ts), lat, lon, mass_kg, radius_m"
                " FROM debris_patches"
            )
        }
        if not patches or now < self._idle_until.get(vessel_id, 0.0):
            return
        q = f"SELECT {ROUTE_COLS} FROM routes WHERE vessel_id = %s"
        latest = route_ref(
            conn.execute(f"{q} ORDER BY route_id DESC LIMIT 1", [vessel_id]).fetchone()
        )
        active = route_ref(
            conn.execute(
                f"{q} AND status = 'active' ORDER BY route_id DESC LIMIT 1", [vessel_id]
            ).fetchone()
        )
        live = {pid for pid, p in patches.items() if p.mass_kg > 0}

        def again(r: RouteRef) -> list[Position | None]:
            meets = repredict(field, now, pos, [pid for pid, _, _ in r.targets], patches)
            return [None if m is None else (m.lat, m.lon) for m in meets]

        reason = recalc_reason(now, latest, active, live, again)
        if reason is None:
            return
        t0 = time.perf_counter()
        plan = plan_chain(field, now, pos, patches.values())
        ms = (time.perf_counter() - t0) * 1000
        if not plan.targets:
            log.info("gate fired (%s) but no patch is reachable; retry in 30 sim-min", reason)
            self._idle_until[vessel_id] = now + MIN_INTERVAL_S
            return
        rec = route_record(plan)
        row = conn.execute(
            INSERT_ROUTE,
            [
                vessel_id,
                reason,
                now,
                rec["wkt"],
                json.dumps(rec["waypoints"]),
                json.dumps(rec["targets"]),
                rec["energy_kwh"],
                rec["mass_kg"],
                ms,
            ],
        ).fetchone()
        if row:
            log.info(
                "route %d proposed (%s): %s, %.0f kg, %.0f kWh, %.0f ms",
                row[0],
                reason,
                " -> ".join(t["patch_id"] for t in rec["targets"]),
                rec["mass_kg"],
                rec["energy_kwh"],
                ms,
            )
