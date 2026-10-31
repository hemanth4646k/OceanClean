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

-- M5: who decided a route (operator | autopilot | timeout; ADR-0008), the clock hold while a
-- proposal awaits the operator, and injected faults for the anomaly demo.
ALTER TABLE routes ADD COLUMN IF NOT EXISTS decided_by TEXT
    CHECK (decided_by IN ('operator', 'autopilot', 'timeout'));
-- The simulator runs only when NOT (paused OR hitl_hold): the operator's pause is separate.
ALTER TABLE sim_clock ADD COLUMN IF NOT EXISTS hitl_hold BOOLEAN NOT NULL DEFAULT false;
-- Sim time until which the vessel leaks fuel (1.5x burn): POST /sim/fault.
CREATE TABLE IF NOT EXISTS sim_faults (
    vessel_id        TEXT PRIMARY KEY,
    fuel_leak_until  TIMESTAMPTZ NOT NULL
);

-- 5-minute event-time windows from the watermarked query (ADR-0005), scored by
-- streaming/anomaly.py: energy and debris since the previous window, and the fuel-burn z-score.
CREATE TABLE IF NOT EXISTS telemetry_windows (
    vessel_id      TEXT NOT NULL,
    window_end     TIMESTAMPTZ NOT NULL,
    last_ts        TIMESTAMPTZ NOT NULL,
    n              INTEGER NOT NULL,
    fuel_l         DOUBLE PRECISION NOT NULL,
    battery_pct    DOUBLE PRECISION NOT NULL,
    hold_fill_pct  DOUBLE PRECISION NOT NULL,
    energy_kwh     DOUBLE PRECISION NOT NULL,
    expected_kwh   DOUBLE PRECISION NOT NULL,
    collected_kg   DOUBLE PRECISION NOT NULL,
    residual       DOUBLE PRECISION,
    z              DOUBLE PRECISION,
    anomaly        BOOLEAN NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (vessel_id, window_end)
);

-- Alerts for the operator (WebSocket toasts); ts is sim time. Unique so a replayed batch
-- does not alert twice.
CREATE TABLE IF NOT EXISTS alerts (
    alert_id    BIGSERIAL PRIMARY KEY,
    vessel_id   TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    kind        TEXT NOT NULL,
    level       TEXT NOT NULL CHECK (level IN ('info', 'success', 'warn')),
    text        TEXT NOT NULL,
    detail      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (vessel_id, kind, ts)
);

-- Spark StreamingQueryListener progress, one row per micro-batch per query (wall time).
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    ts             TIMESTAMPTZ NOT NULL,
    query          TEXT NOT NULL,
    batch_id       BIGINT NOT NULL,
    input_rows     BIGINT NOT NULL,
    input_rps      DOUBLE PRECISION,
    processed_rps  DOUBLE PRECISION,
    duration_ms    DOUBLE PRECISION,
    kafka_lag      BIGINT
);
CREATE INDEX IF NOT EXISTS pipeline_metrics_by_ts ON pipeline_metrics (ts DESC);

-- Rows written to each lake dataset: bronze counted by the stream as it appends (a retried
-- batch counts twice), silver/gold set by the telemetry batch job.
CREATE TABLE IF NOT EXISTS lake_counts (
    dataset     TEXT PRIMARY KEY,
    rows        BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
