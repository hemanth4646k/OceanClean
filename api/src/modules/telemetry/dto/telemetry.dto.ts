import { z } from 'zod';

export const TelemetryIngestSchema = z.object({
  sourceTier: z.enum(['SATELLITE_SAR', 'AERIAL_UAV', 'VESSEL_OPTICAL', 'DRIFT_BUOY']),
  sensorDeviceId: z.string().min(1),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  detectedDensityKgKm2: z.number().nonnegative(),
  rawConfidence: z.number().min(0).max(1).optional(),
  seaStateWaveM: z.number().nonnegative().optional(),
  observedAt: z.string().datetime().optional(),
});

export type TelemetryIngestDto = z.infer<typeof TelemetryIngestSchema>;

export const TelemetryBatchSyncSchema = z.object({
  events: z.array(TelemetryIngestSchema).min(1),
});

export type TelemetryBatchSyncDto = z.infer<typeof TelemetryBatchSyncSchema>;
