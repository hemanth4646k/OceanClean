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
INGEST_URL = os.environ.get("INGEST_URL", "http://ingestion:8000/telemetry")
TICK_SIM_S = float(os.environ.get("SIM_TICK_SECONDS", "60"))  # one telemetry tick per sim-minute
SIM_RATE = float(os.environ.get("SIM_RATE", "60"))
SIM_START = os.environ.get("SIM_START", "2026-09-01T00:00:00Z")
STATE_FILE = Path(os.environ.get("SIM_STATE_FILE", "/state/OC-01.json"))


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
    resumed = sim_state.load(STATE_FILE)
    if resumed:
        start, v = resumed
        log.info("resuming at %s seq=%d", start.isoformat(), v.seq)
    else:
        start = datetime.fromisoformat(SIM_START.replace("Z", "+00:00"))
        v = VesselState("OC-01", lat=35.0, lon=-142.0, heading_deg=90.0, speed_kn=6.0)
    clock = SimClock(start, rate=SIM_RATE)
    client = httpx.Client(timeout=5)
    next_tick = clock.now
    last = time.monotonic()
    while True:
        now = time.monotonic()
        clock.advance(now - last)
        last = now
        while clock.now >= next_tick:
            v.lat, v.lon = step_position(
                v.lat, v.lon, v.heading_deg, v.speed_kn * KN_TO_MS, TICK_SIM_S
            )
            v.seq += 1
            t = to_telemetry(v, next_tick.astimezone(timezone.utc))
            try:
                client.post(
                    INGEST_URL, content=t.to_json(), headers={"content-type": "application/json"}
                )
            except httpx.HTTPError as e:
                log.warning("send failed: %s", e)
            next_tick += timedelta(seconds=TICK_SIM_S)
            sim_state.save(STATE_FILE, next_tick, v)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
