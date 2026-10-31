import json
from datetime import datetime, timedelta, timezone

import pytest
from oceanclean_common.telemetry import SPARK_DDL, Telemetry, kafka_key, zone_of
from pydantic import ValidationError

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


def test_spark_ddl_matches_model_fields() -> None:
    ddl_names = [col.strip().split()[0] for col in SPARK_DDL.split(",")]
    assert ddl_names == list(Telemetry.model_fields)
