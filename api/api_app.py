"""Operator API: REST reads of the live state, route and sim-clock actions, and a WebSocket feed.

PostGIS is polled once a second (store.snapshot); `/ws` clients get the full snapshot on connect,
then only the parts that changed plus alerts (live.changes, and new rows of the `alerts` table).
Each poll also applies the human-in-the-loop rules (hitl.step, ADR-0008): autopilot decides a
proposal at once; in manual mode the sim clock is held until the operator decides or the
timeout expires the proposal. Static gold exports (mission currents, hotspots) are read once
from the lake; the analytics export on each request, since the batch job rewrites it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone

import hitl
import numpy as np
import psycopg
import replay
import store
from currents import CurrentField
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from live import Wake, changes
from minio import Minio
from minio.error import S3Error
from oceanclean_common import settings
from oceanclean_common.lake import minio_client
from oceanclean_common.regions import (
    EXPORT_ANALYTICS,
    EXPORT_HOTSPOTS,
    EXPORT_MISSION_GRID,
    HISTORY_BOX,
    MISSION_BOX,
)
from pydantic import BaseModel, Field
from urllib3.exceptions import HTTPError as Urllib3Error

log = logging.getLogger("uvicorn.error")
POLL_S = 1.0
MAX_RATE = 7200.0  # sim seconds per real second (2 sim-hours a second)
EXTEND_S = 60.0  # extra decision time while the operator modifies a proposal
MAX_EXTEND_S = 180.0  # the clock cannot be held indefinitely by extending


class Lake:
    """Gold exports from the batch layer, loaded on first use and then cached."""

    def __init__(self, client: Minio, bucket: str, sim_start: datetime) -> None:
        self.client, self.bucket, self.sim_start = client, bucket, sim_start
        self._field: CurrentField | None = None
        self._hotspots: dict | None = None
        self._replay: dict | None = None

    def _get(self, key: str) -> bytes:
        try:
            return self.client.get_object(self.bucket, key).read()
        except (S3Error, Urllib3Error) as e:
            raise HTTPException(503, f"{key} missing; run the batch profile") from e

    def field(self) -> CurrentField:
        if self._field is None:
            self._field = CurrentField.from_npz(self._get(EXPORT_MISSION_GRID), self.sim_start)
        return self._field

    def hotspots(self) -> dict:
        if self._hotspots is None:
            self._hotspots = json.loads(self._get(EXPORT_HOTSPOTS))
        return self._hotspots

    def replay(self) -> dict:
        """The time slider's parcel drift; computed once (a few seconds), then cached."""
        if self._replay is None:
            parcels = replay.seeds(self.hotspots()["hotspots"], MISSION_BOX)
            self._replay = replay.replay(self.field(), parcels)
        return self._replay

    def warm(self) -> None:
        """Compute the replay ahead of the first request; without the exports, the first request
        computes it instead."""
        with contextlib.suppress(HTTPException):
            self.replay()

    def analytics(self) -> dict | None:
        """The telemetry batch job's export, or None before its first run."""
        try:
            return json.loads(self.client.get_object(self.bucket, EXPORT_ANALYTICS).read())
        except (S3Error, Urllib3Error):
            return None


class Hub:
    """Polls PostGIS, applies the HITL rules, keeps the latest snapshot and the vessel's wake,
    and fans changes and alerts out to /ws."""

    def __init__(self, dsn: str, vessel_id: str, autopilot: bool, timeout_s: float) -> None:
        self.dsn, self.vessel_id = dsn, vessel_id
        self.autopilot, self.timeout_s = autopilot, timeout_s
        self.extra_s: dict[int, float] = {}  # route_id -> decision time added by /extend
        self._extra_lock = threading.Lock()  # the poll thread and /extend both touch extra_s
        self.clients: set[WebSocket] = set()
        self.current: dict | None = None
        self.wake = Wake()
        self._conn: psycopg.Connection | None = None
        self._last_alert_id: int | None = None

    def _poll(self) -> tuple[dict, list[dict]] | None:
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=3)
            conn = self._conn
            snap = store.snapshot(conn, self.vessel_id)
            notes, deadline = self._apply_hitl(conn, snap)
            if notes is not None:  # a decision or a hold changed the state: show the result
                snap = store.snapshot(conn, self.vessel_id)
            snap["hitl"] = self.hitl_part(deadline)
            return snap, (notes or []) + self._new_alerts(conn)
        except psycopg.Error as e:
            log.warning("poll failed, keeping the last snapshot: %s", e)
            if self._conn is not None:
                self._conn.close()
            self._conn = None
            return None

    def _apply_hitl(
        self, conn: psycopg.Connection, snap: dict
    ) -> tuple[list[dict] | None, float | None]:
        """Decide or hold the pending proposal. Returns (alerts, deadline); alerts is None
        when nothing changed."""
        pending = snap["routes"]["pending"]
        rid = None if pending is None else pending["route_id"]
        with self._extra_lock:
            self.extra_s = {k: v for k, v in self.extra_s.items() if k == rid}
            extra = self.extra_s.get(rid, 0.0)
        st = hitl.step(snap, self.autopilot, self.timeout_s, extra, time.time())
        notes: list[dict] | None = None
        if st.action == "accept":
            if store.accept_route(conn, rid, "autopilot") is not None:
                notes = []  # live.changes announces the new active route
                log.info("route %d accepted by autopilot (%s)", rid, pending["reason"])
        elif st.action == "expire":
            if store.expire_route(conn, rid) is not None:
                keeps = "keeps its route" if snap["routes"]["active"] else "loiters"
                text = f"Route {rid} expired: no decision in {self.timeout_s:.0f} s, vessel {keeps}"
                notes = [{"kind": "expired", "level": "warn", "text": text}]
                log.info("route %d expired", rid)
        clock = snap["clock"]
        if clock is not None and clock["hitl_hold"] != st.hold:
            store.set_hitl_hold(conn, self.vessel_id, st.hold)
            notes = notes or []
        return notes, st.deadline if st.action == "hold" else None

    def _new_alerts(self, conn: psycopg.Connection) -> list[dict]:
        """Rows the stream added to `alerts` since the last poll (none from before startup)."""
        if self._last_alert_id is None:
            self._last_alert_id = store.last_alert_id(conn)
            return []
        rows = store.new_alerts(conn, self._last_alert_id)
        if rows:
            self._last_alert_id = rows[-1]["alert_id"]
        return [{k: a[k] for k in ("kind", "level", "text", "ts")} for a in rows]

    def hitl_part(self, deadline: float | None) -> dict:
        when = None if deadline is None else datetime.fromtimestamp(deadline, timezone.utc)
        return {
            "autopilot": self.autopilot,
            "timeout_s": self.timeout_s,
            "deadline": None if when is None else store.iso(when),
        }

    def extend(self, route_id: int) -> float:
        """Add decision time to a pending proposal, up to MAX_EXTEND_S; returns the total."""
        with self._extra_lock:
            total = min(MAX_EXTEND_S, self.extra_s.get(route_id, 0.0) + EXTEND_S)
            self.extra_s[route_id] = total
            return self.extra_s[route_id]

    def full(self) -> dict | None:
        return None if self.current is None else {**self.current, "wake": self.wake.points()}

    async def run(self) -> None:
        while True:
            polled = await asyncio.to_thread(self._poll)
            if polled is not None:
                snap, alerts = polled
                v = snap["vessel"]
                if v is not None:
                    t = settings.parse_utc(v["event_ts"]).timestamp()
                    self.wake.add(t, v["lat"], v["lon"])
                msgs = changes(self.current, snap)
                self.current = snap
                sim_now = (snap["clock"] or {}).get("sim_now")
                msgs += [{"type": "alert", "data": {"ts": sim_now, **a}} for a in alerts]
                for msg in msgs:
                    await self.broadcast(msg)
            await asyncio.sleep(POLL_S)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:  # a closed socket; its handler removes it too
                self.clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    env = os.environ
    app.state.dsn = settings.pg_dsn(env)
    app.state.vessel_id = env["VESSEL_ID"]
    app.state.lake = Lake(minio_client(env), env["LAKE_BUCKET"], settings.sim_start(env))
    threading.Thread(target=app.state.lake.warm, name="replay-warm", daemon=True).start()
    autopilot = {"true": True, "false": False}[env["AUTOPILOT"].lower()]
    app.state.hub = Hub(app.state.dsn, app.state.vessel_id, autopilot, float(env["HITL_TIMEOUT_S"]))
    task = asyncio.create_task(app.state.hub.run())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="OceanClean API", lifespan=lifespan)


def db() -> psycopg.Connection:
    try:
        return psycopg.connect(app.state.dsn, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as e:
        raise HTTPException(503, "PostGIS unavailable") from e


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config() -> dict:
    return {
        "vessel_id": app.state.vessel_id,
        "sim_start": store.iso(app.state.lake.sim_start),
        "mission_box": asdict(MISSION_BOX),
        "history_box": asdict(HISTORY_BOX),
    }


@app.get("/vessel")
def vessel() -> dict:
    """Live state plus the recent wake [[lat, lon], ...] the API has seen."""
    with db() as conn:
        return {
            "vessel": store.vessel(conn, app.state.vessel_id),
            "wake": app.state.hub.wake.points(),
        }


@app.get("/routes/active")
def route_active() -> dict | None:
    with db() as conn:
        return store.route(conn, app.state.vessel_id, "active")


@app.get("/routes/pending")
def route_pending() -> dict | None:
    with db() as conn:
        return store.route(conn, app.state.vessel_id, "pending")


@app.post("/routes/{route_id}/accept")
def route_accept(route_id: int) -> dict:
    with db() as conn:
        route = store.accept_route(conn, route_id)
    if route is None:
        raise HTTPException(409, f"route {route_id} is not pending")
    log.info("route %d accepted", route_id)
    return route


@app.post("/routes/{route_id}/reject")
def route_reject(route_id: int) -> dict:
    with db() as conn:
        route = store.reject_route(conn, route_id)
    if route is None:
        raise HTTPException(409, f"route {route_id} is not pending")
    log.info("route %d rejected", route_id)
    return route


class Modify(BaseModel):
    waypoints: dict[str, tuple[float, float]]  # patch_id -> [lat, lon]


@app.post("/routes/{route_id}/modify")
def route_modify(route_id: int, body: Modify) -> dict:
    """Accept a pending route with operator-moved target waypoints."""
    with db() as conn:
        try:
            route = store.modify_route(conn, route_id, body.waypoints)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    if route is None:
        raise HTTPException(409, f"route {route_id} is not pending")
    log.info("route %d modified and accepted: %s", route_id, sorted(body.waypoints))
    return route


@app.post("/routes/{route_id}/extend")
def route_extend(route_id: int) -> dict:
    """More decision time while the operator drags waypoints (Modify in progress)."""
    with db() as conn:
        pending = store.route(conn, app.state.vessel_id, "pending")
    if pending is None or pending["route_id"] != route_id:
        raise HTTPException(409, f"route {route_id} is not pending")
    return {"route_id": route_id, "extra_s": app.state.hub.extend(route_id)}


class HitlUpdate(BaseModel):
    autopilot: bool


@app.get("/hitl")
def hitl_get() -> dict:
    hub: Hub = app.state.hub
    return (hub.current or {}).get("hitl") or hub.hitl_part(None)


@app.post("/hitl")
def hitl_set(body: HitlUpdate) -> dict:
    """Autopilot on/off; the hub applies it on its next poll (within a second)."""
    hub: Hub = app.state.hub
    hub.autopilot = body.autopilot
    log.info("autopilot %s", "on" if body.autopilot else "off")
    return hub.hitl_part(None)


@app.get("/patches")
def patches() -> list[dict]:
    with db() as conn:
        return store.patches(conn)


@app.get("/hotspots")
def hotspots() -> dict:
    """Gold convergence hotspots (1-degree cells) and the microplastics validation ratio."""
    return app.state.lake.hotspots()


@app.get("/currents/grid")
def currents_grid(t: datetime | None = None) -> dict:
    """The mission u/v grid (m/s, rows = lat ascending) at sim time t, default the sim clock."""
    if t is not None and t.utcoffset() is None:
        raise HTTPException(422, "t must carry a UTC offset or Z")
    field = app.state.lake.field()
    if t is None:
        with db() as conn:
            clock = store.sim_clock(conn, app.state.vessel_id)
        t = settings.parse_utc(clock["sim_now"]) if clock else app.state.lake.sim_start
    u, v = field.grid_at(t.timestamp())
    return {
        "t": store.iso(t),
        "lat": field.lat.round(4).tolist(),
        "lon": field.lon.round(4).tolist(),
        "u": np.round(u, 4).tolist(),
        "v": np.round(v, 4).tolist(),
    }


@app.get("/replay")
def replay_frames() -> dict:
    """Time slider: parcels from the mission-box hotspots drifting through the window's real
    daily currents, one frame per 6 sim-hours; fetch a frame's grid with /currents/grid?t=."""
    return app.state.lake.replay()


class ClockUpdate(BaseModel):
    rate: float | None = Field(None, ge=1.0, le=MAX_RATE)
    paused: bool | None = None


@app.get("/sim/clock")
def sim_clock_get() -> dict:
    with db() as conn:
        clock = store.sim_clock(conn, app.state.vessel_id)
    if clock is None:
        raise HTTPException(404, "the simulator has not reported its clock yet")
    return clock


@app.post("/sim/clock")
def sim_clock_set(body: ClockUpdate) -> dict:
    """Play/pause and speed; the simulator adopts them within a second."""
    with db() as conn:
        clock = store.set_sim_clock(conn, app.state.vessel_id, body.rate, body.paused)
    if clock is None:
        raise HTTPException(409, "the simulator has not reported its clock yet")
    log.info("sim clock set: rate=%s paused=%s", clock["rate"], clock["paused"])
    return clock


class Fault(BaseModel):
    hours: float = Field(6.0, gt=0, le=48)


@app.post("/sim/fault")
def sim_fault(body: Fault) -> dict:
    """Inject a fuel leak for `hours` of sim time (the anomaly demo)."""
    with db() as conn:
        until = store.set_fuel_leak(conn, app.state.vessel_id, body.hours)
    if until is None:
        raise HTTPException(409, "the simulator has not reported its clock yet")
    log.info("fuel leak injected until %s", until)
    return {"fuel_leak_until": until}


@app.get("/metrics")
def metrics(minutes: float = 15.0, hours: float = 48.0) -> dict:
    """Admin view: stream query metrics over `minutes` of wall time, lake row counts, the
    last `hours` sim hours of energy, debris, fuel and battery from the 5-minute windows, and
    the newest alerts."""
    if not (1 <= minutes <= 24 * 60 and 1 <= hours <= 24 * 30):
        raise HTTPException(422, "minutes must be 1..1440 and hours 1..720")
    bucket_s = max(2, round(minutes * 60 / 150))  # about 150 points per chart
    with db() as conn:
        out = store.metrics_series(conn, minutes, bucket_s)
        out["hourly"] = store.hourly_windows(conn, app.state.vessel_id, hours)
        out["alerts"] = store.recent_alerts(conn, 8)
    return {**out, "bucket_s": bucket_s}


@app.get("/analytics")
def analytics() -> dict:
    """Gold telemetry aggregates (debris per kWh by day and zone), route acceptance and the
    hotspot validation ratio."""
    with db() as conn:
        counts = store.decision_counts(conn, app.state.vessel_id)
    try:
        validation = app.state.lake.hotspots()["validation"]
    except HTTPException:
        validation = None
    return {
        "telemetry": app.state.lake.analytics(),
        "decisions": counts,
        "acceptance": hitl.acceptance_rates(counts),
        "validation": validation,
    }


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    hub: Hub = app.state.hub
    await socket.accept()
    full = hub.full()
    if full is not None:
        await socket.send_json({"type": "snapshot", "data": full})
    hub.clients.add(socket)
    try:
        while True:
            await socket.receive_text()  # clients don't send; this waits for the disconnect
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(socket)
