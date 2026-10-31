"""Spark fixture tests; run in the oceanclean-spark image (skipped where pyspark is absent)."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pyspark")

import telemetry_stream as ts  # noqa: E402
from oceanclean_common.debris import PatchSurvey  # noqa: E402
from oceanclean_common.settings import to_utc  # noqa: E402
from oceanclean_common.telemetry import Telemetry  # noqa: E402
from pyspark.sql import DataFrame, SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

T0 = datetime(2026, 9, 1, 12, 0, 0, 123_000, tzinfo=timezone.utc)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    s = (
        SparkSession.builder.master("local[1]")
        .appName("oceanclean-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.ivy", "/tmp/.ivy2")  # test uid has no passwd entry, so no JVM home
        .getOrCreate()
    )
    yield s
    s.stop()


def tel(vessel_id: str, seq: int, minutes: float) -> Telemetry:
    return Telemetry(
        vessel_id=vessel_id,
        event_ts=T0 + timedelta(minutes=minutes),
        seq=seq,
        lat=35.12,
        lon=-142.4,
        heading_deg=87.5,
        speed_kn=6.2,
        battery_pct=81.3,
        fuel_l=412.0,
        debris_density=0.63,
        hold_fill_pct=22.0,
        buffered=minutes < 0,
    )


def parsed(spark: SparkSession, events: list[Telemetry]) -> DataFrame:
    """What the stream sees: producer JSON in a Kafka-like `value` column, then the real parser."""
    raw = spark.createDataFrame(
        [(bytearray(e.to_json(), "utf-8"),) for e in events], "value BINARY"
    )
    return ts.parse_telemetry(raw)


# Two vessels; OC-01 has a duplicate seq and a late row (new seq, event time 2 h older).
FIXTURE = [
    tel("OC-01", 1, 0),
    tel("OC-01", 2, 1),
    tel("OC-01", 2, 1),
    tel("OC-01", 3, -120),
    tel("OC-02", 1, 0),
]


def keys(df: DataFrame) -> list[tuple[str, int]]:
    return sorted((r.vessel_id, r.seq) for r in df.select("vessel_id", "seq").collect())


def test_producer_json_parses_to_exact_contract_row(spark: SparkSession) -> None:
    t = tel("OC-01", 7, 0)
    df = parsed(spark, [t]).withColumn("_us", F.unix_micros("event_ts"))
    row = df.collect()[0].asDict()
    assert all(v is not None for v in row.values()), row
    assert row.pop("_us") == (T0 - EPOCH) // timedelta(microseconds=1)
    row["event_ts"] = to_utc(row["event_ts"])
    assert row == t.model_dump()
    assert row["event_ts"].tzinfo == timezone.utc


def test_malformed_json_is_dropped(spark: SparkSession) -> None:
    raw = spark.createDataFrame([(bytearray(b"{not json"),), (bytearray(b"{}"),)], "value BINARY")
    assert ts.parse_telemetry(raw).count() == 0


def test_dedup_batch_drops_repeated_seq_only(spark: SparkSession) -> None:
    out = ts.dedup_batch(parsed(spark, FIXTURE))
    assert keys(out) == [("OC-01", 1), ("OC-01", 2), ("OC-01", 3), ("OC-02", 1)]


def test_latest_per_vessel_picks_newest_event_time_not_highest_seq(spark: SparkSession) -> None:
    out = ts.latest_per_vessel(ts.dedup_batch(parsed(spark, FIXTURE)))
    assert keys(out) == [("OC-01", 2), ("OC-02", 1)]


def test_stale_rows_are_those_not_newer_than_stored_state(spark: SparkSession) -> None:
    stored = spark.createDataFrame([("OC-01", T0)], ts.STORED_DDL)
    out = ts.stale_rows(ts.dedup_batch(parsed(spark, FIXTURE)), stored)
    # seq 1 equals the stored instant and seq 3 is 2 h older; OC-02 has no stored row.
    assert keys(out) == [("OC-01", 1), ("OC-01", 3)]


def survey(pid: str, hours: float, mass: float) -> PatchSurvey:
    return PatchSurvey(
        patch_id=pid,
        survey_ts=T0 + timedelta(hours=hours),
        lat=35.4,
        lon=-139.2,
        mass_kg=mass,
        radius_m=2000.0,
    )


def test_survey_json_parses_to_exact_contract_row(spark: SparkSession) -> None:
    s = survey("P01", 0, 4210.5)
    raw = spark.createDataFrame([(bytearray(s.to_json(), "utf-8"),)], "value BINARY")
    row = ts.parse_survey(raw).collect()[0].asDict()
    row["survey_ts"] = to_utc(row["survey_ts"])
    assert row == s.model_dump()


def test_newest_survey_per_patch_wins(spark: SparkSession) -> None:
    rows = [survey("P01", 0, 900.0), survey("P01", 1, 400.0), survey("P02", 0, 50.0)]
    raw = spark.createDataFrame([(bytearray(r.to_json(), "utf-8"),) for r in rows], "value BINARY")
    out = ts.newest_per(ts.parse_survey(raw), "patch_id", "survey_ts").collect()
    assert sorted((r.patch_id, r.mass_kg) for r in out) == [("P01", 400.0), ("P02", 50.0)]


def test_bronze_partitions_use_event_time_so_late_rows_keep_their_hour(
    spark: SparkSession,
) -> None:
    # The late row (2 h older, buffered) gets its own event hour, not the arrival hour.
    df = ts.bronze_partitions(ts.dedup_batch(parsed(spark, FIXTURE)), "event_ts")
    got = sorted((r.seq, r.vessel_id, str(r.date), r.hour) for r in df.collect())
    assert got == [
        (1, "OC-01", "2026-09-01", 12),
        (1, "OC-02", "2026-09-01", 12),
        (2, "OC-01", "2026-09-01", 12),
        (3, "OC-01", "2026-09-01", 10),
    ]
    assert set(df.columns) == {*ts.SPARK_COLUMNS, "date", "hour"}
