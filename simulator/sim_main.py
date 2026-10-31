"""Simulator entrypoint: sim clock, debris world, route follower, telemetry and surveys.

Each tick moves the vessel along the active route (read from PostGIS) or loiters, collects and
offloads debris, drifts the patches through the mission currents and emits one telemetry event.
Telemetry goes through the offline link; a debris survey goes out every 60 sim-minutes.

`--fast-forward 30d [--tick 1]` instead bursts the previous mission's history and exits
(backfill.py).
"""

from __future__ import annotations

import argparse
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
from backfill import (
    HISTORY_SEED,
    LIVE_SEQ_START,
    Autopilot,
    burst,
    chunks,
    history,
    live_ready,
    parse_duration,
)
from currents import CurrentField
from debris import seed_patches
from minio import Minio
from minio.error import S3Error
from oceanclean_common import settings
from oceanclean_common.debris import PatchSurvey
from oceanclean_common.lake import minio_client
from oceanclean_common.regions import EXPORT_HOTSPOTS, EXPORT_MISSION_GRID, MISSION_BOX
from oceanclean_common.telemetry import Telemetry
from sim_clock import SimClock
from urllib3.exceptions import HTTPError as Urllib3Error
from vessel import VesselState
from world import SURVEY_EVERY_S, RouteTargets, World, tick, to_telemetry, waypoint_targets

log = logging.getLogger("simulator")

N_PATCHES = 40  # ~26 sim-days to clear with instant accepts; operator time adds more
WORLD_SEED = 20261101
ROUTE_POLL_S = 3.0  # real seconds between active-route reads
CLOCK_SYNC_S = 1.0  # real seconds between clock reports / control reads
START = (35.0, -142.0)
LEAK_FACTOR = 1.5  # fuel lost per unit of power during an injected leak (POST /sim/fault)


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


class ClockControl:
    """Reports the sim clock to PostGIS and adopts the operator's rate and pause (API), the hold
    while a route proposal awaits the operator, and any injected fuel leak.

    This is the simulation harness, not the vessel's uplink, so it runs during link outages too.
    """

    SYNC = """
    INSERT INTO sim_clock (vessel_id, sim_now, rate, paused) VALUES (%s, %s, %s, false)
    ON CONFLICT (vessel_id) DO UPDATE SET sim_now = excluded.sim_now, reported_at = now()
    RETURNING rate, paused OR hitl_hold,
              (SELECT fuel_leak_until FROM sim_faults WHERE vessel_id = sim_clock.vessel_id)
    """

    def __init__(self, dsn: str, vessel_id: str) -> None:
        self.dsn, self.vessel_id = dsn, vessel_id
        self.leak_until: datetime | None = None

    def fuel_factor(self, now: datetime) -> float:
        return LEAK_FACTOR if self.leak_until is not None and now < self.leak_until else 1.0

    def sync(self, clock: SimClock) -> None:
        try:
            with psycopg.connect(self.dsn, connect_timeout=3) as conn:
                row = conn.execute(self.SYNC, [self.vessel_id, clock.now, clock.rate]).fetchone()
        except psycopg.Error as e:
            log.warning(
                "clock sync failed, keeping rate %s paused=%s: %s", clock.rate, clock.paused, e
            )
            return
        assert row is not None
        rate, paused = float(row[0]), bool(row[1])
        if row[2] != self.leak_until:
            log.info("fuel leak until %s", row[2])
            self.leak_until = row[2]
        if (rate, paused) != (clock.rate, clock.paused):
            log.info(
                "sim clock: rate %s -> %s, paused %s -> %s", clock.rate, rate, clock.paused, paused
            )
        clock.rate, clock.paused = rate, paused


def post_json(client: httpx.Client, url: str, items: list[str]) -> bool:
    try:
        client.post(
            url, content="[" + ",".join(items) + "]", headers={"content-type": "application/json"}
        ).raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("POST %s failed (%d items): %s", url, len(items), e)
        return False


def fresh_start(vessel_id: str, hotspots: dict, seed: int, seq: int) -> tuple[VesselState, World]:
    """A vessel at START with a full tank, and a debris world seeded from the hotspots."""
    v = VesselState(vessel_id, lat=START[0], lon=START[1], heading_deg=90.0, speed_kn=0.0, seq=seq)
    world = World(seed_patches(hotspots["hotspots"], MISSION_BOX, N_PATCHES, random.Random(seed)))
    total = sum(p.mass_kg for p in world.patches)
    log.info("seeded %d patches, %.0f t, from mission-box hotspots", N_PATCHES, total / 1000)
    return v, world


def live_state(dsn: str, vessel_id: str) -> tuple[int, datetime] | None:
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        row = conn.execute(
            "SELECT seq, event_ts FROM vessel_state WHERE vessel_id = %s", [vessel_id]
        ).fetchone()
    return None if row is None else (int(row[0]), row[1])


def fast_forward(span_s: float, tick_s: float) -> None:
    """Burst the history [SIM_START - span, SIM_START) through ingestion; see backfill.py."""
    env = os.environ
    vessel_id, sim_start = env["VESSEL_ID"], settings.sim_start(env)
    why = live_ready(live_state(settings.pg_dsn(env), vessel_id), sim_start)
    if why:
        raise SystemExit(f"backfill not started: {why}")
    n = int(span_s // tick_s)
    if n >= LIVE_SEQ_START:
        raise SystemExit(f"{n} ticks would reach the live seq range; use a longer --tick")
    field, hotspots = load_exports(minio_client(env), env["LAKE_BUCKET"], sim_start)
    v, world = fresh_start(vessel_id, hotspots, HISTORY_SEED, 0)
    rng = random.Random(f"{HISTORY_SEED}:drift")
    pilot = Autopilot(field)
    t0 = sim_start.timestamp() - n * tick_s
    log.info(
        "backfill: %d ticks of %g s from %s to %s",
        n,
        tick_s,
        datetime.fromtimestamp(t0, timezone.utc).isoformat(),
        sim_start.isoformat(),
    )
    started = time.monotonic()
    with httpx.Client(timeout=30) as client:
        sent = burst(
            chunks(history(world, v, pilot, t0, n, tick_s, rng), n),
            lambda batch: post_json(client, env["INGEST_URL"], batch),
        )
    took = time.monotonic() - started
    log.info(
        "backfill done: %d events in %.0f s (%.0f/s); %.0f t collected; plans %s",
        sent,
        took,
        sent / took,
        world.collected_kg / 1000,
        pilot.reasons,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per POST otherwise
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fast-forward", metavar="SPAN", help="backfill this much history, e.g. 30d")
    ap.add_argument("--tick", type=float, default=1.0, help="backfill tick, sim seconds")
    args = ap.parse_args()
    if args.fast_forward:
        fast_forward(parse_duration(args.fast_forward), args.tick)
        return
    env = os.environ
    vessel_id = env["VESSEL_ID"]
    state_file = Path(env["SIM_STATE_DIR"]) / f"{vessel_id}.json"
    ingest_url, survey_url = env["INGEST_URL"], env["SURVEY_URL"]
    tick_sim_s = float(env["SIM_TICK_SECONDS"])  # sim seconds between telemetry ticks
    sim_start = settings.sim_start(env)
    field, hotspots = load_exports(minio_client(env), env["LAKE_BUCKET"], sim_start)

    resumed = sim_state.load(state_file)
    world: World | None = None
    if resumed:
        start, v, world_doc = resumed
        world = World.from_dict(world_doc) if world_doc else None
        log.info("resuming at %s seq=%d", start.isoformat(), v.seq)
    else:
        start = sim_start
        v, world = fresh_start(vessel_id, hotspots, WORLD_SEED, LIVE_SEQ_START)
    if world is None:  # state from before M3 kept the vessel but no world
        _, world = fresh_start(vessel_id, hotspots, WORLD_SEED, v.seq)
    rng = random.Random(f"{WORLD_SEED}:{v.seq}")  # reproducible, and fresh after a restart

    clock = SimClock(start, rate=float(env["SIM_RATE"]))
    client = httpx.Client(timeout=5)
    routes = RouteSource(settings.pg_dsn(env), vessel_id)
    control = ClockControl(settings.pg_dsn(env), vessel_id)
    next_tick = clock.now
    last = last_poll = last_sync = time.monotonic()
    control.sync(clock)  # a rate or pause set before a restart still applies
    routes.poll()
    while True:
        now = time.monotonic()
        clock.advance(now - last)
        last = now
        if now - last_sync >= CLOCK_SYNC_S:
            control.sync(clock)
            last_sync = now
        fresh: list[Telemetry] = []
        survey: list[PatchSurvey] = []
        while clock.now >= next_tick:
            t = next_tick.timestamp()
            if world.link.maybe_drop(t, tick_sim_s, rng):
                log.info(
                    "link down until %s",
                    datetime.fromtimestamp(world.link.offline_until, timezone.utc),
                )
            factor = control.fuel_factor(next_tick)
            tick(world, v, t - tick_sim_s, tick_sim_s, field, routes.targets, rng, factor)
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
