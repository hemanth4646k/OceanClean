"""Telemetry contract: the single definition shared by producers, Spark and PostGIS.

Change fields here, then update infra/postgres/init.sql (vessel_state) to match.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

# Spark schema as (name, DDL type) so this module does not import pyspark.
# Order, names and types must match Telemetry below (enforced by tests).
SPARK_FIELDS: tuple[tuple[str, str], ...] = (
    ("vessel_id", "STRING"),
    ("event_ts", "TIMESTAMP"),
    ("seq", "BIGINT"),
    ("lat", "DOUBLE"),
    ("lon", "DOUBLE"),
    ("heading_deg", "DOUBLE"),
    ("speed_kn", "DOUBLE"),
    ("battery_pct", "DOUBLE"),
    ("fuel_l", "DOUBLE"),
    ("debris_density", "DOUBLE"),
    ("hold_fill_pct", "DOUBLE"),
    ("buffered", "BOOLEAN"),
)
SPARK_COLUMNS: tuple[str, ...] = tuple(name for name, _ in SPARK_FIELDS)
SPARK_DDL = ", ".join(f"{name} {typ}" for name, typ in SPARK_FIELDS)

TELEMETRY_TOPIC = "telemetry"
ZONE_DEG = 5


class Telemetry(BaseModel):
    vessel_id: str = Field(min_length=1, max_length=32)
    event_ts: datetime
    seq: int = Field(ge=0)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    heading_deg: float = Field(ge=0, lt=360)
    speed_kn: float = Field(ge=0)
    battery_pct: float = Field(ge=0, le=100)
    fuel_l: float = Field(ge=0)
    debris_density: float = Field(ge=0)
    hold_fill_pct: float = Field(ge=0, le=100)
    buffered: bool = False

    @field_validator("event_ts")
    @classmethod
    def _utc_only(cls, v: datetime) -> datetime:
        return require_utc(v)

    def to_json(self) -> str:
        """Serialise with a strict ISO-8601 UTC timestamp ending in 'Z' (millisecond precision)."""
        d = self.model_dump()
        d["event_ts"] = format_ts(self.event_ts)
        return json.dumps(d, separators=(",", ":"))


def require_utc(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("timestamps must be timezone-aware UTC")
    return v


def format_ts(ts: datetime) -> str:
    utc = ts.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def zone_of(lat: float, lon: float) -> str:
    """5-degree cell id naming the cell's south-west corner, e.g. (35.1, -142.4) -> 'N35W145'."""
    la = math.floor(lat / ZONE_DEG) * ZONE_DEG
    lo = math.floor(lon / ZONE_DEG) * ZONE_DEG
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def kafka_key(t: Telemetry) -> str:
    return f"{t.vessel_id}|{zone_of(t.lat, t.lon)}"
