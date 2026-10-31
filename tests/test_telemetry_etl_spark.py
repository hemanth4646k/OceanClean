"""Spark fixture tests for the telemetry batch job: bronze -> silver (dedup, deltas) -> gold."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest

pytest.importorskip("pyspark")

import telemetry_etl as etl  # noqa: E402
from energy import BATTERY_KWH, HOLD_CAPACITY_KG, KWH_PER_L  # noqa: E402
from oceanclean_common.telemetry import SPARK_COLUMNS, SPARK_DDL, Telemetry, zone_of  # noqa: E402
from pyspark.sql import DataFrame, SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

T0 = datetime(2026, 9, 1, 23, 57, tzinfo=timezone.utc)  # seq 3 is the first tick of 2 Sep


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    s = (
        SparkSession.builder.master("local[1]")
        .appName("oceanclean-telemetry-etl-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.ivy", "/tmp/.ivy2")
        .getOrCreate()
    )
    yield s
    s.stop()


def tel(
    seq: int,
    fuel: float,
    battery: float,
    hold: float,
    vessel_id: str = "OC-01",
    lat: float = 35.2,
    lon: float = -142.4,
) -> Telemetry:
    return Telemetry(
        vessel_id=vessel_id,
        event_ts=T0 + timedelta(minutes=seq),
        seq=seq,
        lat=lat,
        lon=lon,
        heading_deg=90.0,
        speed_kn=6.0,
        battery_pct=battery,
        fuel_l=fuel,
        debris_density=0.2,
        hold_fill_pct=hold,
        buffered=False,
    )


def bronze(spark: SparkSession, events: list[Telemetry]) -> DataFrame:
    """Bronze as the stream writes it: contract columns plus event-time date/hour partitions."""
    rows = [tuple(e.model_dump()[c] for c in SPARK_COLUMNS) for e in events]
    df = spark.createDataFrame(rows, SPARK_DDL)
    return df.withColumn("date", F.to_date("event_ts")).withColumn("hour", F.hour("event_ts"))


# OC-01, arriving out of order with a duplicate: burns 10 L, draws 3 % battery and collects
# 4 % hold (seq 2); refuels and keeps collecting (seq 3); offloads (seq 4). Crosses midnight.
EVENTS = [
    tel(3, 12_000.0, 95.0, 6.0),
    tel(1, 500.0, 100.0, 0.0),
    tel(2, 490.0, 97.0, 4.0),
    tel(2, 490.0, 97.0, 4.0),
    tel(4, 11_990.0, 95.0, 0.0),
    tel(1, 800.0, 100.0, 0.0, vessel_id="OC-02", lat=-12.5, lon=7.5),
]


def by_seq(df: DataFrame, vessel_id: str = "OC-01") -> dict[int, dict[str, object]]:
    return {r.seq: r.asDict() for r in df.where(F.col("vessel_id") == vessel_id).collect()}


def test_silver_dedups_and_measures_each_tick_from_the_previous_seq(spark: SparkSession) -> None:
    silver = etl.silver_telemetry(bronze(spark, EVENTS))
    assert silver.count() == 5
    rows = by_seq(silver)
    assert rows[1]["energy_kwh"] == 0.0 and rows[1]["collected_kg"] == 0.0  # no previous tick
    assert rows[2]["energy_kwh"] == pytest.approx(10 * KWH_PER_L + 0.03 * BATTERY_KWH)
    assert rows[2]["collected_kg"] == pytest.approx(0.04 * HOLD_CAPACITY_KG)
    # Refuel: the fuel jump is not consumption; the battery draw still counts.
    assert rows[3]["energy_kwh"] == pytest.approx(0.02 * BATTERY_KWH)
    assert rows[3]["collected_kg"] == pytest.approx(0.02 * HOLD_CAPACITY_KG)
    # Offload empties the hold: nothing collected.
    assert rows[4]["energy_kwh"] == pytest.approx(10 * KWH_PER_L)
    assert rows[4]["collected_kg"] == 0.0
    assert by_seq(silver, "OC-02")[1]["energy_kwh"] == 0.0
    assert {r["date"] for r in rows.values()} == {date(2026, 9, 1), date(2026, 9, 2)}
    assert "hour" not in silver.columns


def test_a_seq_gap_starts_a_new_segment_with_nothing_measured(spark: SparkSession) -> None:
    """Backfill history (seq 1..n) then a live run (from LIVE_SEQ_START + 1): the jump between
    the two missions' end and start state is not one tick's consumption."""
    events = [
        tel(1, 900.0, 60.0, 50.0),
        tel(2, 890.0, 55.0, 52.0),
        tel(10_000_001, 12_000.0, 100.0, 0.0),
        tel(10_000_002, 11_990.0, 99.0, 1.0),
    ]
    rows = by_seq(etl.silver_telemetry(bronze(spark, events)))
    assert rows[2]["energy_kwh"] == pytest.approx(10 * KWH_PER_L + 0.05 * BATTERY_KWH)
    assert rows[10_000_001]["energy_kwh"] == 0.0 and rows[10_000_001]["collected_kg"] == 0.0
    assert rows[10_000_002]["energy_kwh"] == pytest.approx(10 * KWH_PER_L + 0.01 * BATTERY_KWH)
    assert rows[10_000_002]["collected_kg"] == pytest.approx(0.01 * HOLD_CAPACITY_KG)


@pytest.mark.parametrize(
    "lat, lon",
    [(35.2, -142.4), (-12.5, 7.5), (0.0, 0.0), (-0.1, -0.1), (40.0, -145.0), (-5.0, 179.9)],
)
def test_spark_zone_matches_the_python_zone_of(spark: SparkSession, lat: float, lon: float) -> None:
    df = spark.createDataFrame([(lat, lon)], "lat DOUBLE, lon DOUBLE")
    assert df.select(etl.zone_col("lat", "lon")).first()[0] == zone_of(lat, lon)


def test_gold_sums_energy_and_debris_per_day_and_zone(spark: SparkSession) -> None:
    silver = etl.silver_telemetry(bronze(spark, EVENTS))
    daily = {r.date: r.asDict() for r in etl.daily(silver).collect()}
    day1 = daily[date(2026, 9, 1)]  # seq 1 of both vessels and OC-01 seq 2
    assert day1["rows"] == 3
    assert day1["energy_kwh"] == pytest.approx(10 * KWH_PER_L + 0.03 * BATTERY_KWH)
    assert day1["kg_per_kwh"] == pytest.approx(day1["collected_kg"] / day1["energy_kwh"])
    zones = {(r.date, r.zone): r.rows for r in etl.daily_zone(silver).collect()}
    assert zones[(date(2026, 9, 1), "S15E005")] == 1
    assert sum(zones.values()) == 5


def test_kg_per_kwh_is_null_without_energy(spark: SparkSession) -> None:
    silver = etl.silver_telemetry(bronze(spark, [tel(1, 500.0, 100.0, 0.0)]))
    [row] = etl.daily(silver).collect()
    assert row.kg_per_kwh is None


def test_zone_totals_are_built_from_the_gold_day_zone_view(spark: SparkSession) -> None:
    silver = etl.silver_telemetry(bronze(spark, EVENTS))
    totals = {r.zone: r.asDict() for r in etl.zone_totals(etl.daily_zone(silver)).collect()}
    by_zone = {
        r.zone: r
        for r in silver.groupBy("zone")
        .agg(
            F.count(F.lit(1)).alias("n"),
            F.sum("energy_kwh").alias("e"),
            F.sum("collected_kg").alias("c"),
        )
        .collect()
    }
    assert set(totals) == set(by_zone)
    for zone, t in totals.items():  # summing per-day rows gives the whole-mission totals
        assert t["rows"] == by_zone[zone].n
        assert t["energy_kwh"] == pytest.approx(by_zone[zone].e)
        assert t["collected_kg"] == pytest.approx(by_zone[zone].c)
