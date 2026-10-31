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
