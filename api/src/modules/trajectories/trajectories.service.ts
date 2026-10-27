import {
  Inject,
  Injectable,
  InternalServerErrorException,
  Logger,
  NotFoundException,
  Optional,
} from '@nestjs/common';
import { eq } from 'drizzle-orm';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import {
  debrisPatches,
  interceptionRoutes,
  vessels,
  InterceptionRoute,
} from '../../infrastructure/database/schema';
import { DebrisPatchesService } from '../debris-patches/debris-patches.service';
import { VesselsService } from '../vessels/vessels.service';
import { SseStreamService } from '../../infrastructure/sse/sse-stream.service';

@Injectable()
export class TrajectoriesService {
  private readonly logger = new Logger(TrajectoriesService.name);

  constructor(
    @Inject(DRIZZLE_DB) private readonly db: Database,
    private readonly debrisPatchesService: DebrisPatchesService,
    private readonly vesselsService: VesselsService,
    @Optional() private readonly sseService?: SseStreamService,
  ) {}

  async generateRoutes(): Promise<InterceptionRoute[]> {
    // 1. Fetch available vessels and confirmed patches
    const fleetVessels = await this.vesselsService.findAll();
    const confirmedPatches = await this.debrisPatchesService.findAll('CONFIRMED_PATCH');

    if (fleetVessels.length === 0) {
      throw new NotFoundException('No vessels found in fleet');
    }

    if (confirmedPatches.length === 0) {
      this.logger.warn('No confirmed patches available for interception');
      return [];
    }

    const mlSparkUrl = process.env.ML_SPARK_URL || 'http://localhost:8000';

    // 2. Call ml-spark optimizer service
    let optimizationResponse: any;
    try {
      const response = await fetch(`${mlSparkUrl}/api/v1/ml/optimize-routes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vessels: fleetVessels.map((v) => ({
            id: v.id,
            name: v.name,
            latitude: v.latitude,
            longitude: v.longitude,
            h3_index: v.h3Index,
            max_capacity_tons: v.maxCapacityTons,
            current_load_tons: v.currentLoadTons,
            cruise_speed_knots: v.cruiseSpeedKnots,
            fuel_level_pct: v.fuelLevelPct,
          })),
          patches: confirmedPatches.map((p) => ({
            id: p.id,
            h3_index: p.h3Index,
            latitude: p.latitude,
            longitude: p.longitude,
            estimated_mass_kg: p.estimatedMassKg,
            polymer_density_kg_km2: p.polymerDensityKgKm2,
            confidence_score: p.confidenceScore,
            status: p.status,
            current_velocity_ms: p.currentVelocityMs,
            current_direction_deg: p.currentDirectionDeg,
            last_observed_at: p.lastObservedAt.toISOString(),
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`ML service responded with status ${response.status}`);
      }

      optimizationResponse = await response.json();
    } catch (err: any) {
      this.logger.error(`Failed to invoke ML optimization engine: ${err.message}`);
      throw new InternalServerErrorException(
        `ML Optimization Engine unreachable or returned error: ${err.message}`,
      );
    }

    const savedRoutes: InterceptionRoute[] = [];
    const assignedPatchIds: string[] = [];

    // 3. Persist interception routes and update patch statuses
    for (const routeData of optimizationResponse.routes || []) {
      const [route] = await this.db
        .insert(interceptionRoutes)
        .values({
          vesselId: routeData.vesselId,
          status: 'PLANNED',
          totalDistanceNm: routeData.totalDistanceNm,
          estimatedFuelLiters: routeData.estimatedFuelLiters,
          expectedYieldKg: routeData.expectedYieldKg,
          waypointsJson: routeData.waypoints,
          createdAt: new Date(),
        })
        .returning();

      savedRoutes.push(route);

      for (const wp of routeData.waypoints || []) {
        if (wp.patchId) {
          assignedPatchIds.push(wp.patchId);
        }
      }
    }

    for (const patchId of assignedPatchIds) {
      await this.debrisPatchesService.updateStatus(patchId, 'INTERCEPT_ASSIGNED');
    }

    this.sseService?.emit({
      stage: 'ORTOOLS_ROUTE',
      level: 'SUCCESS',
      message: `Generated ${savedRoutes.length} fuel-optimized vessel interception routes`,
      payload: { routesCount: savedRoutes.length, assignedPatches: assignedPatchIds.length },
    });

    return savedRoutes;
  }

  async completeWaypoint(
    routeId: string,
    h3Index: string,
  ): Promise<{ message: string; route: InterceptionRoute; vessel: any }> {
    const [route] = await this.db
      .select()
      .from(interceptionRoutes)
      .where(eq(interceptionRoutes.id, routeId));

    if (!route) {
      throw new NotFoundException(`Route with id ${routeId} not found`);
    }

    const waypoints = (route.waypointsJson as any[]) || [];
    const targetWp = waypoints.find((w) => w.h3Index === h3Index);

    if (!targetWp) {
      throw new NotFoundException(
        `Waypoint with H3 cell ${h3Index} not found on route ${routeId}`,
      );
    }

    targetWp.completed = true;
    targetWp.completedAt = new Date().toISOString();

    const harvestedKg = targetWp.estimatedMassKg || 0;
    const harvestedTons = harvestedKg / 1000.0;

    // Increment vessel current load
    const updatedVessel = await this.vesselsService.incrementLoad(
      route.vesselId,
      harvestedTons,
    );

    // If there is an associated patch, mark CLEARED
    if (targetWp.patchId) {
      await this.debrisPatchesService.updateStatus(targetWp.patchId, 'CLEARED');
    }

    // Check if all waypoints completed
    const allCompleted = waypoints.every((w) => w.completed === true);
    const updatedStatus = allCompleted ? 'COMPLETED' : 'ACTIVE';

    const [updatedRoute] = await this.db
      .update(interceptionRoutes)
      .set({
        waypointsJson: waypoints,
        status: updatedStatus,
      })
      .where(eq(interceptionRoutes.id, routeId))
      .returning();

    return {
      message: `Waypoint ${h3Index} harvested and marked CLEARED. Yield: ${harvestedKg} kg`,
      route: updatedRoute,
      vessel: updatedVessel,
    };
  }

  async findAll(): Promise<InterceptionRoute[]> {
    return this.db.select().from(interceptionRoutes);
  }

  async findById(id: string): Promise<InterceptionRoute> {
    const [route] = await this.db
      .select()
      .from(interceptionRoutes)
      .where(eq(interceptionRoutes.id, id));

    if (!route) {
      throw new NotFoundException(`Route ${id} not found`);
    }
    return route;
  }

  async getAnalyticsHotspots(): Promise<any> {
    const mlSparkUrl = process.env.ML_SPARK_URL || 'http://localhost:8000';
    try {
      const response = await fetch(`${mlSparkUrl}/api/v1/ml/analytics/hotspots`);
      if (!response.ok) {
        throw new Error(`ML Hotspots returned status ${response.status}`);
      }
      return await response.json();
    } catch (err: any) {
      this.logger.warn(`Could not reach ML Spark hotspots service: ${err.message}`);
      return {
        timestamp: new Date().toISOString(),
        clusterCount: 0,
        hotspots: [],
        message: `Offline fallback or ML engine pending: ${err.message}`,
      };
    }
  }

  async getCurrentsGrid(): Promise<any> {
    const mlSparkUrl = process.env.ML_SPARK_URL || 'http://localhost:8000';
    try {
      const response = await fetch(`${mlSparkUrl}/api/v1/ml/currents-grid`);
      if (!response.ok) {
        throw new Error(`Currents grid returned status ${response.status}`);
      }
      return await response.json();
    } catch (err: any) {
      this.logger.warn(`Could not reach ML Spark currents grid: ${err.message}`);
      // Fallback deterministic grid for UI
      const points: any[] = [];
      for (let lat = 26; lat <= 36; lat += 2) {
        for (let lon = -152; lon <= -136; lon += 2) {
          points.push({
            lat,
            lon,
            u_ms: 0.5,
            v_ms: 0.0,
            velocity_ms: 0.5,
            direction_deg: 90.0,
            wave_height_m: 1.5,
          });
        }
      }
      return { grid_points: points, count: points.length };
    }
  }
}

