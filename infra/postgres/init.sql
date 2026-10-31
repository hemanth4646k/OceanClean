-- Operational store. Columns of vessel_state mirror common/oceanclean_common/telemetry.py.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS vessel_state (
    vessel_id       TEXT PRIMARY KEY,
    event_ts        TIMESTAMPTZ NOT NULL,
    seq             BIGINT NOT NULL,
    geom            geometry(Point, 4326) NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    heading_deg     DOUBLE PRECISION NOT NULL,
    speed_kn        DOUBLE PRECISION NOT NULL,
    battery_pct     DOUBLE PRECISION NOT NULL,
    fuel_l          DOUBLE PRECISION NOT NULL,
    debris_density  DOUBLE PRECISION NOT NULL,
    hold_fill_pct   DOUBLE PRECISION NOT NULL,
    buffered        BOOLEAN NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Provenance of each external dataset (ADR-0002): API or cache fallback, and when it was fetched.
-- Idempotent: re-apply to a running DB with `psql ... < infra/postgres/init.sql`.
CREATE TABLE IF NOT EXISTS data_sources (
    dataset      TEXT PRIMARY KEY,
    source       TEXT NOT NULL CHECK (source IN ('api', 'cache')),
    fetched_at   TIMESTAMPTZ NOT NULL,
    detail       JSONB NOT NULL DEFAULT '{}',
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest survey of each debris patch (topic debris_survey); mass_kg = 0 once collected.
-- Columns mirror common/oceanclean_common/debris.py.
CREATE TABLE IF NOT EXISTS debris_patches (
    patch_id    TEXT PRIMARY KEY,
    survey_ts   TIMESTAMPTZ NOT NULL,
    geom        geometry(Point, 4326) NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    mass_kg     DOUBLE PRECISION NOT NULL,
    radius_m    DOUBLE PRECISION NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Route proposals from the recalc gate and their operator decision (SRS 3.3, 5.4).
-- waypoints: start + one per target (what the vessel steers for; Modify moves these).
-- targets: patch now, predicted intercept (ghost), drift line, energy and score per leg.
CREATE TABLE IF NOT EXISTS routes (
    route_id    BIGSERIAL PRIMARY KEY,
    vessel_id   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'active', 'rejected', 'expired', 'superseded')),
    reason      TEXT NOT NULL,
    planned_at  TIMESTAMPTZ NOT NULL,
    geom        geometry(LineString, 4326) NOT NULL,
    waypoints   JSONB NOT NULL,
    targets     JSONB NOT NULL,
    energy_kwh  DOUBLE PRECISION NOT NULL,
    mass_kg     DOUBLE PRECISION NOT NULL,
    compute_ms  DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at  TIMESTAMPTZ
);
-- planned_at is sim time (the vessel state the plan starts from); created_at is wall time.
CREATE INDEX IF NOT EXISTS routes_by_vessel ON routes (vessel_id, route_id DESC);
-- At most one proposal awaiting the operator and one route being followed, per vessel.
CREATE UNIQUE INDEX IF NOT EXISTS routes_one_pending ON routes (vessel_id) WHERE status = 'pending';
CREATE UNIQUE INDEX IF NOT EXISTS routes_one_active ON routes (vessel_id) WHERE status = 'active';

-- Sim clock control (ADR-0003). The simulator reports its clock (sim_now at wall reported_at)
-- every second and adopts rate/paused, which the API sets for the operator's play/pause/speed.
CREATE TABLE IF NOT EXISTS sim_clock (
    vessel_id    TEXT PRIMARY KEY,
    sim_now      TIMESTAMPTZ NOT NULL,
    rate         DOUBLE PRECISION NOT NULL CHECK (rate > 0),
    paused       BOOLEAN NOT NULL,
    reported_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
