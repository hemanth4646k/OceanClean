import { Inject, Injectable, Logger, Optional } from '@nestjs/common';
import { latLngToCell } from 'h3-js';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import { telemetryEvents } from '../../infrastructure/database/schema';
import { KafkaService } from '../../infrastructure/kafka/kafka.service';
import { DebrisPatchesService } from '../debris-patches/debris-patches.service';
import { SseStreamService } from '../../infrastructure/sse/sse-stream.service';
import { TelemetryIngestDto } from './dto/telemetry.dto';

const SENSOR_DEFAULT_WEIGHTS: Record<string, number> = {
  SATELLITE_SAR: 0.55,
  AERIAL_UAV: 0.85,
  VESSEL_OPTICAL: 0.95,
  DRIFT_BUOY: 0.95,
};

@Injectable()
export class TelemetryService {
  private readonly logger = new Logger(TelemetryService.name);

  constructor(
    @Inject(DRIZZLE_DB) private readonly db: Database,
    private readonly kafkaService: KafkaService,
    private readonly debrisPatchesService: DebrisPatchesService,
    @Optional() private readonly sseService?: SseStreamService,
  ) {}

  async processEvent(dto: TelemetryIngestDto) {
    const h3Index = latLngToCell(dto.latitude, dto.longitude, 7);
    const rawConfidence =
      dto.rawConfidence !== undefined
        ? dto.rawConfidence
        : SENSOR_DEFAULT_WEIGHTS[dto.sourceTier] || 0.55;
    const observedAt = dto.observedAt ? new Date(dto.observedAt) : new Date();

    // 1. Persist raw telemetry event
    const [savedEvent] = await this.db
      .insert(telemetryEvents)
      .values({
        sourceTier: dto.sourceTier,
        sensorDeviceId: dto.sensorDeviceId,
        h3Index,
        latitude: dto.latitude,
        longitude: dto.longitude,
        detectedDensityKgKm2: dto.detectedDensityKgKm2,
        rawConfidence,
        seaStateWaveM: dto.seaStateWaveM ?? 1.0,
        observedAt,
      })
      .returning();

    // 2. Perform Bayesian Confidence Fusion into active debris patches
    const patch = await this.debrisPatchesService.fuseTelemetry({
      sourceTier: dto.sourceTier,
      h3Index,
      latitude: dto.latitude,
      longitude: dto.longitude,
      detectedDensityKgKm2: dto.detectedDensityKgKm2,
      rawConfidence,
      seaStateWaveM: dto.seaStateWaveM ?? 1.0,
      observedAt,
    });

    // 3. Publish to Kafka asynchronously
    const kafkaPayload = {
      eventId: savedEvent.id,
      sourceTier: dto.sourceTier,
      sensorDeviceId: dto.sensorDeviceId,
      h3Index,
      latitude: dto.latitude,
      longitude: dto.longitude,
      detectedDensityKgKm2: dto.detectedDensityKgKm2,
      rawConfidence,
      seaStateWaveM: dto.seaStateWaveM ?? 1.0,
      observedAt: observedAt.toISOString(),
      associatedPatchId: patch.id,
      patchConfidence: patch.confidenceScore,
      patchStatus: patch.status,
    };

    const topic = process.env.KAFKA_TOPIC_TELEMETRY_RAW || 'marine.telemetry.raw';
    // Async fire-and-forget to Kafka without blocking response
    this.kafkaService
      .sendTelemetryEvent(topic, h3Index, kafkaPayload)
      .catch((err) => {
        this.logger.error(`Error sending message to Kafka: ${err.message}`);
      });

    this.sseService?.emit({
      stage: 'KAFKA_INGEST',
      level: 'INFO',
      message: `Ingested ${dto.sourceTier} telemetry [${dto.sensorDeviceId}] at H3 ${h3Index}`,
      payload: { eventId: savedEvent.id, h3Index, sourceTier: dto.sourceTier },
    });

    return {
      eventId: savedEvent.id,
      h3Index,
      patch: {
        id: patch.id,
        status: patch.status,
        confidenceScore: patch.confidenceScore,
        polymerDensityKgKm2: patch.polymerDensityKgKm2,
        estimatedMassKg: patch.estimatedMassKg,
      },
    };
  }

  async processBatch(events: TelemetryIngestDto[]) {
    const results: any[] = [];
    for (const event of events) {
      const res = await this.processEvent(event);
      results.push(res);
    }
    return {
      processedCount: results.length,
      events: results,
    };
  }
}
