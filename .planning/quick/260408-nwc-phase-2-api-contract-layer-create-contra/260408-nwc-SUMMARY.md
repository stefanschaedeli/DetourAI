---
phase: quick-260408-nwc
plan: "01"
subsystem: contracts
tags: [api-contract, openapi, sse, tooling]
dependency_graph:
  requires: []
  provides: [contracts/api-contract.yaml, contracts/sse-events.md]
  affects: [scripts/generate-types.sh]
tech_stack:
  added: [pyyaml (already present)]
  patterns: [offline OpenAPI dump, YAML contract file]
key_files:
  created:
    - scripts/dump-openapi.py
    - contracts/api-contract.yaml
    - contracts/sse-events.md
  modified:
    - scripts/generate-types.sh
decisions:
  - "Use app.openapi() for schema extraction — no server startup required"
  - "YAML preferred over JSON for human readability; JSON fallback if pyyaml absent"
  - "generate-types.sh uses python3 yaml→json one-liner — no new runtime dependencies"
metrics:
  duration: "~8 min"
  completed: "2026-04-08"
  tasks_completed: 3
  files_changed: 4
---

# Phase quick-260408-nwc Plan 01: API Contract Layer — Summary

**One-liner:** Offline OpenAPI contract (48 endpoints) + SSE event reference created; generate-types.sh now uses YAML contract file instead of spinning up a local server.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create scripts/dump-openapi.py | 9b80320 | scripts/dump-openapi.py, contracts/api-contract.yaml |
| 2 | Create contracts/sse-events.md | 98b2d80 | contracts/sse-events.md |
| 3 | Update scripts/generate-types.sh | 7c3a1f3 | scripts/generate-types.sh |

## What Was Built

### scripts/dump-openapi.py
Imports the FastAPI app statically (no uvicorn), calls `app.openapi()`, and writes
the full OpenAPI schema to `contracts/api-contract.yaml`. Runs from repo root with:
```
python3 scripts/dump-openapi.py
```
Output: `OK: contracts/api-contract.yaml written (48 endpoint paths)`

### contracts/api-contract.yaml
Committed OpenAPI snapshot with 48 documented endpoints. 2116 lines. Readable
offline by any worker without starting the backend. Regenerated on demand via
`dump-openapi.py`.

### contracts/sse-events.md
88-line SSE event reference documenting all ~20 event types across 5 phases:
- Route building (ping, debug_log, route_option_ready, route_options_done, stop_done, region_plan_ready, region_updated)
- Accommodation (accommodation_loading, accommodation_loaded, accommodations_all_loaded)
- Full planning (stop_research_started, activities_loaded, restaurants_loaded, leg_complete, route_ready)
- Stop replacement (replace_stop_progress, replace_stop_complete)
- Terminal (job_complete, job_error)
- Optional/conditional (style_mismatch_warning, agent_start, agent_done)

Each event documents data shape, emitting component, and trigger point.

### scripts/generate-types.sh
Updated to check for `contracts/api-contract.yaml` first:
1. If file exists: converts YAML to temp JSON via `python3 -c "import yaml,json..."` and passes to `openapi-typescript` — no server needed.
2. If file missing: falls back to original behavior (start uvicorn on port 18765, hit localhost, kill server).

Script echoes which mode is active. Uses `trap` to clean up temp file on exit.

## How to Regenerate the Contract

```bash
python3 scripts/dump-openapi.py
```

Run this whenever backend endpoints change. Commit the updated `contracts/api-contract.yaml`.

## How to Use in generate-types.sh

Automatic. If `contracts/api-contract.yaml` exists (it does after this plan), the script
uses it. No server required. Run from any directory:

```bash
scripts/generate-types.sh
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- contracts/api-contract.yaml: FOUND
- contracts/sse-events.md: FOUND
- scripts/dump-openapi.py: FOUND
- scripts/generate-types.sh: updated with both paths
- Commits 9b80320, 98b2d80, 7c3a1f3: verified in git log
- Endpoint count: 48 (> 30 required)
- SSE event count: ~20 events documented
