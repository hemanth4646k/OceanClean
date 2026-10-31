"""Spark fixture tests for the batch ETL; run in the oceanclean-spark image (see CLAUDE.md)."""

import json
import math
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

import currents_etl as etl  # noqa: E402
import netCDF4  # noqa: E402
import numpy as np  # noqa: E402
from oceanclean_common.settings import to_utc  # noqa: E402
from pyspark.sql import DataFrame, SparkSession  # noqa: E402

R = etl.EARTH_RADIUS_M
D = math.radians(etl.GRID_DEG)


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    s = (
        SparkSession.builder.master("local[1]")
        .appName("oceanclean-etl-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.ivy", "/tmp/.ivy2")
        .getOrCreate()
    )
    yield s
    s.stop()


def epoch(d: date) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()


def make_netcdf(path: Path) -> bytes:
    """2 August days + 1 September day (ERDDAP may snap an edge day into the next month)."""
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("time", 3)
        ds.createDimension("latitude", 2)
        ds.createDimension("longitude", 3)
        t = ds.createVariable("time", "f8", ("time",))
        t.units = "seconds since 1970-01-01T00:00:00Z"
        t[:] = [epoch(date(2026, 8, 30)), epoch(date(2026, 8, 31)), epoch(date(2026, 9, 1))]
        ds.createVariable("latitude", "f4", ("latitude",))[:] = [30.125, 30.375]
        ds.createVariable("longitude", "f4", ("longitude",))[:] = [179.875, 180.125, 230.125]
        dims = ("time", "latitude", "longitude")
        u = ds.createVariable("u", "f4", dims, fill_value=-9999.0)
        v = ds.createVariable("v", "f4", dims, fill_value=-9999.0)
        u[:] = np.arange(18, dtype="f4").reshape(3, 2, 3) / 100
        v[:] = -np.arange(18, dtype="f4").reshape(3, 2, 3) / 100
        u[0, 1, 2] = np.ma.masked  # land / missing
    return path.read_bytes()


def silver_fixture(tmp_path: Path, spark: SparkSession) -> DataFrame:
    rows = list(etl.netcdf_rows(make_netcdf(tmp_path / "f.nc"), "2026-08"))
    return etl.explode_grid(spark.createDataFrame(rows, etl.ROW_DDL))


def test_month_of_reads_the_chunk_month_from_the_bronze_key() -> None:
    assert etl.month_of("s3a://lake/bronze/currents/scud_pac/scud_pac_2026-08.nc") == "2026-08"


def test_netcdf_to_silver_rows(tmp_path: Path, spark: SparkSession) -> None:
    out = silver_fixture(tmp_path, spark)
    rows = out.orderBy("date", "lat", "lon").collect()
    # 2 August days x 2 lats x 3 lons, minus the masked cell; the September day belongs elsewhere.
    assert len(rows) == 11
    assert {r.date for r in rows} == {date(2026, 8, 30), date(2026, 8, 31)}
    first = rows[0]
    # 0..360 -> -180..180: 230.125 -> -129.875, 180.125 -> -179.875, 179.875 stays.
    assert sorted({r.lon for r in rows}) == [-179.875, -129.875, 179.875]
    assert (first.lat, first.lon) == (30.125, -179.875)
    assert first.u == pytest.approx(0.01) and first.v == pytest.approx(-0.01)
    assert to_utc(first.time) == datetime(2026, 8, 30, tzinfo=timezone.utc)
    assert set(out.columns) == {"time", "date", "lat", "lon", "u", "v"}


def grid(spark: SparkSession, fu: object, fv: object, days: int = 1) -> DataFrame:
    """5x5 quarter-degree grid at ~35N; fu/fv map (i_lat, i_lon) -> velocity."""
    rows = [
        (date(2026, 8, 1 + d), 35.125 + 0.25 * i, -140.125 + 0.25 * j, fu(i, j), fv(i, j))
        for d in range(days)
        for i in range(5)
        for j in range(5)
    ]
    return spark.createDataFrame(rows, "date DATE, lat DOUBLE, lon DOUBLE, u FLOAT, v FLOAT")


def div_at(df: DataFrame, i: int, j: int) -> float | None:
    lat, lon = 35.125 + 0.25 * i, -140.125 + 0.25 * j
    rows = df.where((df.lat == lat) & (df.lon == lon)).collect()
    assert len(rows) == 1
    return rows[0].div


def test_divergence_of_eastward_shear(spark: SparkSession) -> None:
    k = 0.01  # u grows 1 cm/s per cell eastward
    out = etl.divergence(grid(spark, lambda i, j: k * j, lambda i, j: 0.0))
    lat = math.radians(35.125 + 0.5)
    assert div_at(out, 2, 2) == pytest.approx(k / (R * math.cos(lat) * D), rel=1e-5)
    assert div_at(out, 2, 0) is None  # no western neighbour
    assert div_at(out, 0, 2) is None  # no southern neighbour


def test_divergence_of_uniform_meridional_flow_is_the_spherical_term(spark: SparkSession) -> None:
    c = 0.1
    out = etl.divergence(grid(spark, lambda i, j: 0.0, lambda i, j: c))
    lat_s, lat_c, lat_n = (math.radians(35.125 + 0.25 * i) for i in (1, 2, 3))
    want = c * (math.cos(lat_n) - math.cos(lat_s)) / (2 * D * R * math.cos(lat_c))
    assert div_at(out, 2, 2) == pytest.approx(want, rel=1e-4)
    assert want < 0  # poleward flow converges as meridians close in


def test_inflow_converges(spark: SparkSession) -> None:
    out = etl.divergence(grid(spark, lambda i, j: -0.01 * (j - 2), lambda i, j: -0.01 * (i - 2)))
    assert div_at(out, 2, 2) < 0


def daily_div(spark: SparkSession, rows: list[tuple[int, float, float, float]]) -> DataFrame:
    return spark.createDataFrame(
        [(date(2026, 8, d), lat, lon, dv) for d, lat, lon, dv in rows],
        "date DATE, lat DOUBLE, lon DOUBLE, div DOUBLE",
    )


def test_cell_convergence_ranks_persistent_negative_divergence_first(spark: SparkSession) -> None:
    rows = []
    for d in (1, 2, 3, 4):
        rows += [(d, 35.125, -140.125, -3.0), (d, 35.375, -140.375, -1.0)]  # cell (35,-141)
        rows += [(d, 30.125, -150.125, 2.0)]  # cell (30,-151): always diverging
        rows += [(d, 40.125, -135.125, -9.0 if d == 1 else 1.0)]  # one strong day, then not
        rows += [(d, 25.125, -160.125, 0.5)]
    cells = etl.cell_convergence(daily_div(spark, rows), min_subcells=1).orderBy("rank").collect()
    assert [(c.cell_lat, c.cell_lon) for c in cells] == [
        (35, -141),
        (40, -136),
        (25, -161),
        (30, -151),
    ]
    top = cells[0]
    assert (top.lat, top.lon) == (35.5, -140.5)  # cell centre
    assert top.mean_div == pytest.approx(-2.0)
    assert top.frac_convergent == 1.0 and top.n_days == 4
    # Top quartile of 4 cells is one cell; the runner-up is convergent on only 1 day in 4.
    assert [c.is_hotspot for c in cells] == [True, False, False, False]
    assert cells[1].frac_convergent == 0.25


def test_cell_convergence_skips_days_with_too_few_subcells(spark: SparkSession) -> None:
    rows = [(1, 35.125, -140.125, -1.0), (1, 35.375, -140.125, -1.0), (2, 35.125, -140.125, 5.0)]
    cells = etl.cell_convergence(daily_div(spark, rows), min_subcells=2).collect()
    assert [(c.n_days, c.mean_div) for c in cells] == [(1, -1.0)]


def test_climatology_is_monthly_cell_mean(spark: SparkSession) -> None:
    rows = [
        (date(2025, 8, 1), 35.125, -140.125, 0.1, 0.0),
        (date(2026, 8, 5), 35.125, -140.125, 0.3, -0.2),
        (date(2026, 9, 1), 35.125, -140.125, 9.0, 9.0),
    ]
    df = spark.createDataFrame(rows, "date DATE, lat DOUBLE, lon DOUBLE, u FLOAT, v FLOAT")
    out = {r.month: r for r in etl.climatology(df).collect()}
    assert out[8].u_mean == pytest.approx(0.2) and out[8].v_mean == pytest.approx(-0.1)
    assert out[8].n_days == 2 and out[9].n_days == 1


def mp_feature(lat: float, lon: float, conc: float | None, unit: str = "pieces/m3") -> dict:
    return {
        "attributes": {
            "Latitude__degree_": lat,
            "Longitude_degree_": lon,
            "Medium": "Ocean water",
            "Sampling_Method": "Neuston net",
            "Microplastics_measurement": conc,
            "Unit": unit,
            "Short_Reference": "Law et al.2014",
            "Date_m_d_yyyy": 1016668800000,
        },
        "geometry": {"x": lon, "y": lat},
    }


def bronze(spark: SparkSession, feats: list[dict]) -> DataFrame:
    doc = json.dumps({"fetched_at": "2026-10-31T00:00:00+00:00", "features": feats})
    return spark.read.json(spark.sparkContext.parallelize([doc]))


def test_samples_keep_ocean_water_in_one_unit(spark: SparkSession) -> None:
    feats = [
        mp_feature(35.2, -140.7, 0.5),
        mp_feature(35.2, -140.7, None),
        mp_feature(35.2, -140.7, 3.0, unit="pieces/10 mins"),
    ]
    rows = etl.samples_from_bronze(bronze(spark, feats)).collect()
    assert len(rows) == 1
    r = rows[0]
    assert (r.lat, r.lon, r.conc, r.method) == (35.2, -140.7, 0.5, "Neuston net")
    assert r.sample_date == date(2002, 3, 21)


def cells_fixture(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(35, -141, True), (30, -151, False), (25, -161, False)],
        "cell_lat INT, cell_lon INT, is_hotspot BOOLEAN",
    )


def samples_fixture(spark: SparkSession) -> DataFrame:
    pts = [(35.5, -140.5, c) for c in (10.0, 20.0, 30.0)]
    pts += [(30.5, -150.5, 1.0), (30.5, -150.5, 2.0), (25.5, -160.5, 3.0), (25.5, -160.5, 4.0)]
    pts += [(44.5, -131.5, 1000.0)]  # outside every analysed cell: ignored
    return spark.createDataFrame(pts, "lat DOUBLE, lon DOUBLE, conc DOUBLE")


def test_hotspot_validation_compares_convergent_cells_with_the_rest(spark: SparkSession) -> None:
    v = etl.hotspot_validation(cells_fixture(spark), samples_fixture(spark)).collect()[0]
    assert (v.n_convergent, v.n_rest) == (3, 4)
    assert (v.median_convergent, v.median_rest) == (20.0, 2.5)
    assert v.median_ratio == pytest.approx(8.0)
    assert v.mean_ratio == pytest.approx(20.0 / 2.5)


def test_cell_microplastics_counts_samples_per_cell(spark: SparkSession) -> None:
    out = {
        (r.cell_lat, r.cell_lon): r
        for r in etl.cell_microplastics(cells_fixture(spark), samples_fixture(spark)).collect()
    }
    assert (out[(35, -141)].mp_n, out[(35, -141)].mp_median) == (3, 20.0)
    assert out[(30, -151)].mp_n == 2


def test_grid_arrays_builds_a_dense_cube_with_nan_gaps() -> None:
    t0, t1 = epoch(date(2026, 9, 1)), epoch(date(2026, 9, 2))
    rows = [
        (t1, 30.125, -150.125, 0.1, 0.2),
        (t0, 30.125, -150.125, 0.3, 0.4),
        (t0, 30.375, -149.875, 0.5, 0.6),
    ]
    g = etl.grid_arrays(rows)
    assert g["time"].tolist() == [t0, t1]
    assert g["lat"].tolist() == [30.125, 30.375]
    assert g["lon"].tolist() == [-150.125, -149.875]
    assert g["u"].shape == (2, 2, 2) and g["u"].dtype == np.float32
    assert g["u"][0, 0, 0] == pytest.approx(0.3) and g["v"][1, 0, 0] == pytest.approx(0.2)
    assert np.isnan(g["u"][1, 1, 1])
