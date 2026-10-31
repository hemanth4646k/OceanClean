"""Operator API: REST reads of the live state, route and sim-clock actions, and a WebSocket feed.

PostGIS is polled once a second (store.snapshot); `/ws` clients get the full snapshot on connect,
then only the parts that changed plus alerts (live.changes). Static gold exports (mission
currents, hotspots) are read once from the lake.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime

import numpy as np
import psycopg
import store
from currents import CurrentField
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from live import Wake, changes
from minio import Minio
from minio.error import S3Error
from oceanclean_common import settings
from oceanclean_common.lake import minio_client
from oceanclean_common.regions import EXPORT_HOTSPOTS, EXPORT_MISSION_GRID, HISTORY_BOX, MISSION_BOX
from pydantic import BaseModel, Field
from urllib3.exceptions import HTTPError as Urllib3Error

log = logging.getLogger("uvicorn.error")
POLL_S = 1.0
MAX_RATE = 7200.0  # sim seconds per real second (2 sim-hours a second)


class Lake:
    """Gold exports from the batch layer, loaded on first use and then cached."""

    def __init__(self, client: Minio, bucket: str, sim_start: datetime) -> None:
        self.client, self.bucket, self.sim_start = client, bucket, sim_start
        self._field: CurrentField | None = None
        self._hotspots: dict | None = None

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


class Hub:
    """Polls PostGIS, keeps the latest snapshot and the vessel's wake, fans changes out to /ws."""

    def __init__(self, dsn: str, vessel_id: str) -> None:
        self.dsn, self.vessel_id = dsn, vessel_id
        self.clients: set[WebSocket] = set()
        self.current: dict | None = None
        self.wake = Wake()
        self._conn: psycopg.Connection | None = None

    def _poll(self) -> dict | None:
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=3)
            return store.snapshot(self._conn, self.vessel_id)
        except psycopg.Error as e:
            log.warning("poll failed, keeping the last snapshot: %s", e)
            if self._conn is not None:
                self._conn.close()
            self._conn = None
            return None

    def full(self) -> dict | None:
        return None if self.current is None else {**self.current, "wake": self.wake.points()}

    async def run(self) -> None:
        while True:
            snap = await asyncio.to_thread(self._poll)
            if snap is not None:
                v = snap["vessel"]
                if v is not None:
                    t = settings.parse_utc(v["event_ts"]).timestamp()
                    self.wake.add(t, v["lat"], v["lon"])
                msgs = changes(self.current, snap)
                self.current = snap
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
    app.state.hub = Hub(app.state.dsn, app.state.vessel_id)
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
