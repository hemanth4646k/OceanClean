#!/bin/sh
# Clean simulation start: sim clock back to SIM_START, a freshly seeded debris world, empty live
# state and routes, and no speed-layer history in the lake (a new run reuses seq 1, 2, ...).
# Keeps the batch layer (currents, hotspots, exports, data_sources), Kafka and stream checkpoints.
set -eu
cd "$(dirname "$0")/.."
dc() { docker compose -f infra/docker-compose.yml "$@"; }
psql_q() { dc exec -T postgis sh -c 'psql -qtA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' _ "$1"; }

dc stop simulator
# The stream must finish what the simulator already sent; otherwise those events land after
# the truncate and their newer event times make the UPSERT reject the fresh run.
echo "waiting for the stream to drain..."
until [ "$(psql_q "select coalesce(bool_and(updated_at < now() - interval '15 seconds'), true) from vessel_state")" = t ]; do
  sleep 2
done
dc stop spark-stream
dc rm -f simulator
docker volume rm oceanclean_sim-state
psql_q "truncate vessel_state, debris_patches; truncate routes restart identity"
dc run --rm --no-deps --build -u "$(id -u)" minio-init python infra/minio/delete_prefixes.py \
  bronze/telemetry/ bronze/debris_survey/
dc up -d
echo "reset done; the simulator starts at SIM_START with a new world"
