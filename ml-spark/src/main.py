"""FastAPI Microservice Entrypoint for Lagrangian Drift, OR-Tools Optimization, and PySpark Analytics."""

import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.clients.currents_grid import generate_currents_grid
from src.drift.lagrangian import lagrangian_engine
from src.optimizer.vessel_routing import optimizer_engine
from src.spark.batch_hotspots import discover_gyre_hotspots
from src.spark.seed_datalake import generate_synthetic_telemetry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OceanCleanML")

app = FastAPI(
    title="Marine IoT ML & Optimization Microservice",
    version="1.0.0",
    description="Lagrangian Particle Drift, Google OR-Tools Trajectory Optimization & Spark Big Data Hotspots",
)


class PatchDriftRequestItem(BaseModel):
    id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    observed_at: str | None = None


class DriftPredictRequest(BaseModel):
    patches: list[PatchDriftRequestItem]
    horizons: list[int] = [6, 12, 24]


class VesselInput(BaseModel):
    id: str
    name: str | None = "Vessel"
    latitude: float
    longitude: float
    h3_index: str | None = None
    max_capacity_tons: float
    current_load_tons: float = 0.0
    cruise_speed_knots: float = 12.0
    fuel_level_pct: float = 100.0


class DebrisPatchInput(BaseModel):
    id: str
    h3_index: str
    latitude: float
    longitude: float
    estimated_mass_kg: float
    polymer_density_kg_km2: float
    confidence_score: float = 0.8
    status: str = "CONFIRMED_PATCH"
    current_velocity_ms: float | None = 0.5
    current_direction_deg: float | None = 90.0
    sea_state_wave_m: float | None = 1.5
    last_observed_at: str | None = None


class OptimizeRoutesRequest(BaseModel):
    vessels: list[VesselInput]
    patches: list[DebrisPatchInput]


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ml-spark-optimizer"}


@app.get("/api/v1/ml/currents-grid")
async def get_currents_grid(
    min_lat: float = 26.0,
    max_lat: float = 36.0,
    min_lon: float = -152.0,
    max_lon: float = -136.0,
    step_deg: float = 1.5,
):
    grid = await generate_currents_grid(min_lat, max_lat, min_lon, max_lon, step_deg)
    return {"grid_points": grid, "count": len(grid)}


@app.post("/api/v1/ml/predict-drift")
async def predict_drift(payload: DriftPredictRequest):
    results = []
    for patch in payload.patches:
        drift_predictions = await lagrangian_engine.predict_patch_drift(
            lat=patch.latitude,
            lon=patch.longitude,
            horizons_hours=payload.horizons,
        )
        results.append({
            "patch_id": patch.id,
            "origin_lat": patch.latitude,
            "origin_lon": patch.longitude,
            "predictions": drift_predictions,
        })
    return {"results": results}


@app.post("/api/v1/ml/optimize-routes")
async def optimize_routes(payload: OptimizeRoutesRequest):
    try:
        vessels_dict = [v.model_dump() for v in payload.vessels]
        patches_dict = [p.model_dump() for p in payload.patches]
        result = await optimizer_engine.optimize_fleet_routes(vessels_dict, patches_dict)
        return result
    except Exception as exc:
        logger.exception("Route optimization failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/ml/analytics/hotspots")
async def get_hotspots():
    parquet_path = "/tmp/marine-datalake/parquet/year=2026/month=10"
    if not os.path.exists(parquet_path):
        logger.info("Parquet datalake missing. Seeding sample dataset...")
        generate_synthetic_telemetry(num_rows=10_000, output_path=parquet_path)

    try:
        hotspots_data = discover_gyre_hotspots(parquet_path, k=3)
        return hotspots_data
    except Exception as exc:  # noqa: BLE001
        logger.error("Spark hotspot discovery failed: %s", exc)
        return {
            "status": "FALLBACK",
            "cluster_count": 0,
            "hotspots": [],
            "message": str(exc),
        }
