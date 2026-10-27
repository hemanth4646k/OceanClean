CREATE TABLE IF NOT EXISTS "debris_patches" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"h3_index" varchar(20) NOT NULL,
	"latitude" double precision NOT NULL,
	"longitude" double precision NOT NULL,
	"estimated_mass_kg" double precision NOT NULL,
	"polymer_density_kg_km2" double precision NOT NULL,
	"confidence_score" real DEFAULT 0.5 NOT NULL,
	"status" varchar(50) DEFAULT 'UNVERIFIED_ANOMALY' NOT NULL,
	"current_velocity_ms" double precision DEFAULT 0,
	"current_direction_deg" double precision DEFAULT 0,
	"predicted_lat_6h" double precision,
	"predicted_lon_6h" double precision,
	"last_observed_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "interception_routes" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"vessel_id" uuid NOT NULL,
	"status" varchar(50) DEFAULT 'PLANNED' NOT NULL,
	"total_distance_nm" double precision NOT NULL,
	"estimated_fuel_liters" double precision NOT NULL,
	"expected_yield_kg" double precision NOT NULL,
	"waypoints_json" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "telemetry_events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"source_tier" varchar(50) NOT NULL,
	"sensor_device_id" varchar(255) NOT NULL,
	"h3_index" varchar(20) NOT NULL,
	"latitude" double precision NOT NULL,
	"longitude" double precision NOT NULL,
	"detected_density_kg_km2" double precision NOT NULL,
	"raw_confidence" real NOT NULL,
	"sea_state_wave_m" double precision DEFAULT 1 NOT NULL,
	"observed_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "users" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" varchar(255) NOT NULL,
	"password_hash" varchar(255) NOT NULL,
	"role" varchar(50) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "vessels" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(255) NOT NULL,
	"callsign" varchar(100) NOT NULL,
	"operator_id" uuid,
	"status" varchar(50) DEFAULT 'IDLE' NOT NULL,
	"latitude" double precision NOT NULL,
	"longitude" double precision NOT NULL,
	"h3_index" varchar(20) NOT NULL,
	"max_capacity_tons" double precision NOT NULL,
	"current_load_tons" double precision DEFAULT 0 NOT NULL,
	"fuel_level_pct" double precision DEFAULT 100 NOT NULL,
	"cruise_speed_knots" double precision DEFAULT 12 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "vessels_callsign_unique" UNIQUE("callsign")
);
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "interception_routes" ADD CONSTRAINT "interception_routes_vessel_id_vessels_id_fk" FOREIGN KEY ("vessel_id") REFERENCES "public"."vessels"("id") ON DELETE no action ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "vessels" ADD CONSTRAINT "vessels_operator_id_users_id_fk" FOREIGN KEY ("operator_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_debris_h3" ON "debris_patches" USING btree ("h3_index");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_telemetry_h3" ON "telemetry_events" USING btree ("h3_index");