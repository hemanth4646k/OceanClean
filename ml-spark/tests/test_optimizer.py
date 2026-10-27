"""Phase 5 Verification Gate Tests: OR-Tools Current-Assisted CVRPTW Optimizer."""

import pytest

from src.optimizer.vessel_routing import (
    calculate_edge_cost,
    haversine_nm,
    optimizer_engine,
)


def test_edge_cost_rewards_sailing_with_current_over_against_current():
    """Verify that heading with current reduces traversal cost compared to heading against current."""
    lat_center, lon_center = 30.0, -145.0
    lat_east, lon_east = 30.0, -144.0
    lat_west, lon_west = 30.0, -146.0

    # Eastward current: 1.5 m/s at 90 degrees
    current_vel = 1.5
    current_dir = 90.0

    # Distances are identical (symmetric longitudinal separation at same latitude)
    dist_east = haversine_nm(lat_center, lon_center, lat_east, lon_east)
    dist_west = haversine_nm(lat_center, lon_center, lat_west, lon_west)
    assert abs(dist_east - dist_west) < 1e-4

    # Traversal cost sailing East (with current) vs West (against current)
    cost_east, fuel_east = calculate_edge_cost(
        lat_center, lon_center, lat_east, lon_east, current_vel, current_dir, 1.5
    )
    cost_west, fuel_west = calculate_edge_cost(
        lat_center, lon_center, lat_west, lon_west, current_vel, current_dir, 1.5
    )

    assert cost_east < cost_west, f"Cost with current ({cost_east}) should be strictly less than against ({cost_west})"
    assert fuel_east < fuel_west, f"Fuel with current ({fuel_east}) should be strictly less than against ({fuel_west})"


@pytest.mark.asyncio
async def test_solver_selects_patch_aligned_with_current_given_equidistant_targets():
    """Success Criteria 1: test_optimizer.py proves that given two equidistant patches of equal mass,

    the OR-Tools solver selects the patch aligned WITH the ocean current at lower fuel cost.
    """
    # Vessel at (30.0, -145.0) with capacity for ONLY ONE 5-ton patch
    vessels = [
        {
            "id": "vessel-single-capacity",
            "name": "OceanHarvester-1",
            "latitude": 30.0,
            "longitude": -145.0,
            "max_capacity_tons": 6.0,
            "current_load_tons": 0.0,  # 6 tons capacity remaining
            "cruise_speed_knots": 12.0,
        }
    ]

    # Two equidistant patches of 5 tons each
    # Patch A is East (sailing with current), Patch B is West (sailing against current)
    patches = [
        {
            "id": "patch-east-with-current",
            "h3_index": "87283472bffffff",
            "latitude": 30.0,
            "longitude": -144.2,  # East
            "estimated_mass_kg": 5000.0,
            "polymer_density_kg_km2": 50.0,
            "current_velocity_ms": 1.5,
            "current_direction_deg": 90.0,  # Eastward current
            "sea_state_wave_m": 1.5,
        },
        {
            "id": "patch-west-against-current",
            "h3_index": "87283472affffff",
            "latitude": 30.0,
            "longitude": -145.8,  # West
            "estimated_mass_kg": 5000.0,
            "polymer_density_kg_km2": 50.0,
            "current_velocity_ms": 1.5,
            "current_direction_deg": 90.0,
            "sea_state_wave_m": 1.5,
        },
    ]

    result = await optimizer_engine.optimize_fleet_routes(vessels, patches)
    routes = result["routes"]
    assert len(routes) == 1

    vessel_route = routes[0]
    waypoints = vessel_route["waypoints"]

    # Capacity constraint (6 tons) allows visiting only 1 patch
    assert len(waypoints) == 1, f"Expected exactly 1 waypoint due to capacity, got {len(waypoints)}"

    selected_patch_id = waypoints[0]["patchId"]
    assert selected_patch_id == "patch-east-with-current", (
        f"Expected solver to select patch-east-with-current, but selected {selected_patch_id}"
    )


@pytest.mark.asyncio
async def test_solver_enforces_capacity_and_rejects_oversized_patch():
    """Success Criteria 2: test_optimizer.py proves that vessel capacity constraints

    prevent assigning 50 tons of debris to a vessel with 20 tons of remaining storage.
    """
    vessels = [
        {
            "id": "vessel-limited-storage",
            "name": "SmallInterceptor",
            "latitude": 31.0,
            "longitude": -142.0,
            "max_capacity_tons": 30.0,
            "current_load_tons": 10.0,  # Exactly 20 tons remaining
        }
    ]

    # Patch with 50 metric tons (50,000 kg)
    patches = [
        {
            "id": "patch-oversized-50t",
            "h3_index": "87283472bffffff",
            "latitude": 31.1,
            "longitude": -142.1,
            "estimated_mass_kg": 50000.0,  # 50 tons exceeds 20 tons remaining
            "polymer_density_kg_km2": 80.0,
            "current_velocity_ms": 0.5,
            "current_direction_deg": 90.0,
            "sea_state_wave_m": 1.5,
        }
    ]

    result = await optimizer_engine.optimize_fleet_routes(vessels, patches)
    routes = result["routes"]
    vessel_route = routes[0]

    # Oversized patch must NOT be assigned to this vessel
    assert len(vessel_route["waypoints"]) == 0, (
        f"Oversized 50-ton patch should be dropped by capacity disjunction, but got {vessel_route['waypoints']}"
    )
    assert vessel_route["expectedYieldKg"] == 0.0


def test_wave_storm_hazard_penalty():
    """Verify that seaStateWaveM > 4.0 meters triggers a 300% traversal cost penalty."""
    calm_cost, _ = calculate_edge_cost(28.0, -140.0, 28.5, -140.0, sea_state_wave_m=2.0)
    storm_cost, _ = calculate_edge_cost(28.0, -140.0, 28.5, -140.0, sea_state_wave_m=4.5)
    # 4.0x multiplier
    assert storm_cost >= (calm_cost * 3.8)
