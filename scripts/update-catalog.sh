#!/usr/bin/env bash
# update-catalog.sh — Update the TrueNAS catalog repo with a new release.
#
# Usage:
#   ./scripts/update-catalog.sh <app_version> <catalog_repo_url>
#
# Example:
#   ./scripts/update-catalog.sh 7.0.0 git@github.com:user/detour-ai-catalog.git
#
# Environment:
#   GITHUB_USER — GitHub username for GHCR image paths (required)
#
# Requires: python3, pyyaml (pip install pyyaml)
# In GitHub Actions: pyyaml is pre-installed on ubuntu-latest runners.

set -euo pipefail

APP_VERSION="${1:?Usage: $0 <app_version> <catalog_repo_url>}"
CATALOG_REPO="${2:?Usage: $0 <app_version> <catalog_repo_url>}"
GITHUB_USER="${GITHUB_USER:?GITHUB_USER env var required}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "==> Cloning catalog repo..."
git clone "$CATALOG_REPO" "$WORK_DIR/catalog"
cd "$WORK_DIR/catalog"

APP_DIR="ix-dev/stable/detour-ai"
TRAINS_DIR="trains/stable/detour-ai"

# ── Bootstrap catalog structure on first run ──
if [ ! -f "$APP_DIR/app.yaml" ]; then
  echo "==> First run detected — bootstrapping catalog structure..."
  mkdir -p "$APP_DIR"
  cat > "$APP_DIR/app.yaml" <<APPYAML
name: detour-ai
train: stable
version: 1.0.0
app_version: "$APP_VERSION"
title: DetourAI
description: KI-gestützter Roadtrip-Planer
home: https://github.com/${GITHUB_USER}/DetourAI
icon_url: https://raw.githubusercontent.com/${GITHUB_USER}/detour-ai-catalog/main/assets/icon.png
APPYAML
  cat > "$APP_DIR/ix_values.yaml" <<IXVALS
images:
  backend:
    repository: ghcr.io/${GITHUB_USER}/detour-ai-backend
    tag: "$APP_VERSION"
  frontend:
    repository: ghcr.io/${GITHUB_USER}/detour-ai-frontend
    tag: "$APP_VERSION"
  redis:
    repository: redis
    tag: "7-alpine"
IXVALS
fi

# ── Read current catalog version and bump minor ──
CURRENT_VERSION=$(python3 -c "import yaml; d=yaml.safe_load(open('$APP_DIR/app.yaml')); print(d['version'])")
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
NEW_CATALOG_VERSION="$MAJOR.$((MINOR + 1)).0"

echo "==> Updating catalog: $CURRENT_VERSION → $NEW_CATALOG_VERSION (app: $APP_VERSION)"

# ── Update ix_values.yaml with new image tags (Python for safe YAML editing) ──
python3 -c "
import yaml, sys

with open('$APP_DIR/ix_values.yaml') as f:
    data = yaml.safe_load(f)

for key, img in data.get('images', {}).items():
    # Only update our own images, not third-party (redis)
    if 'detour-ai' in img.get('repository', ''):
        img['tag'] = '$APP_VERSION'

with open('$APP_DIR/ix_values.yaml', 'w') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
"

# ── Update app.yaml ──
python3 -c "
import yaml

with open('$APP_DIR/app.yaml') as f:
    data = yaml.safe_load(f)

data['app_version'] = '$APP_VERSION'
data['version'] = '$NEW_CATALOG_VERSION'

with open('$APP_DIR/app.yaml', 'w') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
"

# ── Create new version snapshot in trains/ ──
mkdir -p "$TRAINS_DIR/$NEW_CATALOG_VERSION"
cp -r "$APP_DIR/"* "$TRAINS_DIR/$NEW_CATALOG_VERSION/"

# ── Update app_versions.json ──
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")
python3 -c "
import json, sys

versions_file = '$TRAINS_DIR/app_versions.json'
try:
    with open(versions_file) as f:
        versions = json.load(f)
except FileNotFoundError:
    versions = {}

versions['$NEW_CATALOG_VERSION'] = {
    'healthy': True,
    'supported': True,
    'healthy_error': None,
    'location': '/$TRAINS_DIR/$NEW_CATALOG_VERSION',
    'last_update': '$TIMESTAMP',
    'human_version': '${APP_VERSION}_${NEW_CATALOG_VERSION}',
    'version': '$NEW_CATALOG_VERSION'
}

with open(versions_file, 'w') as f:
    json.dump(versions, f, indent=2)
"

# ── Update catalog.json ──
python3 -c "
import json

catalog = {
    'stable': {
        'detour-ai': {
            'name': 'DetourAI',
            'categories': ['productivity'],
            'app_version': '$APP_VERSION',
            'train': 'stable',
            'description': 'KI-gestützter Roadtrip-Planer',
            'home': 'https://github.com/$GITHUB_USER/DetourAI',
            'latest_version': '$NEW_CATALOG_VERSION',
            'latest_app_version': '$APP_VERSION',
            'icon_url': 'https://raw.githubusercontent.com/$GITHUB_USER/detour-ai-catalog/main/assets/icon.png'
        }
    }
}

with open('catalog.json', 'w') as f:
    json.dump(catalog, f, indent=2)
"

# ── Commit and push ──
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -A
git commit -m "release: DetourAI $APP_VERSION (catalog $NEW_CATALOG_VERSION)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push

echo "==> Catalog updated: v$NEW_CATALOG_VERSION (app $APP_VERSION)"
