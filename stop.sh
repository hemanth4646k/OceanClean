#!/bin/sh
# Stop and remove every OceanClean container, batch jobs included. Data volumes (PostGIS, lake,
# Kafka, Spark checkpoints, sim state) and data/cache are kept, so ./start.sh resumes the run.
# For a fresh simulation instead, run infra/reset_sim.sh while the stack is up.
set -eu
cd "$(dirname "$0")"
docker compose -f infra/docker-compose.yml --profile batch down
echo "OceanClean stopped; data volumes kept."
