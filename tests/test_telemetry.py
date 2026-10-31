import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from oceanclean_common.telemetry import (
    SPARK_COLUMNS,
    SPARK_DDL,
    SPARK_FIELDS,
    Telemetry,
    kafka_key,
    zone_of,
)
from pydantic import ValidationError

INIT_SQL = Path(__file__).resolve().parents[1] / "infra" / "postgres" / "init.sql"
SPARK_TYPE = {str: "STRING", datetime: "TIMESTAMP", int: "BIGINT", float: "DOUBLE", bool: "BOOLEAN"}
PG_TYPE = {
    str: "TEXT",
    datetime: "TIMESTAMPTZ",
    int: "BIGINT",
    float: "DOUBLE PRECISION",
    bool: "BOOLEAN",
}

SAMPLE = {
    "vessel_id": "OC-01",
    "event_ts": "2026-11-01T10:15:30.000Z",
    "seq": 1042,
    "lat": 35.12,
    "lon": -142.40,
    "heading_deg": 87.5,
    "speed_kn": 6.2,
    "battery_pct": 81.3,
    "fuel_l": 412.0,
    "debris_density": 0.63,
    "hold_fill_pct": 22.0,
    "buffered": False,
}


@pytest.mark.parametrize(
    ("lat", "lon", "zone"),
    [
        (35.12, -142.40, "N35W145"),
        (0.0, 0.0, "N00E000"),
        (-0.1, -0.1, "S05W005"),
        (44.99, -130.0, "N40W130"),
        (20.0, -180.0, "N20W180"),
    ],
)
def test_zone_of(lat: float, lon: float, zone: str) -> None:
    assert zone_of(lat, lon) == zone


def test_round_trip_preserves_contract() -> None:
    t = Telemetry.model_validate(SAMPLE)
    assert json.loads(t.to_json()) == SAMPLE


def test_kafka_key_is_vessel_and_zone() -> None:
    assert kafka_key(Telemetry.model_validate(SAMPLE)) == "OC-01|N35W145"


def test_naive_or_non_utc_timestamps_rejected() -> None:
    for ts in ("2026-11-01T10:15:30", "2026-11-01T10:15:30+05:30"):
        with pytest.raises(ValidationError):
            Telemetry.model_validate({**SAMPLE, "event_ts": ts})


def test_utc_offset_zero_accepted() -> None:
    ts = datetime(2026, 11, 1, tzinfo=timezone(timedelta(0)))
    assert Telemetry.model_validate({**SAMPLE, "event_ts": ts}).event_ts == ts


def vessel_state_columns() -> dict[str, str]:
    """Column name -> SQL type of vessel_state, constraints stripped."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS vessel_state \((.*?)\n\);", INIT_SQL.read_text(), re.S
    )
    assert m, "vessel_state table not found in init.sql"
    cols = {}
    for line in m.group(1).strip().splitlines():
        name, rest = line.strip().rstrip(",").split(None, 1)
        cols[name] = re.split(r"\s+(?:NOT NULL|NULL|PRIMARY KEY|DEFAULT)\b", rest)[0]
    return cols


def test_spark_schema_matches_model_names_and_types() -> None:
    expected = [(name, SPARK_TYPE[f.annotation]) for name, f in Telemetry.model_fields.items()]
    assert list(SPARK_FIELDS) == expected
    assert list(SPARK_COLUMNS) == list(Telemetry.model_fields)
    assert SPARK_DDL == ", ".join(f"{n} {t}" for n, t in expected)


def test_vessel_state_has_every_contract_column_with_matching_type() -> None:
    cols = vessel_state_columns()
    for name, f in Telemetry.model_fields.items():
        assert name in cols, f"vessel_state lacks contract column {name}"
        assert cols[name] == PG_TYPE[f.annotation], f"{name}: {cols[name]}"
