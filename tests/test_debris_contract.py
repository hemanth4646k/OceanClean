import json

import pytest
from oceanclean_common.debris import (
    SURVEY_COLUMNS,
    SURVEY_DDL,
    SURVEY_FIELDS,
    PatchSurvey,
)
from pydantic import ValidationError
from sql_schema import PG_TYPE, SPARK_TYPE, table_columns

SAMPLE = {
    "patch_id": "P07",
    "survey_ts": "2026-09-02T05:00:00.000Z",
    "lat": 35.41,
    "lon": -139.2,
    "mass_kg": 4210.5,
    "radius_m": 2000.0,
}


def test_round_trip_preserves_contract() -> None:
    assert json.loads(PatchSurvey.model_validate(SAMPLE).to_json()) == SAMPLE


def test_naive_timestamps_and_negative_mass_rejected() -> None:
    for bad in ({"survey_ts": "2026-09-02T05:00:00"}, {"mass_kg": -1.0}, {"radius_m": 0.0}):
        with pytest.raises(ValidationError):
            PatchSurvey.model_validate({**SAMPLE, **bad})


def test_spark_schema_matches_model_names_and_types() -> None:
    expected = [(n, SPARK_TYPE[f.annotation]) for n, f in PatchSurvey.model_fields.items()]
    assert list(SURVEY_FIELDS) == expected
    assert list(SURVEY_COLUMNS) == list(PatchSurvey.model_fields)
    assert SURVEY_DDL == ", ".join(f"{n} {t}" for n, t in expected)


def test_debris_patches_has_every_contract_column_with_matching_type() -> None:
    cols = table_columns("debris_patches")
    for name, f in PatchSurvey.model_fields.items():
        assert cols.get(name) == PG_TYPE[f.annotation], f"{name}: {cols.get(name)}"
    assert cols["geom"] == "geometry(Point, 4326)"


def test_routes_geometry_is_a_4326_linestring() -> None:
    assert table_columns("routes")["geom"] == "geometry(LineString, 4326)"
