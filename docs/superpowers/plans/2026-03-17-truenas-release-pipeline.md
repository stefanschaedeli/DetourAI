# TrueNAS Release Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automated release pipeline that builds Docker images, pushes to GHCR, and updates a TrueNAS custom app catalog for one-click install/update on TrueNAS 25.04.

**Architecture:** Two GitHub repos — Travelman3 (source + pipeline) and travelman-catalog (TrueNAS catalog metadata). Pipeline triggered by `release/v*` tags builds 2 Docker images, pushes to GHCR, then clones and updates the catalog repo with new version snapshots.

**Tech Stack:** GitHub Actions, Docker buildx, GHCR, TrueNAS ix_lib Jinja2 templates, Bash

**Spec:** `docs/superpowers/specs/2026-03-17-truenas-release-pipeline-design.md`

---

## File Map

### Travelman3 (this repo)

| File | Action | Responsibility |
|------|--------|---------------|
| `infra/Dockerfile.backend` | Modify (line 6-7) | Pin UID/GID to 568 |
| `.github/workflows/release.yml` | Create | GitHub Actions release pipeline |
| `scripts/update-catalog.sh` | Create | Clone catalog repo, update version files, commit + push |

### travelman-catalog (new repo)

| File | Action | Responsibility |
|------|--------|---------------|
| `catalog.json` | Create | Root catalog index |
| `features_capability.json` | Create | TrueNAS version feature gates |
| `ix-dev/stable/travelman/app.yaml` | Create | App metadata |
| `ix-dev/stable/travelman/ix_values.yaml` | Create | Image repos + tags + constants |
| `ix-dev/stable/travelman/questions.yaml` | Create | TrueNAS UI config form |
| `ix-dev/stable/travelman/README.md` | Create | Short app description |
| `ix-dev/stable/travelman/item.yaml` | Create | Categories, icon, tags |
| `ix-dev/stable/travelman/templates/docker-compose.yaml` | Create | Jinja2 compose template |
| `ix-dev/stable/travelman/templates/test_values/basic-values.yaml` | Create | CI test values |
| `trains/stable/travelman/item.yaml` | Create | Published catalog entry |
| `trains/stable/travelman/app_versions.json` | Create | Version index |
| `trains/stable/travelman/1.0.0/` | Create | Initial version snapshot |

---

## Chunk 1: Dockerfile Fix + Catalog Repo Setup

### Task 1: Pin UID/GID in Dockerfile.backend

**Files:**
- Modify: `infra/Dockerfile.backend:6-7`

- [ ] **Step 1: Update addgroup/adduser with explicit UID/GID and add /app/logs**

In `infra/Dockerfile.backend`, change lines 6-9 from:

```dockerfile
RUN addgroup --system appgroup \
 && adduser --system --ingroup appgroup appuser \
 && mkdir -p /app/outputs /app/data \
 && chown -R appuser:appgroup /app/outputs /app/data
```

to:

```dockerfile
RUN addgroup --system --gid 568 appgroup \
 && adduser --system --uid 568 --ingroup appgroup appuser \
 && mkdir -p /app/outputs /app/data /app/logs \
 && chown -R appuser:appgroup /app/outputs /app/data /app/logs
```

- [ ] **Step 2: Verify Docker build still works**

Run: `docker build -f infra/Dockerfile.backend -t travelman-backend-test .`
Expected: Build completes successfully

- [ ] **Step 3: Verify user inside container**

Run: `docker run --rm travelman-backend-test id`
Expected: Output contains `uid=568` and `gid=568`

- [ ] **Step 4: Commit**

```bash
git add infra/Dockerfile.backend
git commit -m "fix: Pin UID/GID 568 in Backend-Dockerfile für TrueNAS-Kompatibilität

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 2: Create travelman-catalog repo on GitHub

This task is performed manually via GitHub UI or `gh` CLI. The plan provides the exact commands.

- [ ] **Step 1: Create the repository**

```bash
gh repo create travelman-catalog --private --description "TrueNAS custom app catalog for Travelman" --clone
cd travelman-catalog
```

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p ix-dev/stable/travelman/templates/test_values
mkdir -p ix-dev/stable/travelman/templates/library
mkdir -p trains/stable/travelman/1.0.0
mkdir -p assets
```

- [ ] **Step 3: Create `.gitignore`**

```
.DS_Store
*.pyc
__pycache__/
```

- [ ] **Step 4: Download ix_lib library from official TrueNAS apps repo (CRITICAL)**

The Jinja2 compose template requires the `ix_lib` Python library to render. Copy it from the official TrueNAS apps repo:

```bash
# Check which library version is current
LIB_VERSION="2.2.2"  # Match the lib_version in app.yaml

# Clone official apps repo (sparse checkout for just the library)
git clone --depth 1 --filter=blob:none --sparse https://github.com/truenas/apps.git /tmp/truenas-apps
cd /tmp/truenas-apps
git sparse-checkout set "library/$LIB_VERSION"
cd -

# Copy library into our catalog
cp -r /tmp/truenas-apps/library/$LIB_VERSION ix-dev/stable/travelman/templates/library/base_v2_2_2

# Compute lib_version_hash for app.yaml
LIB_HASH=$(find ix-dev/stable/travelman/templates/library/ -type f -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)
echo "lib_version_hash: $LIB_HASH"
# Update app.yaml with the computed hash (replace the empty string)

# Cleanup
rm -rf /tmp/truenas-apps
```

> **Note:** The exact library directory name (`base_v2_2_2`) must match the version format used in the official repo. Check `/tmp/truenas-apps/library/` for the exact directory name and adjust if needed.

- [ ] **Step 4: Create `features_capability.json`**

Create file `features_capability.json` at repo root:

```json
{
  "normalize/acl": {
    "stable": {"min": "24.10-ALPHA"}
  },
  "normalize/ix_volume": {
    "stable": {"min": "24.10-ALPHA"}
  },
  "definitions/node_bind_ip": {
    "stable": {"min": "24.10-ALPHA"}
  },
  "definitions/certificate": {
    "stable": {"min": "24.10-ALPHA"}
  }
}
```

- [ ] **Step 5: Create `ix-dev/stable/travelman/app.yaml`**

```yaml
annotations:
  min_scale_version: 24.10.2.2
app_version: "1.0.0"
capabilities: []
categories:
  - productivity
changelog_url: https://github.com/<user>/Travelman3/releases
date_added: "2026-03-17"
description: "KI-gestützter Roadtrip-Planer mit interaktiver Routenplanung, Unterkünften, Aktivitäten und Tagesführer."
home: https://github.com/<user>/Travelman3
icon: https://raw.githubusercontent.com/<user>/travelman-catalog/main/assets/icon.png
keywords:
  - travel
  - planner
  - ai
lib_version: 2.2.2
lib_version_hash: ""
maintainers:
  - name: stefan
    email: ""
name: travelman
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
screenshots: []
sources:
  - https://github.com/<user>/Travelman3
title: Travelman
train: stable
version: "1.0.0"
```

> **Note:** Replace `<user>` with your actual GitHub username throughout all files.

- [ ] **Step 6: Create `ix-dev/stable/travelman/ix_values.yaml`**

```yaml
images:
  backend_image:
    repository: ghcr.io/<user>/travelman-backend
    tag: "1.0.0"
  frontend_image:
    repository: ghcr.io/<user>/travelman-frontend
    tag: "1.0.0"
  redis_image:
    repository: redis
    tag: "7-alpine"
consts:
  backend_container_name: travelman-backend
  celery_container_name: travelman-celery
  frontend_container_name: travelman-frontend
  redis_container_name: travelman-redis
  perms_container_name: permissions
  data_path: /app/data
  logs_path: /app/logs
  outputs_path: /app/outputs
```

- [ ] **Step 7: Create `ix-dev/stable/travelman/questions.yaml`**

```yaml
groups:
  - name: Travelman Configuration
    description: Configure Travelman
  - name: User and Group Configuration
    description: Configure User and Group for Travelman
  - name: Network Configuration
    description: Configure Network for Travelman
  - name: Storage Configuration
    description: Configure Storage for Travelman
  - name: Resources Configuration
    description: Configure Resources for Travelman

questions:
  - variable: travelman
    label: ""
    group: Travelman Configuration
    schema:
      type: dict
      attrs:
        - variable: anthropic_api_key
          label: Anthropic API Key
          description: API key for Claude AI (required).
          schema:
            type: string
            required: true
            private: true
        - variable: google_maps_api_key
          label: Google Maps API Key
          description: API key for Google Maps (Geocoding, Directions, Places).
          schema:
            type: string
            required: true
            private: true
        - variable: brave_api_key
          label: Brave Search API Key
          description: Optional API key for Brave Search.
          schema:
            type: string
            default: ""
        - variable: test_mode
          label: Test Mode
          description: |
            When enabled, all AI agents use claude-haiku-4-5 (cheaper, faster).</br>
            When disabled, production models are used (Opus/Sonnet).
          schema:
            type: boolean
            default: false

  - variable: run_as
    label: ""
    group: User and Group Configuration
    schema:
      type: dict
      attrs:
        - variable: user
          label: User ID
          description: The user id that Travelman data files will be owned by.
          schema:
            type: int
            min: 568
            default: 568
            required: true
        - variable: group
          label: Group ID
          description: The group id that Travelman data files will be owned by.
          schema:
            type: int
            min: 568
            default: 568
            required: true

  - variable: network
    label: ""
    group: Network Configuration
    schema:
      type: dict
      attrs:
        - variable: web_port
          label: WebUI Port
          schema:
            type: dict
            attrs:
              - variable: bind_mode
                label: Port Bind Mode
                description: |
                  The port bind mode.</br>
                  - Publish: The port will be published on the host for external access.</br>
                  - Expose: The port will be exposed for inter-container communication.</br>
                  - None: The port will not be exposed or published.
                schema:
                  type: string
                  default: "published"
                  enum:
                    - value: "published"
                      description: Publish port on the host for external access
                    - value: "exposed"
                      description: Expose port for inter-container communication
                    - value: ""
                      description: None
              - variable: port_number
                label: Port Number
                schema:
                  type: int
                  default: 30080
                  min: 1
                  max: 65535
                  required: true
              - variable: host_ips
                label: Host IPs
                description: IPs on the host to bind this port
                schema:
                  type: list
                  show_if: [["bind_mode", "=", "published"]]
                  default: []
                  items:
                    - variable: host_ip
                      label: Host IP
                      schema:
                        type: string
                        required: true
                        $ref:
                          - definitions/node_bind_ip

  - variable: storage
    label: ""
    group: Storage Configuration
    schema:
      type: dict
      attrs:
        - variable: data
          label: Travel Data Storage
          description: The path to store travel plan data (SQLite database).
          schema:
            type: dict
            attrs:
              - variable: type
                label: Type
                description: |
                  ixVolume: Is dataset created automatically by the system.</br>
                  Host Path: Is a path that already exists on the system.
                schema:
                  type: string
                  required: true
                  default: "ix_volume"
                  enum:
                    - value: "host_path"
                      description: Host Path (Path that already exists on the system)
                    - value: "ix_volume"
                      description: ixVolume (Dataset created automatically by the system)
              - variable: ix_volume_config
                label: ixVolume Configuration
                description: The configuration for the ixVolume dataset.
                schema:
                  type: dict
                  show_if: [["type", "=", "ix_volume"]]
                  $ref:
                    - "normalize/ix_volume"
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      description: Enable ACL for the storage.
                      schema:
                        type: boolean
                        default: false
                    - variable: dataset_name
                      label: Dataset Name
                      description: The name of the dataset to use for storage.
                      schema:
                        type: string
                        required: true
                        hidden: true
                        default: "data"
                    - variable: acl_entries
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
              - variable: host_path_config
                label: Host Path Configuration
                schema:
                  type: dict
                  show_if: [["type", "=", "host_path"]]
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      description: Enable ACL for the storage.
                      schema:
                        type: boolean
                        default: false
                    - variable: acl
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
                        $ref:
                          - "normalize/acl"
                    - variable: path
                      label: Host Path
                      description: The host path to use for storage.
                      schema:
                        type: hostpath
                        show_if: [["acl_enable", "=", false]]
                        required: true
        - variable: logs
          label: Logs Storage
          description: The path to store application logs.
          schema:
            type: dict
            attrs:
              - variable: type
                label: Type
                schema:
                  type: string
                  required: true
                  default: "ix_volume"
                  enum:
                    - value: "host_path"
                      description: Host Path (Path that already exists on the system)
                    - value: "ix_volume"
                      description: ixVolume (Dataset created automatically by the system)
              - variable: ix_volume_config
                label: ixVolume Configuration
                schema:
                  type: dict
                  show_if: [["type", "=", "ix_volume"]]
                  $ref:
                    - "normalize/ix_volume"
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      schema:
                        type: boolean
                        default: false
                    - variable: dataset_name
                      label: Dataset Name
                      schema:
                        type: string
                        required: true
                        hidden: true
                        default: "logs"
                    - variable: acl_entries
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
              - variable: host_path_config
                label: Host Path Configuration
                schema:
                  type: dict
                  show_if: [["type", "=", "host_path"]]
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      schema:
                        type: boolean
                        default: false
                    - variable: acl
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
                        $ref:
                          - "normalize/acl"
                    - variable: path
                      label: Host Path
                      schema:
                        type: hostpath
                        show_if: [["acl_enable", "=", false]]
                        required: true
        - variable: outputs
          label: Outputs Storage
          description: The path to store generated PDF/PPTX files.
          schema:
            type: dict
            attrs:
              - variable: type
                label: Type
                schema:
                  type: string
                  required: true
                  default: "ix_volume"
                  enum:
                    - value: "host_path"
                      description: Host Path (Path that already exists on the system)
                    - value: "ix_volume"
                      description: ixVolume (Dataset created automatically by the system)
              - variable: ix_volume_config
                label: ixVolume Configuration
                schema:
                  type: dict
                  show_if: [["type", "=", "ix_volume"]]
                  $ref:
                    - "normalize/ix_volume"
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      schema:
                        type: boolean
                        default: false
                    - variable: dataset_name
                      label: Dataset Name
                      schema:
                        type: string
                        required: true
                        hidden: true
                        default: "outputs"
                    - variable: acl_entries
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
              - variable: host_path_config
                label: Host Path Configuration
                schema:
                  type: dict
                  show_if: [["type", "=", "host_path"]]
                  attrs:
                    - variable: acl_enable
                      label: Enable ACL
                      schema:
                        type: boolean
                        default: false
                    - variable: acl
                      label: ACL Configuration
                      schema:
                        type: dict
                        show_if: [["acl_enable", "=", true]]
                        attrs: []
                        $ref:
                          - "normalize/acl"
                    - variable: path
                      label: Host Path
                      schema:
                        type: hostpath
                        show_if: [["acl_enable", "=", false]]
                        required: true

  - variable: resources
    label: ""
    group: Resources Configuration
    schema:
      type: dict
      attrs:
        - variable: limits
          label: Limits
          schema:
            type: dict
            attrs:
              - variable: cpus
                label: CPUs
                description: CPUs limit for Travelman.
                schema:
                  type: int
                  default: 4
                  required: true
              - variable: memory
                label: Memory (in MB)
                description: Memory limit for Travelman.
                schema:
                  type: int
                  default: 4096
                  required: true
```

- [ ] **Step 8: Create `ix-dev/stable/travelman/templates/docker-compose.yaml`**

This is the Jinja2 template that uses `ix_lib` to render the final Docker Compose file. It creates 4 services: redis, backend, celery, frontend.

```yaml
{% set tpl = ix_lib.base.render.Render(values) %}

{# ── Redis ── #}
{% set redis = tpl.add_container(values.consts.redis_container_name, "redis_image") %}
{% do redis.healthcheck.set_test("redis", {"port": 6379}) %}

{# ── Permissions init container ── #}
{% set perm_container = tpl.deps.perms(values.consts.perms_container_name) %}
{% set perms_config = {"uid": values.run_as.user, "gid": values.run_as.group, "mode": "check"} %}

{# ── Backend (FastAPI) ── #}
{% set backend = tpl.add_container(values.consts.backend_container_name, "backend_image") %}
{% do backend.set_user(values.run_as.user, values.run_as.group) %}
{% do backend.depends.add_dependency(values.consts.redis_container_name, "service_healthy") %}
{% do backend.healthcheck.set_test("curl", {"port": 8000, "path": "/api/health"}) %}

{% do backend.environment.add_env("ANTHROPIC_API_KEY", values.travelman.anthropic_api_key) %}
{% do backend.environment.add_env("GOOGLE_MAPS_API_KEY", values.travelman.google_maps_api_key) %}
{% if values.travelman.brave_api_key %}
{% do backend.environment.add_env("BRAVE_API_KEY", values.travelman.brave_api_key) %}
{% endif %}
{% do backend.environment.add_env("TEST_MODE", values.travelman.test_mode | string | lower) %}
{% do backend.environment.add_env("REDIS_URL", "redis://%s:6379" | format(values.consts.redis_container_name)) %}
{% do backend.environment.add_env("DATA_DIR", values.consts.data_path) %}
{% do backend.environment.add_env("LOGS_DIR", values.consts.logs_path) %}
{% do backend.environment.add_env("OUTPUTS_DIR", values.consts.outputs_path) %}

{% do backend.add_storage(values.consts.data_path, values.storage.data) %}
{% do backend.add_storage(values.consts.logs_path, values.storage.logs) %}
{% do backend.add_storage(values.consts.outputs_path, values.storage.outputs) %}
{% do perm_container.add_or_skip_action("data", values.storage.data, perms_config) %}
{% do perm_container.add_or_skip_action("logs", values.storage.logs, perms_config) %}
{% do perm_container.add_or_skip_action("outputs", values.storage.outputs, perms_config) %}

{# ── Celery Worker ── #}
{% set celery = tpl.add_container(values.consts.celery_container_name, "backend_image") %}
{% do celery.set_user(values.run_as.user, values.run_as.group) %}
{% do celery.set_command(["celery", "-A", "tasks", "worker", "--loglevel=info"]) %}
{% do celery.depends.add_dependency(values.consts.redis_container_name, "service_healthy") %}
{% do celery.healthcheck.set_custom_test("celery -A tasks inspect ping --timeout 10") %}

{% do celery.environment.add_env("ANTHROPIC_API_KEY", values.travelman.anthropic_api_key) %}
{% do celery.environment.add_env("GOOGLE_MAPS_API_KEY", values.travelman.google_maps_api_key) %}
{% if values.travelman.brave_api_key %}
{% do celery.environment.add_env("BRAVE_API_KEY", values.travelman.brave_api_key) %}
{% endif %}
{% do celery.environment.add_env("TEST_MODE", values.travelman.test_mode | string | lower) %}
{% do celery.environment.add_env("REDIS_URL", "redis://%s:6379" | format(values.consts.redis_container_name)) %}
{% do celery.environment.add_env("DATA_DIR", values.consts.data_path) %}
{% do celery.environment.add_env("LOGS_DIR", values.consts.logs_path) %}

{% do celery.add_storage(values.consts.data_path, values.storage.data) %}
{% do celery.add_storage(values.consts.logs_path, values.storage.logs) %}

{# ── Frontend (Nginx) ── #}
{% set frontend = tpl.add_container(values.consts.frontend_container_name, "frontend_image") %}
{% do frontend.depends.add_dependency(values.consts.backend_container_name, "service_healthy") %}
{% do frontend.healthcheck.set_test("curl", {"port": 8080, "path": "/"}) %}
{% do frontend.add_port(values.network.web_port) %}

{# ── Permissions activation ── #}
{% if perm_container.has_actions() %}
  {% do perm_container.activate() %}
  {% do backend.depends.add_dependency(values.consts.perms_container_name, "service_completed_successfully") %}
  {% do celery.depends.add_dependency(values.consts.perms_container_name, "service_completed_successfully") %}
{% endif %}

{# ── Portal link ── #}
{% do tpl.portals.add(values.network.web_port) %}

{{ tpl.render() | tojson }}
```

- [ ] **Step 9: Create `ix-dev/stable/travelman/item.yaml`**

```yaml
categories:
  - productivity
icon_url: https://raw.githubusercontent.com/<user>/travelman-catalog/main/assets/icon.png
screenshots: []
tags:
  - travel
  - planner
  - ai
```

- [ ] **Step 10: Create `ix-dev/stable/travelman/README.md`**

```markdown
# Travelman

KI-gestützter Roadtrip-Planer mit interaktiver Routenplanung, Unterkünften, Aktivitäten und Tagesführer.

- [GitHub](https://github.com/<user>/Travelman3)
```

- [ ] **Step 11: Create `ix-dev/stable/travelman/templates/test_values/basic-values.yaml`**

```yaml
travelman:
  anthropic_api_key: "sk-ant-test-key"
  google_maps_api_key: "test-maps-key"
  brave_api_key: ""
  test_mode: true

run_as:
  user: 568
  group: 568

network:
  web_port:
    bind_mode: "published"
    port_number: 30080
    host_ips: []

storage:
  data:
    type: "host_path"
    host_path_config:
      acl_enable: false
      path: /opt/tests/data
  logs:
    type: "host_path"
    host_path_config:
      acl_enable: false
      path: /opt/tests/logs
  outputs:
    type: "host_path"
    host_path_config:
      acl_enable: false
      path: /opt/tests/outputs

resources:
  limits:
    cpus: 2
    memory: 2048
```

- [ ] **Step 12: Create initial `trains/` version snapshot**

```bash
# Copy ix-dev files as initial version snapshot
cp -r ix-dev/stable/travelman/* trains/stable/travelman/1.0.0/
```

Create `trains/stable/travelman/item.yaml` (same content as ix-dev item.yaml).

Create `trains/stable/travelman/app_versions.json`:

```json
{
  "1.0.0": {
    "healthy": true,
    "supported": true,
    "healthy_error": null,
    "location": "/trains/stable/travelman/1.0.0",
    "last_update": "2026-03-17 00:00:00",
    "human_version": "1.0.0_1.0.0",
    "version": "1.0.0"
  }
}
```

- [ ] **Step 13: Create `catalog.json`**

```json
{
  "stable": {
    "travelman": {
      "name": "Travelman",
      "categories": ["productivity"],
      "app_version": "1.0.0",
      "train": "stable",
      "description": "KI-gestützter Roadtrip-Planer",
      "home": "https://github.com/<user>/Travelman3",
      "latest_version": "1.0.0",
      "latest_app_version": "1.0.0",
      "icon_url": "https://raw.githubusercontent.com/<user>/travelman-catalog/main/assets/icon.png"
    }
  }
}
```

- [ ] **Step 14: Add an app icon**

Place an icon image (PNG, ~256x256) at `assets/icon.png`. This can be any travel-themed icon for now.

- [ ] **Step 15: Verify no `<user>` placeholders remain**

```bash
grep -r '<user>' . --include='*.yaml' --include='*.json' --include='*.md' | head -20
```

Replace all occurrences with your actual GitHub username.

- [ ] **Step 16: Commit and push catalog repo**

```bash
git add -A
git commit -m "feat: Initial Travelman TrueNAS catalog

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push -u origin main
```

---

## Chunk 2: GitHub Actions Pipeline + Update Script

### Task 3: Create the catalog update script

**Files:**
- Create: `scripts/update-catalog.sh` (in Travelman3)

- [ ] **Step 1: Write the update script**

This script is used by the pipeline and can also be run manually. It:
1. Clones the catalog repo
2. Updates `ix_values.yaml` with new image tags
3. Updates `app.yaml` with bumped catalog version + new app_version
4. Creates a new version snapshot in `trains/`
5. Regenerates `app_versions.json` and `catalog.json`
6. Commits and pushes

Create `scripts/update-catalog.sh`:

```bash
#!/usr/bin/env bash
# update-catalog.sh — Update the TrueNAS catalog repo with a new release.
#
# Usage:
#   ./scripts/update-catalog.sh <app_version> <catalog_repo_url>
#
# Example:
#   ./scripts/update-catalog.sh 7.0.0 git@github.com:user/travelman-catalog.git
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

APP_DIR="ix-dev/stable/travelman"
TRAINS_DIR="trains/stable/travelman"

# ── Read current catalog version and bump minor ──
CURRENT_VERSION=$(grep '^version:' "$APP_DIR/app.yaml" | sed 's/version: *"\(.*\)"/\1/')
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
    if 'travelman' in img.get('repository', ''):
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
        'travelman': {
            'name': 'Travelman',
            'categories': ['productivity'],
            'app_version': '$APP_VERSION',
            'train': 'stable',
            'description': 'KI-gestützter Roadtrip-Planer',
            'home': 'https://github.com/$GITHUB_USER/Travelman3',
            'latest_version': '$NEW_CATALOG_VERSION',
            'latest_app_version': '$APP_VERSION',
            'icon_url': 'https://raw.githubusercontent.com/$GITHUB_USER/travelman-catalog/main/assets/icon.png'
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
git commit -m "release: Travelman $APP_VERSION (catalog $NEW_CATALOG_VERSION)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push

echo "==> Catalog updated: v$NEW_CATALOG_VERSION (app $APP_VERSION)"
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x scripts/update-catalog.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/update-catalog.sh
git commit -m "feat: Katalog-Update-Skript für TrueNAS-Releases

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 4: Create GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml` (in Travelman3)

- [ ] **Step 1: Create workflows directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write the workflow file**

Create `.github/workflows/release.yml`:

```yaml
name: Release & Deploy

on:
  push:
    tags:
      - 'release/v*'

env:
  REGISTRY: ghcr.io

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: python -m pytest tests/ -v

  build-and-push:
    name: Build & Push Images
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Extract version from tag
        id: version
        run: |
          TAG="${GITHUB_REF#refs/tags/release/v}"
          echo "app_version=$TAG" >> "$GITHUB_OUTPUT"
          echo "Released version: $TAG"

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push backend image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: infra/Dockerfile.backend
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ github.repository_owner }}/travelman-backend:${{ steps.version.outputs.app_version }}
            ${{ env.REGISTRY }}/${{ github.repository_owner }}/travelman-backend:latest
          platforms: linux/amd64

      - name: Build and push frontend image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: infra/Dockerfile.frontend
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ github.repository_owner }}/travelman-frontend:${{ steps.version.outputs.app_version }}
            ${{ env.REGISTRY }}/${{ github.repository_owner }}/travelman-frontend:latest
          platforms: linux/amd64

      - name: Update TrueNAS catalog
        env:
          GITHUB_USER: ${{ github.repository_owner }}
        run: |
          eval "$(ssh-agent -s)"
          echo "${{ secrets.CATALOG_DEPLOY_KEY }}" | ssh-add -
          mkdir -p ~/.ssh
          ssh-keyscan github.com >> ~/.ssh/known_hosts
          ./scripts/update-catalog.sh \
            "${{ steps.version.outputs.app_version }}" \
            "git@github.com:${{ github.repository_owner }}/travelman-catalog.git"

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          name: "Travelman ${{ steps.version.outputs.app_version }}"
          generate_release_notes: true
          draft: false
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat: GitHub Actions Release-Pipeline für TrueNAS-Deployment

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 5: Set up GitHub secrets and deploy key

This task is manual setup, documented here for reference.

- [ ] **Step 1: Generate SSH deploy key pair**

```bash
ssh-keygen -t ed25519 -C "travelman-catalog-deploy" -f /tmp/catalog-deploy-key -N ""
```

- [ ] **Step 2: Add public key to travelman-catalog repo**

Go to: `travelman-catalog` → Settings → Deploy keys → Add deploy key
- Title: "Travelman3 pipeline"
- Key: contents of `/tmp/catalog-deploy-key.pub`
- Allow write access: **checked**

- [ ] **Step 3: Add private key to Travelman3 repo**

Go to: `Travelman3` → Settings → Secrets and variables → Actions → New repository secret
- Name: `CATALOG_DEPLOY_KEY`
- Value: contents of `/tmp/catalog-deploy-key`

- [ ] **Step 4: Clean up local key files**

```bash
rm /tmp/catalog-deploy-key /tmp/catalog-deploy-key.pub
```

### Task 6: Test the full pipeline

- [ ] **Step 1: Push current changes**

```bash
git push
```

- [ ] **Step 2: Create and push a release tag**

```bash
git tag release/v1.0.0
git push --tags
```

- [ ] **Step 3: Monitor the pipeline**

Go to: `Travelman3` → Actions → watch the "Release & Deploy" workflow.

Expected:
1. Tests pass
2. Two images pushed to `ghcr.io/<user>/travelman-backend:1.0.0` and `ghcr.io/<user>/travelman-frontend:1.0.0`
3. Catalog repo updated with version `1.1.0` in `trains/`
4. GitHub Release created on Travelman3

- [ ] **Step 4: Verify on TrueNAS**

1. TrueNAS → Apps → Discover → Manage Catalogs → Refresh
2. Travelman should appear in the Discover screen
3. Click Install → verify config form shows API key fields, port, storage options

---

## Chunk 3: Post-Setup Verification

### Task 7: End-to-end verification checklist

- [ ] **Step 1: Verify GHCR images are accessible**

```bash
docker pull ghcr.io/<user>/travelman-backend:1.0.0
docker pull ghcr.io/<user>/travelman-frontend:1.0.0
```

- [ ] **Step 2: Verify catalog repo structure**

```bash
cd /tmp && git clone git@github.com:<user>/travelman-catalog.git
ls travelman-catalog/trains/stable/travelman/
# Expected: 1.0.0/  1.1.0/  app_versions.json  item.yaml
```

- [ ] **Step 3: Verify TrueNAS GHCR auth**

On TrueNAS: Settings → Docker Registry → verify `ghcr.io` entry exists with valid PAT.

- [ ] **Step 4: Test a second release**

```bash
# Back in Travelman3
git tag release/v1.0.1
git push --tags
```

After pipeline completes, verify on TrueNAS that an "Update available" badge appears.

- [ ] **Step 5: Commit version tag and push**

```bash
# Check current latest tag
git tag --sort=-v:refname | head -1
# Increment patch and tag
git tag v6.1.XX   # replace XX with next patch number
git push && git push --tags
```
