"""Telemetry backfill (`sim_main.py --fast-forward 30d`): the vessel's previous mission, in bulk.

The same physics, debris world and optimizer as the live run, but run as fast as the CPU allows
instead of on the sim clock, and burst through ingestion and Kafka. The history covers
[SIM_START - span, SIM_START) and numbers its ticks 1, 2, ...; a live run numbers its ticks from
LIVE_SEQ_START, so seq and event time stay in step across history and live.

The vessel logs at 1 Hz by default (2.6M events in 30 days) where the live run reports once a
sim-minute. Patches still drift every 60 s, as in the live run: they move centimetres per second.

Every backfill event is older than the live state and the windows' watermark, by design
(ADR-0005): bronze and silver get all of it, the live-state UPSERT and the 5-minute windows none.
That only holds once the live run is past SIM_START, so `live_ready` is checked first.

Onboard, an autopilot stands in for the stream's gate + optimizer + HITL autopilot: it sees an
hourly survey, runs the same recalc gate and accepts every plan at once.
"""

from __future__ import annotations

import logging
import queue
import random
import re
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from currents import CurrentField
from debris import debris_density, drift_patches
from gate import RouteRef, recalc_reason
from intercept import Position
from oceanclean_common.telemetry import Telemetry
from planner import PatchObs, plan_chain, predicted_targets, repredict, route_record
from vessel import VesselState
from world import SURVEY_EVERY_S, RouteTargets, World, move_vessel, to_telemetry, waypoint_targets

log = logging.getLogger("simulator")

LIVE_SEQ_START = 10_000_000  # a live run's first tick is LIVE_SEQ_START + 1; history stays below
HISTORY_SEED = 20260801  # the previous mission's debris world, not the live one (WORLD_SEED)
DRIFT_STEP_S = 60.0
GATE_EVERY_S = 1800.0  # the stream's gate runs every micro-batch: 2-120 sim-minutes apart
LIVE_LEAD_S = 3600.0  # the live run must be this far past SIM_START (windows watermark: 10 min)
BATCH = 2000  # events per POST
RETRY_S = 2.0

_UNITS = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0}


def parse_duration(s: str) -> float:
    """'30d', '12h', '90m' or '45s' as seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([dhms])", s.strip())
    if m is None:
        raise ValueError(f"expected a duration like 30d, 12h or 90m, got {s!r}")
    return float(m[1]) * _UNITS[m[2]]


def live_ready(state: tuple[int, datetime] | None, sim_start: datetime) -> str | None:
    """Why a backfill must not start yet, given the live (seq, event_ts); None when it may."""
    if state is None:
        return "no live state yet: start the stack and let the live run report"
    seq, ts = state
    if seq <= LIVE_SEQ_START:
        return (
            f"the live run's seq {seq} overlaps the backfill's range (it predates M6):"
            " run infra/reset_sim.sh first"
        )
    if ts < sim_start + timedelta(seconds=LIVE_LEAD_S):
        return f"the live run is at {ts.isoformat()}; wait until it is an hour past SIM_START"
    return None


def observe(w: World, t: float) -> dict[str, PatchObs]:
    """The optimizer's view of every patch at sim time t, as an hourly survey would give it."""
    return {
        p.patch_id: PatchObs(p.patch_id, t, p.lat, p.lon, p.mass_kg, p.radius_m) for p in w.patches
    }


@dataclass
class Autopilot:
    """The gate and optimizer of the stream, with every proposal accepted at once."""

    field: CurrentField
    latest: RouteRef | None = None
    active: RouteRef | None = None
    targets: RouteTargets | None = None
    reasons: dict[str, int] = field(default_factory=dict)

    def step(self, t: float, pos: Position, obs: Mapping[str, PatchObs]) -> None:
        live = {pid for pid, p in obs.items() if p.mass_kg > 0}

        def again(r: RouteRef) -> list[Position | None]:
            meets = repredict(self.field, t, pos, [pid for pid, _, _ in r.targets], obs)
            return [None if m is None else (m.lat, m.lon) for m in meets]

        reason = recalc_reason(t, self.latest, self.active, live, again)
        if reason is None:
            return
        self.reasons[reason] = self.reasons.get(reason, 0) + 1
        route_id = sum(self.reasons.values())  # one route row per gate firing, as in `routes`
        plan = plan_chain(self.field, t, pos, obs.values())
        if not plan.targets:  # nothing reachable: keep the active route, retry after the gate's
            self.latest = RouteRef(route_id, "expired", t, ())  # throttle (30 sim-minutes)
            return
        rec = route_record(plan)
        self.latest = self.active = RouteRef(
            route_id, "active", t, predicted_targets(rec["targets"])
        )
        self.targets = waypoint_targets(rec["waypoints"])


def history(
    w: World,
    v: VesselState,
    pilot: Autopilot,
    t0: float,
    n_ticks: int,
    tick_s: float,
    rng: random.Random,
) -> Iterator[Telemetry]:
    """n_ticks events, each stamped at the end of its tick: t0 + tick_s, ..., t0 + n * tick_s."""
    drift_every = max(1, round(DRIFT_STEP_S / tick_s))
    obs: dict[str, PatchObs] = {}
    next_survey = next_gate = t0
    for k in range(n_ticks):
        t = t0 + k * tick_s
        if t >= next_survey:
            obs = observe(w, t)
            next_survey += SURVEY_EVERY_S
        if t >= next_gate:
            pilot.step(t, (v.lat, v.lon), obs)
            next_gate += GATE_EVERY_S
        move_vessel(w, v, t, tick_s, pilot.field, pilot.targets)
        if (k + 1) % drift_every == 0:
            dt = drift_every * tick_s
            drift_patches(w.patches, pilot.field, t + tick_s - dt, dt, rng)
        v.debris_density = debris_density(w.patches, v.lat, v.lon)
        v.seq += 1
        yield to_telemetry(v, datetime.fromtimestamp(t + tick_s, timezone.utc))


def chunks(events: Iterable[Telemetry], n_total: int, size: int = BATCH) -> Iterator[list[str]]:
    """Events as JSON in POST-sized chunks, logging progress about every 5 %."""
    chunk: list[str] = []
    done, step, t_start = 0, max(size, n_total // 20), time.monotonic()
    for e in events:
        chunk.append(e.to_json())
        if len(chunk) == size:
            yield chunk
            done += len(chunk)
            chunk = []
            if done % step < size:
                rate = done / max(time.monotonic() - t_start, 1e-9)
                log.info("backfill: %d/%d events (%.0f/s), at %s", done, n_total, rate, e.event_ts)
    if chunk:
        yield chunk


def burst(
    batches: Iterable[list[str]], post: Callable[[list[str]], bool], retry_s: float = RETRY_S
) -> int:
    """POST every batch in order; a batch is retried until ingestion acknowledges it.

    Simulation and sending overlap: a sender thread posts while the caller builds the next batch.
    Returns the number of events acknowledged.
    """
    q: queue.Queue[list[str] | None] = queue.Queue(maxsize=8)
    sent = 0

    def sender() -> None:
        nonlocal sent
        while (batch := q.get()) is not None:
            while not post(batch):
                time.sleep(retry_s)
            sent += len(batch)

    thread = threading.Thread(target=sender, name="backfill-sender", daemon=True)
    thread.start()
    try:
        for b in batches:
            q.put(b)
    finally:
        q.put(None)
        thread.join()
    return sent
