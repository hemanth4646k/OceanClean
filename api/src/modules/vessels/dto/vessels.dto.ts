import { z } from 'zod';

export const CreateVesselSchema = z.object({
  name: z.string().min(1),
  callsign: z.string().min(1),
  operatorId: z.string().uuid().optional(),
  status: z.enum(['IDLE', 'EN_ROUTE', 'HARVESTING', 'MAINTENANCE']).optional().default('IDLE'),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  maxCapacityTons: z.number().positive(),
  currentLoadTons: z.number().nonnegative().optional().default(0),
  fuelLevelPct: z.number().min(0).max(100).optional().default(100),
  cruiseSpeedKnots: z.number().positive().optional().default(12),
});

export type CreateVesselDto = z.infer<typeof CreateVesselSchema>;

export const UpdateVesselTelemetrySchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  status: z.enum(['IDLE', 'EN_ROUTE', 'HARVESTING', 'MAINTENANCE']).optional(),
  currentLoadTons: z.number().nonnegative().optional(),
  fuelLevelPct: z.number().min(0).max(100).optional(),
  cruiseSpeedKnots: z.number().positive().optional(),
});

export type UpdateVesselTelemetryDto = z.infer<typeof UpdateVesselTelemetrySchema>;

