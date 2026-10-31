"""Spark StreamingQueryListener -> PostGIS `pipeline_metrics` (the Admin Metrics tab, M5).

One row per micro-batch of each named query: wall-clock time, input rows and rates, trigger
duration and Kafka lag (offsets behind latest, the largest over the query's sources).
"""

from __future__ import annotations

import json
import logging
from dataclasses import astuple, dataclass
from datetime import datetime

import psycopg
from oceanclean_common.settings import parse_utc
from pyspark.sql.streaming import StreamingQueryListener
from stream_store import insert_metrics

log = logging.getLogger("pipeline_metrics")


@dataclass(frozen=True)
class MetricsRow:
    ts: datetime
    query: str
    batch_id: int
    input_rows: int
    input_rps: float | None
    processed_rps: float | None
    duration_ms: float | None
    kafka_lag: int | None


def _float(v: object) -> float | None:
    # Spark writes NaN rates (no previous batch) as the string "NaN"; Python reads it as nan.
    if v is None:
        return None
    f = float(v)
    return None if f != f else f


def progress_row(p: dict) -> MetricsRow:
    """A StreamingQueryProgress (its JSON as a dict) -> one pipeline_metrics row."""
    lags = [
        int(m["maxOffsetsBehindLatest"])
        for s in p.get("sources", [])
        if "maxOffsetsBehindLatest" in (m := s.get("metrics") or {})
    ]
    return MetricsRow(
        ts=parse_utc(p["timestamp"]),
        query=p.get("name") or p["id"],
        batch_id=int(p["batchId"]),
        input_rows=int(p["numInputRows"]),
        input_rps=_float(p.get("inputRowsPerSecond")),
        processed_rps=_float(p.get("processedRowsPerSecond")),
        duration_ms=_float(p.get("durationMs", {}).get("triggerExecution")),
        kafka_lag=max(lags) if lags else None,
    )


class MetricsListener(StreamingQueryListener):
    """Inserts one pipeline_metrics row per progress event. Never raises into Spark."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def onQueryStarted(self, event: object) -> None:
        log.info("query started: %s", getattr(event, "name", None))

    def onQueryProgress(self, event: object) -> None:
        try:
            row = progress_row(json.loads(event.progress.json))
            with psycopg.connect(self.dsn) as conn:
                insert_metrics(conn, astuple(row))
        except Exception:
            log.exception("could not record query progress")

    def onQueryIdle(self, event: object) -> None:
        pass

    def onQueryTerminated(self, event: object) -> None:
        log.warning("query terminated: %s %s", event.id, event.exception)
