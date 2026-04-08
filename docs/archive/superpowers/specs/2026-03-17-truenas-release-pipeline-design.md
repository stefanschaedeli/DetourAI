# TrueNAS Release Pipeline & Auto-Deploy Design

**Date:** 2026-03-17
**Status:** Approved

---

## Overview

Automated release pipeline that builds Docker images, pushes them to GitHub Container Registry (GHCR), and updates a TrueNAS custom app catalog — enabling one-click install and update on TrueNAS 25.04 (Fangtooth).

## Goals

- Push a release tag → TrueNAS sees an app update automatically
- TrueNAS discovers DetourAI in the "Discover" screen as a native app
- Native config UI for API keys, ports, and storage
- No changes to existing development workflow (patch tags continue as-is)
- Existing source code remains untouched (minor Dockerfile change for UID alignment)

## Non-Goals

- Publishing to the official TrueNAS catalog (iXsystems does not support third-party catalogs)
- Multi-arch builds (TrueNAS runs x86_64 only for this deployment)
- Public access — both repos and images remain private

---

## Architecture

### Repository Topology

**Two GitHub repositories:**

1. **`DetourAI`** (existing, private) — Source code + GitHub Actions pipeline. Builds Docker images and updates the catalog repo on release.

2. **`detour-ai-catalog`** (new, private) — TrueNAS custom app catalog. Contains only catalog metadata, compose templates, and version snapshots. TrueNAS points to this repo.

**Why two repos?** TrueNAS clones the entire catalog repository. Keeping it separate prevents TrueNAS from pulling source code, logs, and outputs.

### Image Registry

Images are hosted on GitHub Container Registry (GHCR):
- `ghcr.io/<user>/detour-ai-backend:<version>` — Backend + Celery worker (same image, different entrypoint)
- `ghcr.io/<user>/detour-ai-frontend:<version>` — Nginx + static frontend

Only 2 images are built. The Celery worker reuses the backend image with a different command.

### Version Scheme

| Context | Format | Example | Purpose |
|---------|--------|---------|---------|
| Dev patches | `vX.X.Y` | `v6.1.74` | Every commit, no pipeline triggered |
| Release tags | `release/vX.Y.Z` | `release/v7.0.0` | Triggers the full build+deploy pipeline |
| Catalog version | `X.Y.Z` | `1.1.0` | Auto-incremented minor per release, shown in TrueNAS |
| App version | `X.Y.Z` | `7.0.0` | Extracted from release tag, shown as upstream version |

---

## Pipeline Design

### Trigger

Push of a Git tag matching `release/v*` on the DetourAI repository.

### Pipeline Steps (GitHub Actions)

```
release/v7.0.0 tag pushed
         │
         ▼
┌─────────────────────────┐
│  1. Validate & Test      │  pytest tests/ -v
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  2. Build Images         │  docker buildx build (amd64)
│                          │  → detour-ai-backend
│                          │  → detour-ai-frontend
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  3. Push to GHCR         │  ghcr.io/<user>/detour-ai-backend:7.0.0
│                          │  ghcr.io/<user>/detour-ai-frontend:7.0.0
│                          │  + :latest tags
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  4. Update Catalog Repo  │  Clone detour-ai-catalog
│                          │  Update ix_values.yaml (new image tags)
│                          │  Update app.yaml (bump version + app_version)
│                          │  Create new version dir in trains/
│                          │  Regenerate catalog.json + app_versions.json
│                          │  Commit + push to catalog repo
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  5. GitHub Release       │  Create release on DetourAI
│                          │  with auto-generated changelog
└─────────────────────────┘
```

### Workflow File

**Location:** `.github/workflows/release.yml` in DetourAI

**Key implementation details:**
- Uses `docker/build-push-action` for multi-stage builds
- GHCR login via built-in `GITHUB_TOKEN`
- Catalog repo access via `CATALOG_DEPLOY_KEY` secret (SSH deploy key)
- Catalog update logic lives in `scripts/update-catalog.sh` (reusable for manual runs)
- Auto-increments catalog version by reading current `app.yaml` and bumping minor

### GitHub Secrets Required

| Secret | Purpose |
|--------|---------|
| `CATALOG_DEPLOY_KEY` | SSH deploy key with write access to `detour-ai-catalog` repo (script clones via SSH URL `git@github.com:<user>/detour-ai-catalog.git`) |
| *(built-in)* `GITHUB_TOKEN` | GHCR push access (automatic) |

**TrueNAS pull PAT:** The PAT configured on TrueNAS for GHCR needs `read:packages` scope.

---

## TrueNAS Catalog Structure

### Repository Layout (`detour-ai-catalog`)

```
detour-ai-catalog/
├── catalog.json                         # Auto-generated catalog index
├── features_capability.json             # TrueNAS version feature gates
├── ix-dev/
│   └── stable/
│       └── detour-ai/
│           ├── app.yaml                 # App metadata
│           ├── ix_values.yaml           # Image repos + tags
│           ├── questions.yaml           # TrueNAS UI config form
│           ├── README.md                # Short description
│           ├── item.yaml                # Categories, icon, tags
│           └── templates/
│               ├── docker-compose.yaml  # Jinja2 compose template
│               ├── library/             # ix_lib (copied from official repo)
│               └── test_values/
│                   └── basic-values.yaml
└── trains/
    └── stable/
        └── detour-ai/
            ├── item.yaml
            ├── app_versions.json        # Index of all published versions
            └── <version>/               # Snapshot per release
                └── ...                  # Full copy of ix-dev files
```

### app.yaml

**UID/GID alignment:** TrueNAS convention uses UID/GID 568 for the `apps` user. The existing `Dockerfile.backend` creates a system user with an unspecified UID — this must be changed to use UID/GID 568 so that TrueNAS-managed storage permissions work correctly. The frontend image (`nginxinc/nginx-unprivileged`) runs as UID 101 internally; this is fine since it only serves static files and does not access shared storage.

```yaml
annotations:
  min_scale_version: 24.10.2.2
app_version: "7.0.0"
capabilities: []
categories:
  - productivity
date_added: "2026-03-17"
description: "KI-gestützter Roadtrip-Planer mit interaktiver Routenplanung, Unterkünften, Aktivitäten und Tagesführer."
home: https://github.com/<user>/DetourAI
icon: https://raw.githubusercontent.com/<user>/detour-ai-catalog/main/assets/icon.png
keywords:
  - travel
  - planner
  - ai
lib_version: 2.2.2
maintainers:
  - name: stefan
    email: ""
name: detour-ai
run_as_context:
  - description: Backend and Celery containers run as apps user
    gid: 568
    group_name: Host group is [apps]
    uid: 568
    user_name: Host user is [apps]
  - description: Frontend (nginx) runs as built-in non-root user
    gid: 101
    uid: 101
  - description: Redis runs as built-in redis user
    gid: 999
    uid: 999
title: DetourAI
train: stable
version: "1.0.0"
```

### questions.yaml Config Groups

| Group | Variables |
|-------|-----------|
| **DetourAI Configuration** | `ANTHROPIC_API_KEY` (string, required, private), `GOOGLE_MAPS_API_KEY` (string, required, private), `BRAVE_API_KEY` (string, optional), `TEST_MODE` (boolean, default false) |
| **User and Group Configuration** | `user` (int, default 568, min 568), `group` (int, default 568, min 568) — applies to backend + celery containers only |
| **Network Configuration** | `web_port` (int, default 30080, bind mode, host IPs), `host_network` (boolean, default false) |
| **Storage Configuration** | `travel_data` (ixVolume/host_path), `logs` (ixVolume/host_path, optional), `outputs` (ixVolume/host_path, optional) |
| **Resources Configuration** | CPU limit (default 4), memory limit (default 4096 MB) |

### ix_values.yaml

```yaml
images:
  backend_image:
    repository: ghcr.io/<user>/detour-ai-backend
    tag: "7.0.0"
  frontend_image:
    repository: ghcr.io/<user>/detour-ai-frontend
    tag: "7.0.0"
  redis_image:
    repository: redis
    tag: "7-alpine"
consts:
  backend_container_name: detour-ai-backend
  celery_container_name: detour-ai-celery
  frontend_container_name: detour-ai-frontend
  redis_container_name: detour-ai-redis
  perms_container_name: permissions
  data_path: /app/data
  logs_path: /app/logs
  outputs_path: /app/outputs
```

### Compose Template (Jinja2)

The template creates 4 services:

1. **redis** — Redis 7 Alpine, internal only, healthcheck via `redis-cli ping`
2. **backend** — FastAPI app, depends on redis, env vars from questions form, exposes port internally
3. **celery** — Same image as backend, command override `celery -A tasks worker --loglevel=info`, depends on redis
4. **frontend** — Nginx serving static files + proxying `/api` to backend, published port from questions form

All services share a Docker network. Storage volumes for `travel_data` and `logs` are mounted on both backend and celery. The `outputs` volume is mounted on backend only (celery does not generate output files).

---

## TrueNAS Deployment Experience

### One-Time Setup

1. **GHCR credentials:** TrueNAS Settings → Docker Registry → Add `ghcr.io` with GitHub PAT (scope: `read:packages`)
2. **Add catalog:** Apps → Discover → Manage Catalogs → Add Catalog → repo URL: `https://github.com/<user>/detour-ai-catalog`, train: `stable`, branch: `main`

### Installing

1. DetourAI appears in the Discover screen
2. Click Install → fill in API keys, choose port, configure storage
3. TrueNAS renders the compose template and deploys 4 containers

### Updating

1. Push `release/v8.0.0` tag → pipeline builds images + updates catalog
2. TrueNAS: Refresh Catalog (or automatic periodic check)
3. "Update available" badge appears on DetourAI
4. Click Update → TrueNAS pulls new images and redeploys

---

## Changes to DetourAI

### New Files

| File | Purpose |
|------|---------|
| `.github/workflows/release.yml` | GitHub Actions release pipeline |
| `scripts/update-catalog.sh` | Helper script to update the catalog repo (used by pipeline + manual) |

### Minimal Changes to Existing Files

| File | Change |
|------|--------|
| `infra/Dockerfile.backend` | Pin UID/GID to 568: change `addgroup --system appgroup` → `addgroup --system --gid 568 appgroup` and `adduser --system --ingroup appgroup appuser` → `adduser --system --uid 568 --ingroup appgroup appuser` |

All other files (docker-compose.yml, deploy.sh, install.sh, source code) remain unchanged. The pipeline builds from the existing Dockerfiles. The catalog repo has its own adapted compose template referencing GHCR images.

---

## Developer Workflow

```bash
# Normal development (unchanged)
git add <files>
git commit -m "feat: neue Funktion"
git tag v6.1.75
git push && git push --tags

# When ready to deploy to TrueNAS
git tag release/v7.0.0
git push --tags
# → Pipeline runs automatically
# → TrueNAS sees update on next catalog refresh
```

---

## Rollback

If a release is broken, tag a known-good commit as the next release version and push:
```bash
git tag release/v7.0.1 <known-good-sha>
git push --tags
# Pipeline runs, publishes the good version as a new catalog update
```

TrueNAS will see the new catalog version and offer an update back to the working state.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `ix_lib` API changes between TrueNAS versions | Pin `lib_version` in app.yaml, test after TrueNAS updates |
| iXsystems drops custom catalog support | Fallback to manual Docker Compose deployment (compose file is standard) |
| GHCR rate limits | Images are small, private repo has generous limits |
| Catalog repo push fails | Pipeline fails visibly, manual `scripts/update-catalog.sh` as fallback |
