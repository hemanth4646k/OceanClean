#!/bin/sh
# Clean simulation start: sim clock back to SIM_START at SIM_RATE, unpaused; a freshly seeded
# debris world; empty live state, routes, windows, alerts, faults and metrics; and no telemetry
# history in the lake (a new run numbers ticks from LIVE_SEQ_START + 1 again; a backfill, 1..n).
# Keeps the batch layer's currents, hotspots and their exports (data_sources), Kafka, and the
# telemetry/survey stream checkpoints. Drops the windows query's checkpoint: its watermark is
# in the old run's sim time and would drop every event of the new run as late.
set -eu
cd "$(dirname "$0")/.."
dc() { docker compose -f infra/docker-compose.yml "$@"; }
psql_q() { dc exec -T postgis sh -c 'psql -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' _ "$1"; }

dc stop simulator analytics  # analytics would rebuild silver/gold from the old run
# The stream must finish what the simulator already sent; otherwise those events land after
# the truncate and their newer event times make the UPSERT reject the fresh run.
echo "waiting for the stream to drain..."
until [ "$(psql_q "select coalesce(bool_and(updated_at < now() - interval '15 seconds'), true) from vessel_state")" = t ]; do
  sleep 2
done
dc stop spark-stream
dc rm -f simulator
docker volume rm oceanclean_sim-state
# alerts keeps its sequence: the running API broadcasts rows above the last id it has seen.
psql_q "truncate vessel_state, debris_patches, sim_clock, sim_faults, telemetry_windows, alerts,
  pipeline_metrics, lake_counts; truncate routes restart identity"
dc run --rm --no-deps --entrypoint sh spark-stream -c 'rm -rf "$WINDOW_CHECKPOINT_DIR"'
dc run --rm --no-deps --build -u "$(id -u)" minio-init python infra/minio/delete_prefixes.py \
  bronze/telemetry/ bronze/debris_survey/ silver/telemetry/ gold/telemetry_daily/ \
  gold/telemetry_daily_zone/ gold/exports/analytics.json
dc up -d
echo "reset done; the simulator starts at SIM_START with a new world"
