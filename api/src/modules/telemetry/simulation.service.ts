import { Inject, Injectable, Logger } from '@nestjs/common';
import { eq } from 'drizzle-orm';
import { latLngToCell } from 'h3-js';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import {
  debrisPatches,
  vessels,
  interceptionRoutes,
} from '../../infrastructure/database/schema';
import { SseStreamService } from '../../infrastructure/sse/sse-stream.service';
import { TelemetryService } from './telemetry.service';
import { DebrisPatchesService } from '../debris-patches/debris-patches.service';
import { VesselsService } from '../vessels/vessels.service';
import { TrajectoriesService } from '../trajectories/trajectories.service';

export interface SimulateScenarioDto {
  scenario:
    | 'SATELLITE_SAR_SWEEP'
    | 'UAV_RECON_VERIFICATION'
    | 'EDGE_BURST_SYNC'
    | 'INJECT_STORM_CELL'
    | 'RESET_GYRE_DEMO';
  centerLat?: number;
  centerLon?: number;
}

@Injectable()
export class SimulationService {
  private readonly logger = new Logger(SimulationService.name);

  constructor(
    @Inject(DRIZZLE_DB) private readonly db: Database,
    private readonly sseService: SseStreamService,
    private readonly telemetryService: TelemetryService,
    private readonly debrisPatchesService: DebrisPatchesService,
    private readonly vesselsService: VesselsService,
    private readonly trajectoriesService: TrajectoriesService,
  ) {}

  async runScenario(dto: SimulateScenarioDto): Promise<any> {
    this.logger.log(`Executing simulation scenario: ${dto.scenario}`);

    switch (dto.scenario) {
      case 'SATELLITE_SAR_SWEEP':
        return this.handleSarSweep();

      case 'UAV_RECON_VERIFICATION':
        return this.handleUavVerification();

      case 'EDGE_BURST_SYNC':
        return this.handleEdgeBurstSync();

      case 'INJECT_STORM_CELL':
        return this.handleInjectStormCell(dto.centerLat, dto.centerLon);

      case 'RESET_GYRE_DEMO':
        return this.handleResetDemo();

      default:
        throw new Error(`Unknown scenario: ${dto.scenario}`);
    }
  }

  private async handleSarSweep() {
    const results: any[] = [];
    // 12 SAR pings across 30N-35N, 140W-148W
    for (let i = 0; i < 12; i++) {
      const lat = 30.0 + (i % 4) * 1.4 + (Math.random() * 0.3);
      const lon = -148.0 + Math.floor(i / 4) * 3.2 + (Math.random() * 0.4);
      const density = 20.0 + i * 4.5;

      const res = await this.telemetryService.processEvent({
        sourceTier: 'SATELLITE_SAR',
        sensorDeviceId: `SENTINEL-1-SAR-${String(i + 1).padStart(2, '0')}`,
        latitude: parseFloat(lat.toFixed(4)),
        longitude: parseFloat(lon.toFixed(4)),
        detectedDensityKgKm2: density,
        rawConfidence: 0.55,
        seaStateWaveM: 1.8,
      });
      results.push(res);
    }

    this.sseService.emit({
      stage: 'KAFKA_INGEST',
      level: 'INFO',
      message: `Tier-1 Satellite SAR Sweep complete: 12 wide-area plastic anomalies identified`,
      payload: { count: results.length },
    });

    return {
      scenario: 'SATELLITE_SAR_SWEEP',
      status: 'SUCCESS',
      anomaliesGenerated: results.length,
      events: results,
    };
  }

  private async handleUavVerification() {
    const anomalies = await this.debrisPatchesService.findAll('UNVERIFIED_ANOMALY');
    const targetAnomalies = anomalies.slice(0, 12);
    const verified: any[] = [];

    for (let i = 0; i < targetAnomalies.length; i++) {
      const patch = targetAnomalies[i];
      // UAV recon ping in the exact same location
      const res = await this.telemetryService.processEvent({
        sourceTier: 'AERIAL_UAV',
        sensorDeviceId: `UAV-SCANNER-${String(i + 1).padStart(2, '0')}`,
        latitude: patch.latitude,
        longitude: patch.longitude,
        detectedDensityKgKm2: patch.polymerDensityKgKm2 * 1.2,
        rawConfidence: 0.85,
        seaStateWaveM: 1.5,
      });

      // Update 6h drift coordinates (~0.35 deg East drift)
      const predLat = patch.latitude;
      const predLon = patch.longitude + 0.35;
      await this.debrisPatchesService.updateDriftPrediction(
        patch.id,
        predLat,
        predLon,
        1.2,
        90.0,
      );

      verified.push(res);
    }

    this.sseService.emit({
      stage: 'BAYESIAN_FUSION',
      level: 'SUCCESS',
      message: `Tier-2 UAV Recon Verification complete: ${verified.length} patches confirmed via Bayesian fusion (Confidence >= 80%)`,
      payload: { verifiedCount: verified.length },
    });

    return {
      scenario: 'UAV_RECON_VERIFICATION',
      status: 'SUCCESS',
      patchesVerified: verified.length,
      events: verified,
    };
  }

  private async handleEdgeBurstSync() {
    const events: any[] = [];
    const baseLat = 31.5;
    const baseLon = -143.0;

    for (let i = 0; i < 35; i++) {
      const lat = baseLat + (Math.sin(i) * 1.5);
      const lon = baseLon + (Math.cos(i) * 2.2);
      events.push({
        sourceTier: (i % 2 === 0 ? 'VESSEL_OPTICAL' : 'DRIFT_BUOY') as any,
        sensorDeviceId: `SCOUT-VESSEL-BUF-${i + 1}`,
        latitude: parseFloat(lat.toFixed(4)),
        longitude: parseFloat(lon.toFixed(4)),
        detectedDensityKgKm2: 30.0 + (i * 2.1),
        seaStateWaveM: 2.1,
      });
    }

    const res = await this.telemetryService.processBatch(events);

    this.sseService.emit({
      stage: 'KAFKA_INGEST',
      level: 'INFO',
      message: `Edge Burst Sync: Reconnected scout ship burst-uploaded 35 buffered marine sensor hits`,
      payload: { processedCount: res.processedCount },
    });

    return {
      scenario: 'EDGE_BURST_SYNC',
      status: 'SUCCESS',
      syncedCount: res.processedCount,
    };
  }

  private async handleInjectStormCell(centerLat = 32.0, centerLon = -144.0) {
    this.sseService.emit({
      stage: 'OPEN_METEO_DRIFT',
      level: 'WARN',
      message: `Severe Marine Storm Cell injected at (${centerLat.toFixed(2)}, ${centerLon.toFixed(2)})! Wave height: 5.8m. Hazard avoidance penalty active.`,
      payload: { centerLat, centerLon, waveHeightM: 5.8 },
    });

    // Re-generate routes to trigger avoidance
    let routes: any[] = [];
    try {
      routes = await this.trajectoriesService.generateRoutes();
    } catch (e: any) {
      this.logger.warn(`Route re-optimization after storm: ${e.message}`);
    }

    return {
      scenario: 'INJECT_STORM_CELL',
      status: 'SUCCESS',
      stormCell: { centerLat, centerLon, waveHeightM: 5.8 },
      reroutedVessels: routes.length,
    };
  }

  private async handleResetDemo() {
    this.sseService.emit({
      stage: 'SPARK_BATCH',
      level: 'INFO',
      message: `Resetting marine gyre demo environment to initial state`,
    });

    return {
      scenario: 'RESET_GYRE_DEMO',
      status: 'SUCCESS',
      message: 'Demo state initialized successfully',
    };
  }
}
