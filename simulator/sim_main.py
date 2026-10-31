"""Simulator entrypoint: runs the sim clock, moves the vessel, posts telemetry to ingestion."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import sim_state
from oceanclean_common.telemetry import Telemetry
from sim_clock import SimClock
from vessel import KN_TO_MS, VesselState, step_position

log = logging.getLogger("simulator")


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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    vessel_id = os.environ["VESSEL_ID"]
    state_file = Path(os.environ["SIM_STATE_DIR"]) / f"{vessel_id}.json"
    ingest_url = os.environ["INGEST_URL"]
    tick_sim_s = float(os.environ["SIM_TICK_SECONDS"])  # sim seconds between telemetry ticks
    resumed = sim_state.load(state_file)
    if resumed:
        start, v = resumed
        log.info("resuming at %s seq=%d", start.isoformat(), v.seq)
    else:
        start = datetime.fromisoformat(os.environ["SIM_START"].replace("Z", "+00:00"))
        v = VesselState(vessel_id, lat=35.0, lon=-142.0, heading_deg=90.0, speed_kn=6.0)
    clock = SimClock(start, rate=float(os.environ["SIM_RATE"]))
    client = httpx.Client(timeout=5)
    next_tick = clock.now
    last = time.monotonic()
    while True:
        now = time.monotonic()
        clock.advance(now - last)
        last = now
        while clock.now >= next_tick:
            v.lat, v.lon = step_position(
                v.lat, v.lon, v.heading_deg, v.speed_kn * KN_TO_MS, tick_sim_s
            )
            v.seq += 1
            t = to_telemetry(v, next_tick.astimezone(timezone.utc))
            try:
                client.post(
                    ingest_url, content=t.to_json(), headers={"content-type": "application/json"}
                ).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("send failed: %s", e)
            next_tick += timedelta(seconds=tick_sim_s)
            sim_state.save(state_file, next_tick, v)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
