"""Batch layer: bronze SCUD NetCDF + NCEI microplastics -> silver currents -> gold views + exports.

bronze/currents (monthly NetCDF, manifest) -> silver/currents (time, lat, lon, u, v; by date)
  -> gold/climatology   monthly mean u/v per quarter-degree cell
  -> gold/convergence   1-degree cells ranked by persistent negative divergence (+ microplastics)
  -> gold/hotspot_validation   measured concentration in convergent cells vs the rest
  -> gold/exports/      mission-window u/v cube (NPZ) and hotspots (JSON) for the API/simulator

Runs with spark-submit in the oceanclean-spark image (Compose service `spark-batch`).
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone

import netCDF4
import numpy as np
from oceanclean_common.regions import (
    BRONZE_MICROPLASTICS,
    CURRENTS_MANIFEST,
    EXPORT_HOTSPOTS,
    EXPORT_MISSION_GRID,
    GOLD_CLIMATOLOGY,
    GOLD_CONVERGENCE,
    GOLD_HOTSPOT_VALIDATION,
    MISSION_BOX,
    SILVER_CURRENTS,
)
from oceanclean_common.settings import lake_url, s3a_conf, to_utc
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

log = logging.getLogger("currents_etl")

GRID_DEG = 0.25  # SCUD resolution
EARTH_RADIUS_M = 6_371_000.0
MIN_SUBCELLS = 8  # of 16 quarter-degree cells, for a 1-degree cell's daily divergence to count
HOTSPOT_SHARE = 0.25  # hotspots: the most convergent quarter of 1-degree cells...
HOTSPOT_MIN_FRAC = 0.5  # ...that also converge on more than half of the days
MISSION_DAYS = 45
MP_UNIT = "pieces/m3"  # 2,310 of 2,315 gyre samples; the rest are beach counts

# One row per (time, latitude) of a NetCDF file; exploded to cells in the JVM, not in Python.
ROW_DDL = "time DOUBLE, lat DOUBLE, lon ARRAY<DOUBLE>, u ARRAY<FLOAT>, v ARRAY<FLOAT>"


def month_of(path: str) -> str:
    """'.../scud_pac_2026-08.nc' -> '2026-08'."""
    return path.rsplit("_", 1)[-1].removesuffix(".nc")


def netcdf_rows(
    data: bytes, month: str | None
) -> Iterator[tuple[float, float, list[float], list[float | None], list[float | None]]]:
    """NetCDF bytes -> ROW_DDL rows; masked cells become None. Only days in `month` are kept:
    ERDDAP snaps a missing edge day to the nearest one, which can sit in the next month."""
    with netCDF4.Dataset("bronze.nc", memory=data) as ds:
        units = ds["time"].units
        if not units.startswith("seconds since 1970-01-01"):
            raise ValueError(f"unexpected time units: {units}")
        times = ds["time"][:].tolist()
        lats = ds["latitude"][:].tolist()
        lons = ds["longitude"][:].tolist()
        u = np.ma.masked_invalid(ds["u"][:])
        v = np.ma.masked_invalid(ds["v"][:])
    for ti, t in enumerate(times):
        if month and datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m") != month:
            continue
        for li, lat in enumerate(lats):
            yield t, lat, lons, u[ti, li].tolist(None), v[ti, li].tolist(None)


def lon180(c: Column) -> Column:
    return F.when(c > 180, c - 360).otherwise(c)


def explode_grid(rows: DataFrame) -> DataFrame:
    """ROW_DDL rows -> silver currents (time, date, lat, lon in -180..180, u, v); drops gaps."""
    cell = F.explode(F.arrays_zip("lon", "u", "v")).alias("c")
    return (
        rows.select("time", "lat", cell)
        .select(
            F.timestamp_seconds("time").alias("time"),
            "lat",
            lon180(F.col("c.lon")).alias("lon"),
            F.col("c.u").alias("u"),
            F.col("c.v").alias("v"),
        )
        .where(F.col("u").isNotNull() & F.col("v").isNotNull())
        .withColumn("date", F.to_date("time"))
    )


def grid_index(c: str) -> Column:
    """Integer quarter-degree index; neighbours differ by exactly 1."""
    return F.floor(F.col(c) / GRID_DEG)


def cell_index(c: str) -> Column:
    """1-degree cell (south-west corner) holding a point."""
    return F.floor(F.col(c)).cast("int")


def divergence(silver: DataFrame) -> DataFrame:
    """Daily horizontal divergence (1/s) per cell from central neighbour differences on the sphere:
    div = [du/dlambda + d(v cos phi)/dphi] / (R cos phi). Null where a neighbour is missing."""
    g = silver.select(
        "date",
        "lat",
        "lon",
        "u",
        (F.col("v") * F.cos(F.radians("lat"))).alias("vcos"),
        grid_index("lat").alias("i"),
        grid_index("lon").alias("j"),
    )
    along_lon = Window.partitionBy("date", "i").orderBy("j")
    along_lat = Window.partitionBy("date", "j").orderBy("i")

    def at(col: str, w: Window, offset: int) -> Column:
        return F.first(col).over(w.rangeBetween(offset, offset))

    step = 2 * math.radians(GRID_DEG) * EARTH_RADIUS_M * F.cos(F.radians("lat"))
    du = at("u", along_lon, 1) - at("u", along_lon, -1)
    dvcos = at("vcos", along_lat, 1) - at("vcos", along_lat, -1)
    return g.select("date", "lat", "lon", ((du + dvcos) / step).alias("div"))


def cell_convergence(
    div: DataFrame,
    min_subcells: int = MIN_SUBCELLS,
    share: float = HOTSPOT_SHARE,
    min_frac: float = HOTSPOT_MIN_FRAC,
) -> DataFrame:
    """1-degree cells ranked by mean daily divergence, most convergent (most negative) first.
    frac_convergent = share of days the cell converged; hotspots are persistent top-share cells."""
    daily = (
        div.where(F.col("div").isNotNull())
        .groupBy("date", cell_index("lat").alias("cell_lat"), cell_index("lon").alias("cell_lon"))
        .agg(F.avg("div").alias("div"), F.count("*").alias("n"))
        .where(F.col("n") >= min_subcells)
    )
    cells = daily.groupBy("cell_lat", "cell_lon").agg(
        F.avg("div").alias("mean_div"),
        F.avg((F.col("div") < 0).cast("double")).alias("frac_convergent"),
        F.count("*").alias("n_days"),
    )
    # One partition on purpose: ~1,250 cells ranked globally.
    everything = Window.partitionBy(F.lit(0))
    ranked = everything.orderBy("mean_div", "cell_lat", "cell_lon")
    n_cells = F.count(F.lit(1)).over(everything)
    return (
        cells.withColumn("rank", F.row_number().over(ranked))
        .withColumn(
            "is_hotspot",
            (F.col("rank") <= F.ceil(n_cells * share)) & (F.col("frac_convergent") > min_frac),
        )
        .withColumn("lat", F.col("cell_lat") + 0.5)
        .withColumn("lon", F.col("cell_lon") + 0.5)
    )


def climatology(silver: DataFrame) -> DataFrame:
    return silver.groupBy(F.month("date").alias("month"), "lat", "lon").agg(
        F.avg("u").alias("u_mean"), F.avg("v").alias("v_mean"), F.count("*").alias("n_days")
    )


def samples_from_bronze(raw: DataFrame) -> DataFrame:
    """Raw ArcGIS features -> open-ocean samples in one unit (concentrations aren't comparable
    across units)."""
    a = raw.select(F.explode("features").alias("f")).select("f.attributes.*")
    return a.where(
        (F.col("Unit") == MP_UNIT)
        & (F.col("Medium") == "Ocean water")
        & F.col("Microplastics_measurement").isNotNull()
    ).select(
        F.col("Latitude__degree_").cast("double").alias("lat"),
        F.col("Longitude_degree_").cast("double").alias("lon"),
        F.col("Microplastics_measurement").cast("double").alias("conc"),
        F.to_date(F.timestamp_millis("Date_m_d_yyyy")).alias("sample_date"),
        F.col("Sampling_Method").alias("method"),
        F.col("Short_Reference").alias("reference"),
    )


def samples_in_cells(cells: DataFrame, samples: DataFrame) -> DataFrame:
    """Samples tagged with their 1-degree cell; samples outside analysed cells are dropped."""
    tagged = samples.withColumn("cell_lat", cell_index("lat")).withColumn(
        "cell_lon", cell_index("lon")
    )
    return tagged.join(cells.select("cell_lat", "cell_lon", "is_hotspot"), ["cell_lat", "cell_lon"])


def hotspot_validation(cells: DataFrame, samples: DataFrame) -> DataFrame:
    """One row: measured concentration in hotspot cells vs all other analysed cells."""
    s = samples_in_cells(cells, samples)
    hot, rest = F.col("is_hotspot"), ~F.col("is_hotspot")
    return (
        s.agg(
            F.count(F.when(hot, 1)).alias("n_convergent"),
            F.count(F.when(rest, 1)).alias("n_rest"),
            F.expr("percentile(CASE WHEN is_hotspot THEN conc END, 0.5)").alias(
                "median_convergent"
            ),
            F.expr("percentile(CASE WHEN NOT is_hotspot THEN conc END, 0.5)").alias("median_rest"),
            F.avg(F.when(hot, F.col("conc"))).alias("mean_convergent"),
            F.avg(F.when(rest, F.col("conc"))).alias("mean_rest"),
        )
        .withColumn("median_ratio", F.col("median_convergent") / F.col("median_rest"))
        .withColumn("mean_ratio", F.col("mean_convergent") / F.col("mean_rest"))
        .withColumn("unit", F.lit(MP_UNIT))
        .withColumn("cell_deg", F.lit(1))
    )


def cell_microplastics(cells: DataFrame, samples: DataFrame) -> DataFrame:
    """Cells plus their sample count and median concentration (patch-seeding weights)."""
    per_cell = (
        samples_in_cells(cells, samples)
        .groupBy("cell_lat", "cell_lon")
        .agg(
            F.count("*").alias("mp_n"),
            F.expr("percentile(conc, 0.5)").alias("mp_median"),
        )
    )
    return cells.join(per_cell, ["cell_lat", "cell_lon"], "left").fillna(0, ["mp_n"])


def grid_arrays(rows: Iterable[tuple[float, float, float, float, float]]) -> dict[str, np.ndarray]:
    """(epoch_s, lat, lon, u, v) rows -> sorted axes, float32 [time, lat, lon] cubes, NaN gaps."""
    rows = list(rows)
    axes = [sorted({r[k] for r in rows}) for k in range(3)]
    index = [{x: n for n, x in enumerate(a)} for a in axes]
    shape = tuple(len(a) for a in axes)
    u = np.full(shape, np.nan, dtype=np.float32)
    v = np.full(shape, np.nan, dtype=np.float32)
    for t, la, lo, uu, vv in rows:
        at = (index[0][t], index[1][la], index[2][lo])
        u[at], v[at] = uu, vv
    time, lat, lon = (np.array(a, dtype=np.float64) for a in axes)
    return {"time": time, "lat": lat, "lon": lon, "u": u, "v": v}


def write_bytes(spark: SparkSession, url: str, data: bytes) -> None:
    jvm = spark.sparkContext._jvm
    path = jvm.org.apache.hadoop.fs.Path(url)
    fs = path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    out = fs.create(path, True)
    try:
        out.write(bytearray(data))
    finally:
        out.close()


def main() -> None:
    # Root at WARNING: py4j logs every gateway call at INFO.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    log.setLevel(logging.INFO)
    env = os.environ
    builder = (
        SparkSession.builder.appName("oceanclean-batch-etl")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "16")
        # Rewrite only the dates this run produced; older silver history stays.
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
    )
    for k, v in s3a_conf(env).items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    def url(key: str) -> str:
        return lake_url(env, key)

    manifest = json.loads(spark.read.text(url(CURRENTS_MANIFEST), wholetext=True).first()[0])
    paths = [url(k) for k in manifest["files"]]
    log.info(
        "bronze: %d NetCDF files, %s..%s, source=%s fetched_at=%s",
        len(paths),
        manifest["start"],
        manifest["end"],
        manifest["source"],
        manifest["fetched_at"],
    )

    # Silver: one task per monthly file parses NetCDF in Python; the JVM explodes the cells.
    raw = spark.sparkContext.binaryFiles(",".join(paths), minPartitions=len(paths)).flatMap(
        lambda kv: netcdf_rows(kv[1], month_of(kv[0]))
    )
    silver = explode_grid(spark.createDataFrame(raw, ROW_DDL))
    silver.repartition("date").write.mode("overwrite").partitionBy("date").parquet(
        url(SILVER_CURRENTS)
    )
    silver = spark.read.parquet(url(SILVER_CURRENTS)).where(
        F.col("date").between(manifest["start"], manifest["end"])
    )
    n_rows = silver.count()
    n_days = silver.select("date").distinct().count()
    log.info(
        "silver/currents: %d grid vectors (%d u/v values) over %d days", n_rows, 2 * n_rows, n_days
    )

    clim = climatology(silver)
    clim.write.mode("overwrite").partitionBy("month").parquet(url(GOLD_CLIMATOLOGY))

    cells = cell_convergence(divergence(silver)).cache()
    samples = samples_from_bronze(
        spark.read.option("multiLine", True).json(url(BRONZE_MICROPLASTICS))
    ).cache()
    gold_cells = cell_microplastics(cells, samples).orderBy("rank").cache()
    gold_cells.coalesce(1).write.mode("overwrite").parquet(url(GOLD_CONVERGENCE))
    validation = (
        hotspot_validation(cells, samples)
        .withColumn("currents_start", F.lit(manifest["start"]))
        .withColumn("currents_end", F.lit(manifest["end"]))
        .withColumn("computed_at", F.current_timestamp())
    )
    validation.coalesce(1).write.mode("overwrite").parquet(url(GOLD_HOTSPOT_VALIDATION))
    report = validation.first().asDict()

    # Exports: mission-window cube for routing/simulator, hotspots for the map and patch seeding.
    box = MISSION_BOX
    mission = silver.where(
        F.col("lat").between(box.lat_min, box.lat_max)
        & F.col("lon").between(box.lon_min, box.lon_max)
    )
    days = mission.select("date").distinct().orderBy(F.desc("date")).limit(MISSION_DAYS).collect()
    cube = grid_arrays(
        mission.where(F.col("date") >= min(d.date for d in days))
        .select(F.unix_timestamp("time").cast("double"), "lat", "lon", "u", "v")
        .collect()
    )
    buf = io.BytesIO()
    np.savez_compressed(buf, **cube)
    write_bytes(spark, url(EXPORT_MISSION_GRID), buf.getvalue())

    hot = [r.asDict() for r in gold_cells.where("is_hotspot").collect()]
    keep = ("rank", "lat", "lon", "mean_div", "frac_convergent", "n_days", "mp_n", "mp_median")
    summary = {
        k: to_utc(x).isoformat() if isinstance(x, datetime) else x for k, x in report.items()
    }
    doc = {
        "cell_deg": 1,
        "validation": summary,
        "hotspots": [{k: h[k] for k in keep} for h in hot],
    }
    write_bytes(spark, url(EXPORT_HOTSPOTS), json.dumps(doc).encode())

    log.info("gold/climatology: %d rows", clim.count())
    log.info("gold/convergence: %d 1-degree cells, %d hotspots", gold_cells.count(), len(hot))
    log.info(
        "microplastics: %d %s samples, %d in convergent cells, %d in the rest",
        samples.count(),
        MP_UNIT,
        report["n_convergent"],
        report["n_rest"],
    )
    log.info(
        "hotspot_validation: median %.4g vs %.4g -> %.2fx; mean %.4g vs %.4g -> %.2fx",
        report["median_convergent"],
        report["median_rest"],
        report["median_ratio"],
        report["mean_convergent"],
        report["mean_rest"],
        report["mean_ratio"],
    )
    nan = int(np.isnan(cube["u"]).sum())
    log.info(
        "exports: mission grid %s (%d days, %d NaN), %d hotspots",
        cube["u"].shape,
        len(cube["time"]),
        nan,
        len(hot),
    )
    spark.stop()


if __name__ == "__main__":
    main()
