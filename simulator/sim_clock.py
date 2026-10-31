"""Compressed simulation clock (ADR-0003). All event timestamps are sim time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SimClock:
    now: datetime
    rate: float = 60.0  # sim seconds per real second
    paused: bool = False

    def advance(self, real_seconds: float) -> timedelta:
        """Advance by real elapsed time scaled by rate; returns the sim delta applied."""
        if self.paused:
            return timedelta(0)
        delta = timedelta(seconds=real_seconds * self.rate)
        self.now += delta
        return delta
