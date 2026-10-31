"""Satcom link with an offline buffer (SRS 5.x): random outages queue telemetry at the edge.

Queued events are flushed in order once the link and ingestion are back, marked buffered=true.
A failed POST (ingestion or broker down) queues the same way, so nothing is dropped silently.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from oceanclean_common.telemetry import Telemetry

log = logging.getLogger("simulator")

OUTAGES_PER_H = 1 / 30  # chance per sim-hour that the link drops
OUTAGE_S = (20 * 60.0, 2 * 3600.0)  # outage length range, sim seconds
MAX_BATCH = 1000  # events per POST
MAX_QUEUE = 100_000


@dataclass
class Link:
    offline_until: float = 0.0  # sim epoch seconds
    queue: list[Telemetry] = field(default_factory=list)

    def online(self, t: float) -> bool:
        return t >= self.offline_until

    def maybe_drop(self, t: float, dt: float, rng: random.Random) -> bool:
        """Start an outage with probability OUTAGES_PER_H per sim-hour; True if one started."""
        if self.online(t) and rng.random() < OUTAGES_PER_H * dt / 3600.0:
            self.offline_until = t + rng.uniform(*OUTAGE_S)
            return True
        return False

    def flush(
        self, t: float, fresh: Sequence[Telemetry], send: Callable[[list[Telemetry]], bool]
    ) -> int:
        """Send the queue, then fresh events, in order; keep what was not sent. Returns sent."""
        todo = [*self.queue, *fresh]
        sent = 0
        if self.online(t):
            for i in range(0, len(todo), MAX_BATCH):
                chunk = todo[i : i + MAX_BATCH]
                if not send(chunk):
                    break
                sent += len(chunk)
        rest = [e if e.buffered else e.model_copy(update={"buffered": True}) for e in todo[sent:]]
        if len(rest) > MAX_QUEUE:
            log.error("offline queue full: dropping %d oldest events", len(rest) - MAX_QUEUE)
            rest = rest[-MAX_QUEUE:]
        self.queue = rest
        return sent
