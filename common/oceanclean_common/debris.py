"""Debris survey contract: one row per patch per survey (every 60 sim-min), topic debris_survey.

The simulator's debris world plays the role of an aerial/satellite survey. Mass 0 = collected.
Change fields here, then update infra/postgres/init.sql (debris_patches) to match.
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from oceanclean_common.telemetry import format_ts, require_utc

SURVEY_FIELDS: tuple[tuple[str, str], ...] = (
    ("patch_id", "STRING"),
    ("survey_ts", "TIMESTAMP"),
    ("lat", "DOUBLE"),
    ("lon", "DOUBLE"),
    ("mass_kg", "DOUBLE"),
    ("radius_m", "DOUBLE"),
)
SURVEY_COLUMNS: tuple[str, ...] = tuple(name for name, _ in SURVEY_FIELDS)
SURVEY_DDL = ", ".join(f"{name} {typ}" for name, typ in SURVEY_FIELDS)

DEBRIS_TOPIC = "debris_survey"


class PatchSurvey(BaseModel):
    patch_id: str = Field(min_length=1, max_length=32)
    survey_ts: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    mass_kg: float = Field(ge=0)
    radius_m: float = Field(gt=0)

    @field_validator("survey_ts")
    @classmethod
    def _utc_only(cls, v: datetime) -> datetime:
        return require_utc(v)

    def to_json(self) -> str:
        d = self.model_dump()
        d["survey_ts"] = format_ts(self.survey_ts)
        return json.dumps(d, separators=(",", ":"))
