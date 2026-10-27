import {
  pgTable,
  uuid,
  varchar,
  timestamp,
  doublePrecision,
  real,
  jsonb,
  index,
} from 'drizzle-orm/pg-core';

export const users = pgTable('users', {
  id: uuid('id').defaultRandom().primaryKey(),
  email: varchar('email', { length: 255 }).notNull().unique(),
  passwordHash: varchar('password_hash', { length: 255 }).notNull(),
  role: varchar('role', { length: 50 })
    .$type<'FLEET_ADMIN' | 'VESSEL_CAPTAIN'>()
    .notNull(),
  createdAt: timestamp('created_at', { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const vessels = pgTable('vessels', {
  id: uuid('id').defaultRandom().primaryKey(),
  name: varchar('name', { length: 255 }).notNull(),
  callsign: varchar('callsign', { length: 100 }).notNull().unique(),
  operatorId: uuid('operator_id').references(() => users.id),
  status: varchar('status', { length: 50 })
    .$type<'IDLE' | 'EN_ROUTE' | 'HARVESTING' | 'MAINTENANCE'>()
    .default('IDLE')
    .notNull(),
  latitude: doublePrecision('latitude').notNull(),
  longitude: doublePrecision('longitude').notNull(),
  h3Index: varchar('h3_index', { length: 20 }).notNull(),
  maxCapacityTons: doublePrecision('max_capacity_tons').notNull(),
  currentLoadTons: doublePrecision('current_load_tons').default(0).notNull(),
  fuelLevelPct: doublePrecision('fuel_level_pct').default(100.0).notNull(),
  cruiseSpeedKnots: doublePrecision('cruise_speed_knots').default(12.0).notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const debrisPatches = pgTable(
  'debris_patches',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    h3Index: varchar('h3_index', { length: 20 }).notNull(),
    latitude: doublePrecision('latitude').notNull(),
    longitude: doublePrecision('longitude').notNull(),
    estimatedMassKg: doublePrecision('estimated_mass_kg').notNull(),
    polymerDensityKgKm2: doublePrecision('polymer_density_kg_km2').notNull(),
    confidenceScore: real('confidence_score').default(0.5).notNull(),
    status: varchar('status', { length: 50 })
      .$type<'UNVERIFIED_ANOMALY' | 'CONFIRMED_PATCH' | 'INTERCEPT_ASSIGNED' | 'CLEARED'>()
      .default('UNVERIFIED_ANOMALY')
      .notNull(),
    currentVelocityMs: doublePrecision('current_velocity_ms').default(0),
    currentDirectionDeg: doublePrecision('current_direction_deg').default(0),
    predictedLat6h: doublePrecision('predicted_lat_6h'),
    predictedLon6h: doublePrecision('predicted_lon_6h'),
    lastObservedAt: timestamp('last_observed_at', { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (table) => [index('idx_debris_h3').on(table.h3Index)],
);

export const telemetryEvents = pgTable(
  'telemetry_events',
  {
    id: uuid('id').defaultRandom().primaryKey(),
    sourceTier: varchar('source_tier', { length: 50 })
      .$type<'SATELLITE_SAR' | 'AERIAL_UAV' | 'VESSEL_OPTICAL' | 'DRIFT_BUOY'>()
      .notNull(),
    sensorDeviceId: varchar('sensor_device_id', { length: 255 }).notNull(),
    h3Index: varchar('h3_index', { length: 20 }).notNull(),
    latitude: doublePrecision('latitude').notNull(),
    longitude: doublePrecision('longitude').notNull(),
    detectedDensityKgKm2: doublePrecision('detected_density_kg_km2').notNull(),
    rawConfidence: real('raw_confidence').notNull(),
    seaStateWaveM: doublePrecision('sea_state_wave_m').default(1.0).notNull(),
    observedAt: timestamp('observed_at', { withTimezone: true })
      .defaultNow()
      .notNull(),
  },
  (table) => [index('idx_telemetry_h3').on(table.h3Index)],
);

export const interceptionRoutes = pgTable('interception_routes', {
  id: uuid('id').defaultRandom().primaryKey(),
  vesselId: uuid('vessel_id')
    .references(() => vessels.id)
    .notNull(),
  status: varchar('status', { length: 50 })
    .$type<'PLANNED' | 'ACTIVE' | 'COMPLETED' | 'ABORTED'>()
    .default('PLANNED')
    .notNull(),
  totalDistanceNm: doublePrecision('total_distance_nm').notNull(),
  estimatedFuelLiters: doublePrecision('estimated_fuel_liters').notNull(),
  expectedYieldKg: doublePrecision('expected_yield_kg').notNull(),
  waypointsJson: jsonb('waypoints_json').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;
export type Vessel = typeof vessels.$inferSelect;
export type NewVessel = typeof vessels.$inferInsert;
export type DebrisPatch = typeof debrisPatches.$inferSelect;
export type NewDebrisPatch = typeof debrisPatches.$inferInsert;
export type TelemetryEvent = typeof telemetryEvents.$inferSelect;
export type NewTelemetryEvent = typeof telemetryEvents.$inferInsert;
export type InterceptionRoute = typeof interceptionRoutes.$inferSelect;
export type NewInterceptionRoute = typeof interceptionRoutes.$inferInsert;

