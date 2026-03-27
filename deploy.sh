#!/usr/bin/env bash
# deploy.sh — Build and run DetourAI locally with Docker Compose.
#
# Usage:
#   ./deploy.sh            # build images and start all services
#   ./deploy.sh --down     # stop and remove containers
#
# Required env vars:
#   ANTHROPIC_API_KEY

set -euo pipefail

if [[ "${1:-}" == "--down" ]]; then
  docker compose down
  exit 0
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  exit 1
fi

ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
TEST_MODE="${TEST_MODE:-true}" \
  docker compose up --build
