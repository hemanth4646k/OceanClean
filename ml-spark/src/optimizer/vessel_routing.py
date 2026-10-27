"""Current-Assisted Moving-Target Vessel Fleet Trajectory Optimizer using Google OR-Tools."""

import logging
import math
from typing import Any

import h3
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from src.drift.lagrangian import advect_point, calculate_uv_components

logger = logging.getLogger(__name__)

EARTH_RADIUS_METERS = 6371000.0
METERS_PER_NAUTICAL_MILE = 1852.0
NOMINAL_FUEL_LITERS_PER_NM = 15.0  # Typical marine cleanup vessel consumption
BETA_CURRENT_ASSISTANCE = 0.25     # Reward for sailing with current in [0.1, 0.35]
MAX_CURRENT_VELOCITY_MS = 2.0      # Reference maximum current velocity for normalization


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes Haversine distance in nautical miles between two WGS84 coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    distance_meters = EARTH_RADIUS_METERS * c
    return distance_meters / METERS_PER_NAUTICAL_MILE


def calculate_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates initial bearing in degrees from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing_rad = math.atan2(y, x)
    return (math.degrees(bearing_rad) + 360.0) % 360.0


def calculate_edge_cost(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    current_velocity_ms: float = 0.5,
    current_direction_deg: float = 90.0,
    sea_state_wave_m: float = 1.5,
) -> tuple[float, float]:
    """Calculates asymmetric fuel traversal cost and distance between two locations.
    
    Formula:
    C(i, j) = d_ij * (1 - beta * (u_ij . v_c) / ||v_c||_max) * wave_multiplier
    """
    distance_nm = haversine_nm(lat1, lon1, lat2, lon2)
    if distance_nm < 0.001:
        return 0.0, 0.0

    bearing_deg = calculate_bearing_deg(lat1, lon1, lat2, lon2)
    u_heading, v_heading = calculate_uv_components(1.0, bearing_deg)
    u_current, v_current = calculate_uv_components(current_velocity_ms, current_direction_deg)

    # Dot product between heading unit vector and ocean current vector
    dot_product = (u_heading * u_current) + (v_heading * v_current)
    normalized_alignment = max(-1.0, min(1.0, dot_product / MAX_CURRENT_VELOCITY_MS))

    # Sailing with current reduces fuel burn; sailing against current increases fuel burn
    current_factor = 1.0 - (BETA_CURRENT_ASSISTANCE * normalized_alignment)

    # Severe wave hazard avoidance (> 4.0 meters triggers 300% penalty)
    wave_penalty = 4.0 if sea_state_wave_m > 4.0 else 1.0

    traversal_cost = distance_nm * current_factor * wave_penalty
    fuel_liters = distance_nm * NOMINAL_FUEL_LITERS_PER_NM * current_factor * wave_penalty
    return traversal_cost, fuel_liters


class FleetRouteOptimizer:
    async def optimize_fleet_routes(
        self,
        vessels: list[dict[str, Any]],
        patches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Dispatches vessels to confirmed debris patches using OR-Tools CVRPTW

        accounting for moving patch coordinates, fuel burn, and vessel capacities.
        Uses open-ended routing (dummy end depot with 0 return cost) for interception missions.
        """
        if not vessels:
            return {"routes": [], "total_fuel_liters": 0.0, "total_yield_kg": 0.0}

        if not patches:
            return {
                "routes": [
                    {
                        "vesselId": v["id"],
                        "vesselName": v.get("name", "Vessel"),
                        "waypoints": [],
                        "totalDistanceNm": 0.0,
                        "estimatedFuelLiters": 0.0,
                        "expectedYieldKg": 0.0,
                    }
                    for v in vessels
                ],
                "total_fuel_liters": 0.0,
                "total_yield_kg": 0.0,
            }

        # Step 1: Project each patch's coordinates forward if needed
        drifted_patches = []
        for p in patches:
            p_lat = p["latitude"]
            p_lon = p["longitude"]
            vel_ms = p.get("current_velocity_ms") or 0.5
            dir_deg = p.get("current_direction_deg") or 90.0

            # Use predicted coordinates if already computed, or if drift_hours specified
            drift_hours = p.get("drift_hours", 0.0)
            if "predicted_lat" in p and "predicted_lon" in p:
                pred_lat = p["predicted_lat"]
                pred_lon = p["predicted_lon"]
            elif "predicted_lat6h" in p and p["predicted_lat6h"] is not None:
                pred_lat = p["predicted_lat6h"]
                pred_lon = p["predicted_lon6h"]
            elif drift_hours > 0.0:
                u, v = calculate_uv_components(vel_ms, dir_deg)
                pred_lat, pred_lon = advect_point(p_lat, p_lon, u, v, drift_hours * 3600.0)
            else:
                pred_lat, pred_lon = p_lat, p_lon

            pred_h3 = h3.latlng_to_cell(pred_lat, pred_lon, 7)

            drifted_patches.append({
                **p,
                "projected_lat": pred_lat,
                "projected_lon": pred_lon,
                "projected_h3": pred_h3,
            })

        num_vessels = len(vessels)
        num_patches = len(drifted_patches)
        # Total nodes = num_vessels (start nodes) + num_patches (target nodes) + 1 (dummy end depot)
        dummy_end_node = num_vessels + num_patches
        total_nodes = dummy_end_node + 1

        all_locations = []
        for v in vessels:
            all_locations.append((v["latitude"], v["longitude"]))
        for dp in drifted_patches:
            all_locations.append((dp["projected_lat"], dp["projected_lon"]))
        # Dummy end node location (arbitrary)
        all_locations.append((0.0, 0.0))

        # Build distance & cost matrices
        cost_matrix = [[0] * total_nodes for _ in range(total_nodes)]
        distance_matrix = [[0.0] * total_nodes for _ in range(total_nodes)]
        fuel_matrix = [[0.0] * total_nodes for _ in range(total_nodes)]

        for i in range(total_nodes):
            for j in range(total_nodes):
                if i == j or j == dummy_end_node:
                    # Traversal to dummy end depot costs 0 (open-ended interception mission)
                    cost_matrix[i][j] = 0
                    distance_matrix[i][j] = 0.0
                    fuel_matrix[i][j] = 0.0
                elif i == dummy_end_node:
                    cost_matrix[i][j] = 0
                    distance_matrix[i][j] = 0.0
                    fuel_matrix[i][j] = 0.0
                else:
                    lat1, lon1 = all_locations[i]
                    lat2, lon2 = all_locations[j]
                    p_info = drifted_patches[j - num_vessels] if (num_vessels <= j < dummy_end_node) else {}
                    vel = p_info.get("current_velocity_ms", 0.5)
                    d_deg = p_info.get("current_direction_deg", 90.0)
                    wave = p_info.get("sea_state_wave_m", 1.5)

                    c_cost, f_liters = calculate_edge_cost(lat1, lon1, lat2, lon2, vel, d_deg, wave)
                    dist = haversine_nm(lat1, lon1, lat2, lon2)

                    cost_matrix[i][j] = int(c_cost * 100.0)
                    distance_matrix[i][j] = dist
                    fuel_matrix[i][j] = f_liters

        # Demands (in integer kg)
        demands = [0] * total_nodes
        for idx, dp in enumerate(drifted_patches):
            demands[num_vessels + idx] = int(dp.get("estimated_mass_kg") or 1000.0)

        # Vessel remaining capacities (in integer kg)
        vehicle_capacities = []
        for v in vessels:
            remaining_tons = max(0.0, float(v["max_capacity_tons"]) - float(v.get("current_load_tons", 0.0)))
            vehicle_capacities.append(int(remaining_tons * 1000.0))

        # Each vessel starts at node v, and all finish at dummy_end_node
        starts = list(range(num_vessels))
        ends = [dummy_end_node] * num_vessels

        manager = pywrapcp.RoutingIndexManager(total_nodes, num_vessels, starts, ends)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return cost_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Capacity Dimension
        def demand_callback(from_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            return demands[from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # null capacity slack
            vehicle_capacities,
            True,  # start cumul to zero
            "Capacity",
        )

        # Disjunctions for all debris patch nodes
        for p_idx in range(num_patches):
            node = num_vessels + p_idx
            index = manager.NodeToIndex(node)
            patch_mass = demands[node]
            density = drifted_patches[p_idx].get("polymer_density_kg_km2", 10.0)
            penalty = int(patch_mass * 100 + density * 50)
            routing.AddDisjunction([index], penalty)

        # Search Parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 2

        solution = routing.SolveWithParameters(search_parameters)

        routes_out = []
        fleet_total_fuel = 0.0
        fleet_total_yield = 0.0

        for v_idx in range(num_vessels):
            v = vessels[v_idx]
            v_name = v.get("name", f"Vessel-{v_idx+1}")
            index = routing.Start(v_idx)
            v_waypoints = []
            v_dist = 0.0
            v_fuel = 0.0
            v_yield = 0.0

            prev_node = manager.IndexToNode(index)

            while not routing.IsEnd(index):
                index = solution.Value(routing.NextVar(index)) if solution else routing.End(v_idx)
                curr_node = manager.IndexToNode(index)

                if num_vessels <= curr_node < dummy_end_node:
                    p_data = drifted_patches[curr_node - num_vessels]
                    step_dist = distance_matrix[prev_node][curr_node]
                    step_fuel = fuel_matrix[prev_node][curr_node]
                    yield_kg = p_data.get("estimated_mass_kg", 0.0)

                    v_dist += step_dist
                    v_fuel += step_fuel
                    v_yield += yield_kg

                    v_waypoints.append({
                        "patchId": p_data["id"],
                        "h3Index": p_data["projected_h3"],
                        "targetLatitude": p_data["projected_lat"],
                        "targetLongitude": p_data["projected_lon"],
                        "estimatedMassKg": yield_kg,
                        "distanceNm": round(step_dist, 2),
                        "estimatedFuelLiters": round(step_fuel, 2),
                        "completed": False,
                    })

                prev_node = curr_node

            fleet_total_fuel += v_fuel
            fleet_total_yield += v_yield

            routes_out.append({
                "vesselId": v["id"],
                "vesselName": v_name,
                "waypoints": v_waypoints,
                "totalDistanceNm": round(v_dist, 2),
                "estimatedFuelLiters": round(v_fuel, 2),
                "expectedYieldKg": round(v_yield, 2),
            })

        return {
            "routes": routes_out,
            "total_fuel_liters": round(fleet_total_fuel, 2),
            "total_yield_kg": round(fleet_total_yield, 2),
        }


optimizer_engine = FleetRouteOptimizer()
