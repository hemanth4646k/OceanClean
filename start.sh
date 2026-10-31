#!/bin/sh
# Start the whole OceanClean stack, then print where to open it.
# On a fresh lake (no batch exports yet) it first fetches the NOAA data (network, else
# data/cache) and runs the Spark batch ETL; the simulator and stream wait for those exports.
# Data volumes persist across ./stop.sh, so later starts skip the batch step.
set -eu
cd "$(dirname "$0")"
dc() { docker compose -f infra/docker-compose.yml "$@"; }

command -v docker >/dev/null || { echo "docker is not installed or not on PATH" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "the Docker daemon is not running" >&2; exit 1; }

mkdir -p data/cache  # before any fetch, or Docker creates it root-owned

echo "==> building images"
dc --profile batch build

echo "==> starting MinIO and creating the lake bucket"
dc up -d minio
dc run --rm minio-init

if ! dc run --rm --no-deps minio-init python infra/minio/has_objects.py \
    gold/exports/mission_currents.npz gold/exports/hotspots.json; then
  echo "==> first run: fetching NOAA data (about 25 min with network; uses data/cache without)"
  dc --profile batch run --rm -u "$(id -u):$(id -g)" fetch
  echo "==> first run: Spark batch ETL (currents grid, hotspots, exports)"
  dc --profile batch run --rm spark-batch
fi

echo "==> starting the stack"
dc up -d

printf "==> waiting for the API"
i=0
until curl -fs localhost:8002/health >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 90 ]; then
    echo; echo "the API did not come up in 3 min; see: docker compose -f infra/docker-compose.yml logs api" >&2
    exit 1
  fi
  printf "."
  sleep 2
done
echo

cat <<'EOF'
OceanClean is up.
  Live map and dashboards: http://localhost:8080
  API:                     http://localhost:8002
  MinIO console:           http://localhost:9001
  Spark UI (stream):       http://localhost:4040
The sim clock keeps its last state (it may be paused): press play in the map's clock bar.
Stop everything with ./stop.sh
EOF
