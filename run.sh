#!/usr/bin/env bash
# ==============================================================================
# Marine IoT Telemetry & Dynamic Trajectory Optimizer - All-in-One Runner
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
BLUE="\033[34m"
RED="\033[31m"
RESET="\033[0m"

function print_banner() {
  echo -e "${CYAN}${BOLD}"
  echo "╔═══════════════════════════════════════════════════════════════════════╗"
  echo "║     🌊 MARINE IoT TELEMETRY & DYNAMIC TRAJECTORY OPTIMIZER 🌊         ║"
  echo "║          Autonomous Fleet Interception & 3D Ocean Twin                ║"
  echo "╚═══════════════════════════════════════════════════════════════════════╝"
  echo -e "${RESET}"
}

function check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not installed or not in PATH.${RESET}"
    exit 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}Error: docker compose plugin is not installed.${RESET}"
    exit 1
  fi
}

function wait_for_api() {
  echo -e "\n${YELLOW}⏳ Waiting for API to become ready...${RESET}"
  local retries=30
  local count=0
  until curl -s -f http://localhost:3000/health >/dev/null 2>&1 || [ $count -ge $retries ]; do
    sleep 2
    count=$((count + 1))
    echo -n "."
  done
  echo ""

  if [ $count -ge $retries ]; then
    echo -e "${RED}⚠️  API took longer than expected to report healthy.${RESET}"
    echo -e "You can inspect container logs using: ${CYAN}docker compose logs api${RESET}"
  else
    echo -e "${GREEN}✓ API is healthy and listening on port 3000!${RESET}"
  fi
}

function seed_database() {
  echo -e "\n${CYAN}🌱 Seeding database with North Pacific Gyre demo state...${RESET}"
  docker compose exec -T api node dist/infrastructure/database/seed.js || {
    echo -e "${YELLOW}Notice: Seeding can also be re-run anytime with: ./run.sh seed${RESET}"
  }
}

function show_services() {
  echo ""
  echo -e "${GREEN}${BOLD}🚀 All Services are Online and Running!${RESET}"
  echo -e "${CYAN}-----------------------------------------------------------------------${RESET}"
  echo -e "  🖥️  ${BOLD}WebGL Command Center UI:${RESET}    ${CYAN}http://localhost:5173${RESET}"
  echo -e "  📘 ${BOLD}Backend REST & Swagger Docs:${RESET} ${CYAN}http://localhost:3000/docs${RESET}"
  echo -e "  📡 ${BOLD}Real-Time Telemetry SSE:${RESET}     ${CYAN}http://localhost:3000/api/v1/telemetry/stream${RESET}"
  echo -e "  🧠 ${BOLD}FastAPI ML & Currents Grid:${RESET}  ${CYAN}http://localhost:8000/docs${RESET}"
  echo -e "  ⚡ ${BOLD}Apache Spark Master Web UI:${RESET}  ${CYAN}http://localhost:8080${RESET}"
  echo -e "  🪣 ${BOLD}MinIO / Silo Object Storage:${RESET} ${CYAN}http://localhost:9001${RESET}  ${YELLOW}(minioadmin / miniopassword)${RESET}"
  echo -e "${CYAN}-----------------------------------------------------------------------${RESET}"
  echo ""
  echo -e "${BOLD}Helpful Commands:${RESET}"
  echo -e "  • Run full mission simulation: ${CYAN}./run.sh sim${RESET}"
  echo -e "  • Re-seed demo database:       ${CYAN}./run.sh seed${RESET}"
  echo -e "  • View live container logs:    ${CYAN}./run.sh logs${RESET}"
  echo -e "  • Stop all containers:         ${CYAN}./run.sh stop${RESET}"
  echo ""
}

function start_all() {
  print_banner
  check_docker
  echo -e "${CYAN}📦 Building and starting all 7 microservices...${RESET}"
  docker compose up -d --build

  wait_for_api
  seed_database
  show_services
}

case "$1" in
  ""|"up"|"start")
    start_all
    ;;
  "seed")
    check_docker
    echo -e "${CYAN}🌱 Populating demo data (vessels, H3 debris patches, routes)...${RESET}"
    docker compose exec api node dist/infrastructure/database/seed.js
    ;;
  "sim"|"simulate")
    echo -e "${CYAN}🚀 Launching End-to-End Ocean Mission Simulation...${RESET}"
    python3 scripts/simulate_ocean_mission.py
    ;;
  "stop"|"down")
    check_docker
    echo -e "${YELLOW}🛑 Stopping all containers...${RESET}"
    docker compose down
    echo -e "${GREEN}✓ All containers stopped.${RESET}"
    ;;
  "restart")
    check_docker
    echo -e "${YELLOW}🔄 Restarting containers...${RESET}"
    docker compose restart
    wait_for_api
    show_services
    ;;
  "status"|"ps")
    check_docker
    docker compose ps
    ;;
  "logs")
    check_docker
    shift || true
    docker compose logs -f "$@"
    ;;
  *)
    echo "Usage: ./run.sh [start|stop|restart|seed|sim|status|logs]"
    echo ""
    echo "  (no args) / start  : Build, launch containers, wait for health, and seed database"
    echo "  seed               : Seed database with vessels, H3 patches & routes"
    echo "  sim                : Run end-to-end Python mission simulator script"
    echo "  stop               : Stop all containers"
    echo "  status             : Show status of all services"
    echo "  logs [service]     : Tail container logs"
    exit 1
    ;;
esac

