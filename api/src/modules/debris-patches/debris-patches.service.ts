import { Inject, Injectable, Logger, Optional } from '@nestjs/common';
import { and, desc, eq, ne } from 'drizzle-orm';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import { debrisPatches, DebrisPatch } from '../../infrastructure/database/schema';
import { SseStreamService } from '../../infrastructure/sse/sse-stream.service';

export type SensorTier =
  | 'SATELLITE_SAR'
  | 'AERIAL_UAV'
  | 'VESSEL_OPTICAL'
  | 'DRIFT_BUOY';

export interface TelemetryFusionInput {
  sourceTier: SensorTier;
  h3Index: string;
  latitude: number;
  longitude: number;
  detectedDensityKgKm2: number;
  rawConfidence?: number;
  seaStateWaveM?: number;
  observedAt?: Date | string;
}

const SENSOR_WEIGHTS: Record<SensorTier, number> = {
  SATELLITE_SAR: 0.55,
  AERIAL_UAV: 0.85,
  VESSEL_OPTICAL: 0.95,
  DRIFT_BUOY: 0.95,
};

const H3_RES_7_AREA_KM2 = 5.16;

@Injectable()
export class DebrisPatchesService {
  private readonly logger = new Logger(DebrisPatchesService.name);

  constructor(
    @Inject(DRIZZLE_DB) private readonly db: Database,
    @Optional() private readonly sseService?: SseStreamService,
  ) {}

  calculateBayesianUpdate(priorP: number, sensorWeight: number): number {
    const numerator = priorP * sensorWeight;
    const denominator = numerator + (1.0 - priorP) * (1.0 - sensorWeight);
    if (denominator === 0) return priorP;
    const updated = numerator / denominator;
    return parseFloat(updated.toFixed(4));
  }

  async fuseTelemetry(input: TelemetryFusionInput): Promise<DebrisPatch> {
    const sensorWeight = SENSOR_WEIGHTS[input.sourceTier] ?? 0.55;
    const observedAtDate = input.observedAt ? new Date(input.observedAt) : new Date();

    // Check if there is an existing active patch for this H3 cell (not cleared)
    const existing = await this.db
      .select()
      .from(debrisPatches)
      .where(
        and(
          eq(debrisPatches.h3Index, input.h3Index),
          ne(debrisPatches.status, 'CLEARED'),
        ),
      )
      .limit(1);

    if (existing.length === 0) {
      // First observation in this H3 cell
      const initialConfidence = sensorWeight;
      const initialStatus =
        initialConfidence >= 0.8 ? 'CONFIRMED_PATCH' : 'UNVERIFIED_ANOMALY';
      const estimatedMassKg = input.detectedDensityKgKm2 * H3_RES_7_AREA_KM2;

      const [newPatch] = await this.db
        .insert(debrisPatches)
        .values({
          h3Index: input.h3Index,
          latitude: input.latitude,
          longitude: input.longitude,
          estimatedMassKg,
          polymerDensityKgKm2: input.detectedDensityKgKm2,
          confidenceScore: initialConfidence,
          status: initialStatus,
          lastObservedAt: observedAtDate,
        })
        .returning();

      this.logger.log(
        `Created new patch ${newPatch.id} at H3 ${input.h3Index} with status ${initialStatus} (${initialConfidence})`,
      );
      return newPatch;
    }

    const currentPatch = existing[0];
    const newConfidence = this.calculateBayesianUpdate(
      currentPatch.confidenceScore,
      sensorWeight,
    );

    let updatedStatus = currentPatch.status;
    if (currentPatch.status === 'UNVERIFIED_ANOMALY' && newConfidence >= 0.8) {
      updatedStatus = 'CONFIRMED_PATCH';
      this.sseService?.emit({
        stage: 'BAYESIAN_FUSION',
        level: 'SUCCESS',
        message: `Debris patch ${currentPatch.id} promoted to CONFIRMED_PATCH (${(newConfidence * 100).toFixed(1)}% confidence) via ${input.sourceTier}`,
        payload: { patchId: currentPatch.id, h3Index: input.h3Index, confidence: newConfidence },
      });
    }

    // Blend density and update mass
    const updatedDensity =
      (currentPatch.polymerDensityKgKm2 + input.detectedDensityKgKm2) / 2.0;
    const updatedMass = updatedDensity * H3_RES_7_AREA_KM2;

    const [updatedPatch] = await this.db
      .update(debrisPatches)
      .set({
        latitude: input.latitude,
        longitude: input.longitude,
        polymerDensityKgKm2: updatedDensity,
        estimatedMassKg: updatedMass,
        confidenceScore: newConfidence,
        status: updatedStatus,
        lastObservedAt: observedAtDate,
      })
      .where(eq(debrisPatches.id, currentPatch.id))
      .returning();

    this.logger.log(
      `Fused telemetry into patch ${updatedPatch.id}: confidence ${currentPatch.confidenceScore} -> ${newConfidence}, status ${updatedStatus}`,
    );
    return updatedPatch;
  }

  async findAll(status?: string): Promise<DebrisPatch[]> {
    if (status) {
      return this.db
        .select()
        .from(debrisPatches)
        .where(eq(debrisPatches.status, status as any))
        .orderBy(desc(debrisPatches.lastObservedAt));
    }
    return this.db
      .select()
      .from(debrisPatches)
      .orderBy(desc(debrisPatches.lastObservedAt));
  }

  async findById(id: string): Promise<DebrisPatch | null> {
    const res = await this.db
      .select()
      .from(debrisPatches)
      .where(eq(debrisPatches.id, id));
    return res[0] || null;
  }

  async updateStatus(id: string, status: 'UNVERIFIED_ANOMALY' | 'CONFIRMED_PATCH' | 'INTERCEPT_ASSIGNED' | 'CLEARED'): Promise<DebrisPatch> {
    const [updated] = await this.db
      .update(debrisPatches)
      .set({ status })
      .where(eq(debrisPatches.id, id))
      .returning();
    return updated;
  }

  async updateDriftPrediction(
    id: string,
    predictedLat6h: number,
    predictedLon6h: number,
    currentVelocityMs?: number,
    currentDirectionDeg?: number,
  ): Promise<DebrisPatch> {
    const [updated] = await this.db
      .update(debrisPatches)
      .set({
        predictedLat6h,
        predictedLon6h,
        currentVelocityMs: currentVelocityMs ?? 0,
        currentDirectionDeg: currentDirectionDeg ?? 0,
      })
      .where(eq(debrisPatches.id, id))
      .returning();
    return updated;
  }
}

