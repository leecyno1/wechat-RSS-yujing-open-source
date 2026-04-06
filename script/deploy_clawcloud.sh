#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_DIR="$ROOT_DIR/compose"
ENV_FILE="$COMPOSE_DIR/.env.clawcloud"
EXAMPLE_FILE="$COMPOSE_DIR/.env.clawcloud.example"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose-clawcloud.yaml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose not available"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$EXAMPLE_FILE" ]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    echo "created $ENV_FILE from example, edit it first then rerun"
    exit 2
  fi
  echo "missing $ENV_FILE"
  exit 2
fi

echo "[1/3] pull runtime images"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull we-mp-rss rsshub rsshub-browserless

echo "[2/3] start app"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d we-mp-rss rsshub rsshub-browserless

echo "[3/3] status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
echo "done. open: http://<your-domain-or-ip>:${WERS_PORT:-8001}"
