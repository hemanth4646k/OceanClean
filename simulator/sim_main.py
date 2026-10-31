"""Simulator entrypoint: sim clock, debris world, route follower, telemetry and surveys.

Each tick moves the vessel along the active route (read from PostGIS) or loiters, collects and
offloads debris, drifts the patches through the mission currents and emits one telemetry event.
Telemetry goes through the offline link; a debris survey goes out every 60 sim-minutes.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg
import sim_state
from currents import CurrentField
from debris import seed_patches
from minio import Minio
from minio.error import S3Error
from oceanclean_common import settings
from oceanclean_common.debris import PatchSurvey
from oceanclean_common.regions import EXPORT_HOTSPOTS, EXPORT_MISSION_GRID, MISSION_BOX
from oceanclean_common.telemetry import Telemetry
from sim_clock import SimClock
from urllib3.exceptions import HTTPError as Urllib3Error
from vessel import VesselState
from world import SURVEY_EVERY_S, RouteTargets, World, tick, waypoint_targets

log = logging.getLogger("simulator")

N_PATCHES = 40  # ~26 sim-days to clear with instant accepts; operator time adds more
WORLD_SEED = 20261101
ROUTE_POLL_S = 3.0  # real seconds between active-route reads
START = (35.0, -142.0)


def to_telemetry(v: VesselState, ts: datetime, buffered: bool = False) -> Telemetry:
    return Telemetry(
        vessel_id=v.vessel_id,
        event_ts=ts,
        seq=v.seq,
        lat=v.lat,
        lon=v.lon,
        heading_deg=v.heading_deg % 360,
        speed_kn=v.speed_kn,
        battery_pct=v.battery_pct,
        fuel_l=v.fuel_l,
        debris_density=v.debris_density,
        hold_fill_pct=v.hold_fill_pct,
        buffered=buffered,
    )


def surveys(w: World, ts: datetime) -> list[PatchSurvey]:
    return [
        PatchSurvey(
            patch_id=p.patch_id,
            survey_ts=ts,
            lat=p.lat,
            lon=p.lon,
            mass_kg=p.mass_kg,
            radius_m=p.radius_m,
        )
        for p in w.patches
    ]


def load_exports(client: Minio, bucket: str, sim_start: datetime) -> tuple[CurrentField, dict]:
    """Mission currents and hotspots from the batch layer; waits until the ETL has run."""
    while True:
        try:
            grid = client.get_object(bucket, EXPORT_MISSION_GRID).read()
            hotspots = json.loads(client.get_object(bucket, EXPORT_HOTSPOTS).read())
            return CurrentField.from_npz(grid, sim_start), hotspots
        except (S3Error, Urllib3Error) as e:
            log.warning("waiting for gold exports (run the batch profile): %s", e)
            time.sleep(10)


class RouteSource:
    """The active route's target waypoints, polled from PostGIS; keeps the last one on errors."""

    def __init__(self, dsn: str, vessel_id: str) -> None:
        self.dsn, self.vessel_id = dsn, vessel_id
        self.route_id: int | None = None
        self.targets: RouteTargets | None = None

    def poll(self) -> None:
        try:
            with psycopg.connect(self.dsn, connect_timeout=3) as conn:
                row = conn.execute(
                    "SELECT route_id, waypoints FROM routes WHERE vessel_id = %s"
                    " AND status = 'active' ORDER BY route_id DESC LIMIT 1",
                    [self.vessel_id],
                ).fetchone()
        except psycopg.Error as e:
            log.warning("route poll failed, keeping route %s: %s", self.route_id, e)
            return
        route_id = row[0] if row else None
        if route_id != self.route_id:
            log.info("active route %s -> %s", self.route_id, route_id)
        self.route_id = route_id
        self.targets = waypoint_targets(row[1]) if row else None


def post_json(client: httpx.Client, url: str, items: list[str]) -> bool:
    try:
        client.post(
            url, content="[" + ",".join(items) + "]", headers={"content-type": "application/json"}
        ).raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("POST %s failed (%d items): %s", url, len(items), e)
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per POST otherwise
    env = os.environ
    vessel_id = env["VESSEL_ID"]
    state_file = Path(env["SIM_STATE_DIR"]) / f"{vessel_id}.json"
    ingest_url, survey_url = env["INGEST_URL"], env["SURVEY_URL"]
    tick_sim_s = float(env["SIM_TICK_SECONDS"])  # sim seconds between telemetry ticks
    sim_start = settings.sim_start(env)
    minio = Minio(
        env["MINIO_ENDPOINT"],
        access_key=env["MINIO_ROOT_USER"],
        secret_key=env["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
    field, hotspots = load_exports(minio, env["LAKE_BUCKET"], sim_start)

    resumed = sim_state.load(state_file)
    world: World | None = None
    if resumed:
        start, v, world_doc = resumed
        world = World.from_dict(world_doc) if world_doc else None
        log.info("resuming at %s seq=%d", start.isoformat(), v.seq)
    else:
        start = sim_start
        v = VesselState(vessel_id, lat=START[0], lon=START[1], heading_deg=90.0, speed_kn=0.0)
    if world is None:
        world = World(
            seed_patches(hotspots["hotspots"], MISSION_BOX, N_PATCHES, random.Random(WORLD_SEED))
        )
        total = sum(p.mass_kg for p in world.patches)
        log.info("seeded %d patches, %.0f t, from mission-box hotspots", N_PATCHES, total / 1000)
    rng = random.Random(f"{WORLD_SEED}:{v.seq}")  # reproducible, and fresh after a restart

    clock = SimClock(start, rate=float(env["SIM_RATE"]))
    client = httpx.Client(timeout=5)
    routes = RouteSource(settings.pg_dsn(env), vessel_id)
    next_tick = clock.now
    last = last_poll = time.monotonic()
    routes.poll()
    while True:
        now = time.monotonic()
        clock.advance(now - last)
        last = now
        fresh: list[Telemetry] = []
        survey: list[PatchSurvey] = []
        while clock.now >= next_tick:
            t = next_tick.timestamp()
            if world.link.maybe_drop(t, tick_sim_s, rng):
                log.info(
                    "link down until %s",
                    datetime.fromtimestamp(world.link.offline_until, timezone.utc),
                )
            tick(world, v, t - tick_sim_s, tick_sim_s, field, routes.targets, rng)
            v.seq += 1
            fresh.append(to_telemetry(v, next_tick.astimezone(timezone.utc)))
            if t >= world.next_survey:
                survey = surveys(world, next_tick.astimezone(timezone.utc))
                world.next_survey = t + SURVEY_EVERY_S
            next_tick += timedelta(seconds=tick_sim_s)
        if not fresh:
            time.sleep(0.1)
            continue
        t_now = fresh[-1].event_ts.timestamp()
        backlog = len(world.link.queue)
        sent = world.link.flush(
            t_now, fresh, lambda batch: post_json(client, ingest_url, [e.to_json() for e in batch])
        )
        if backlog and sent > len(fresh):
            log.info("link up: flushed %d buffered events", sent - len(fresh))
        # A survey is a snapshot: one missed while offline is superseded by the next.
        if survey and world.link.online(t_now):
            post_json(client, survey_url, [s.to_json() for s in survey])
        sim_state.save(state_file, next_tick, v, world.to_dict())
        if now - last_poll >= ROUTE_POLL_S and world.link.online(t_now):
            routes.poll()
            last_poll = now
        time.sleep(0.1)


if __name__ == "__main__":
    main()
