---
phase: quick-260408-nwc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/dump-openapi.py
  - scripts/generate-types.sh
  - contracts/api-contract.yaml
  - contracts/sse-events.md
autonomous: true
requirements:
  - QUICK-260408-nwc-phase2-api-contract-layer
must_haves:
  truths:
    - "contracts/api-contract.yaml exists and contains all FastAPI endpoints"
    - "contracts/sse-events.md documents all SSE event types with data shapes"
    - "scripts/dump-openapi.py runs without a running server and regenerates the YAML"
    - "scripts/generate-types.sh uses contracts/api-contract.yaml when available, falls back to localhost"
  artifacts:
    - path: "scripts/dump-openapi.py"
      provides: "Offline OpenAPI schema dump — no server required"
      exports: ["generates contracts/api-contract.yaml"]
    - path: "contracts/api-contract.yaml"
      provides: "Committed, offline-readable API contract for all workers"
      contains: "openapi:"
    - path: "contracts/sse-events.md"
      provides: "Hand-written SSE event reference for Frontend Specialist worker"
      contains: "job_complete"
  key_links:
    - from: "scripts/dump-openapi.py"
      to: "contracts/api-contract.yaml"
      via: "app.openapi() call"
    - from: "scripts/generate-types.sh"
      to: "contracts/api-contract.yaml"
      via: "file existence check before hitting localhost"
---

<objective>
Create the API contract layer for Phase 2 of the agentic worker architecture. Produces
three artifacts that both the Backend API Specialist and Frontend Specialist workers
reference when making changes:

1. `scripts/dump-openapi.py` — regenerates the contract offline (no running server needed)
2. `contracts/api-contract.yaml` — committed snapshot of the full OpenAPI schema
3. `contracts/sse-events.md` — human-readable SSE event reference

Also updates `scripts/generate-types.sh` to prefer the contract file over hitting a
live server.

Purpose: Workers need a single, offline-readable source of truth for the API surface.
This removes the need for workers to start a server or explore endpoint code to
understand contracts.

Output: `contracts/` directory with two reference files; updated `generate-types.sh`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create scripts/dump-openapi.py</name>
  <files>scripts/dump-openapi.py</files>
  <action>
Create `/Users/stefan/Code/Travelman3/scripts/dump-openapi.py` that imports the FastAPI
app statically (no server start) and dumps its OpenAPI schema to `contracts/api-contract.yaml`.

Key implementation requirements:
- Add `backend/` to `sys.path` BEFORE any imports from the app
- Use `os.chdir` or path-relative logic so the script runs from repo root
- Import `from main import app` after sys.path is set
- Call `app.openapi()` to get the schema dict
- Try `import yaml` first; if available, dump to `contracts/api-contract.yaml`
- If yaml not installed, fall back to `json.dumps` and write `contracts/api-contract.json`
- Create the `contracts/` directory if it does not exist (`Path.mkdir(exist_ok=True)`)
- Print a success message showing which file was written and how many paths it contains
  (e.g., `len(schema.get("paths", {}))` path count)
- Do NOT call `uvicorn.run()` or any lifespan-triggering code
- The script must be runnable as: `python3 scripts/dump-openapi.py` from repo root

The app module-level code in `main.py` calls `_make_redis_client()` and `load_dotenv()`
on import — these are side effects but safe (Redis falls back to in-memory, dotenv is
a no-op if `.env` is absent). Do NOT mock these — just let them run.

After writing the script, run it to generate the initial `contracts/api-contract.yaml`:
```bash
cd /Users/stefan/Code/Travelman3 && python3 scripts/dump-openapi.py
```
If yaml is not installed, install it first: `pip3 install pyyaml`.
  </action>
  <verify>
    <automated>cd /Users/stefan/Code/Travelman3 && python3 scripts/dump-openapi.py && test -f contracts/api-contract.yaml && echo "OK: contracts/api-contract.yaml exists" || (test -f contracts/api-contract.json && echo "OK: contracts/api-contract.json exists (yaml not installed)")</automated>
  </verify>
  <done>
    - `scripts/dump-openapi.py` exists and runs without error from repo root
    - `contracts/api-contract.yaml` (or .json) exists and is non-empty
    - Script output shows endpoint path count (should be 30+ paths)
  </done>
</task>

<task type="auto">
  <name>Task 2: Create contracts/sse-events.md</name>
  <files>contracts/sse-events.md</files>
  <action>
Create `/Users/stefan/Code/Travelman3/contracts/sse-events.md` — a hand-written reference
document (~60 lines) for all SSE events emitted by the backend.

Structure each event as a table row or definition block with:
- Event name (exact string used in the SSE stream)
- Data shape (JSON fields, with types)
- Which backend component emits it (agent name or "orchestrator" or "main.py")
- When it fires in the user flow

Document ALL of the following events in order of when they fire in the planning lifecycle:

**Route building phase (main.py / StopOptionsFinder):**
- `ping` — keepalive, no data, fires every 15s
- `debug_log` — `{message: str, level: str}` — debug_logger, throughout
- `route_option_ready` — `{option: StopOption}` — StopOptionsFinderAgent, one per option presented
- `route_options_done` — `{}` — main.py, all options for current stop delivered
- `stop_done` — `{stop_index: int}` — main.py, user confirmed a stop
- `region_plan_ready` — `{regions: RegionPlan[]}` — RegionPlannerAgent, after initial route built
- `region_updated` — `{region: RegionPlan}` — main.py, after user replaces a region

**Accommodation phase (prefetch_accommodations task):**
- `accommodation_loading` — `{stop_index: int}` — AccommodationResearcherAgent, starting fetch
- `accommodation_loaded` — `{stop_index: int, option: AccommodationOption}` — one result ready
- `accommodations_all_loaded` — `{stop_index: int}` — all accommodations for stop delivered

**Full planning phase (Celery: run_planning_job):**
- `stop_research_started` — `{stop_index: int, stop_name: str}` — orchestrator, research beginning
- `activities_loaded` — `{stop_index: int, activities: Activity[]}` — ActivitiesAgent
- `restaurants_loaded` — `{stop_index: int, restaurants: Restaurant[]}` — RestaurantsAgent
- `leg_complete` — `{leg_index: int}` — orchestrator, one trip leg fully planned
- `route_ready` — `{stops: TravelStop[], geometry: str}` — orchestrator, route confirmed with geometry

**Stop replacement phase (replace_stop_job task):**
- `replace_stop_progress` — `{message: str}` — replace_stop_job, in-progress update
- `replace_stop_complete` — `{stop: TravelStop}` — replace_stop_job, replacement done

**Terminal events:**
- `job_complete` — `{result: TravelPlan}` — orchestrator/main.py, full planning done
- `job_error` — `{error: str}` — any component, fatal failure — client must close SSE

**Optional/conditional:**
- `style_mismatch_warning` — `{message: str}` — main.py, travel style inconsistency detected
- `agent_start` — `{agent: str}` — orchestrator, agent lifecycle
- `agent_done` — `{agent: str, duration_ms: int}` — orchestrator, agent finished

Add a note at the top: SSE auth is via `?token=` query param (EventSource doesn't
support Authorization headers). SSE streams close on `job_complete` or `job_error`.
  </action>
  <verify>
    <automated>test -f /Users/stefan/Code/Travelman3/contracts/sse-events.md && grep -q "job_complete" /Users/stefan/Code/Travelman3/contracts/sse-events.md && grep -q "ping" /Users/stefan/Code/Travelman3/contracts/sse-events.md && echo "OK: sse-events.md exists with required events"</automated>
  </verify>
  <done>
    - `contracts/sse-events.md` exists
    - All ~20 SSE events documented with data shapes and emitting component
    - `job_complete` and `job_error` marked as terminal events
    - Auth note about `?token=` query param present
  </done>
</task>

<task type="auto">
  <name>Task 3: Update scripts/generate-types.sh to prefer contract file</name>
  <files>scripts/generate-types.sh</files>
  <action>
Update `/Users/stefan/Code/Travelman3/scripts/generate-types.sh` to prefer reading
from `contracts/api-contract.yaml` when available, falling back to hitting a live
localhost server only if the file does not exist.

New logic:
1. Check if `contracts/api-contract.yaml` exists (relative to repo root — script should
   work from any directory so use `SCRIPT_DIR` to find the repo root)
2. If yes: extract the OpenAPI JSON from the YAML file and pass to `openapi-typescript`
   - Use `python3 -c "import yaml,json,sys; print(json.dumps(yaml.safe_load(sys.stdin)))" < contracts/api-contract.yaml`
   - Pipe into a temp file or use `--stdin` if supported by openapi-typescript
   - Simplest approach: convert YAML to temp JSON file, pass as local path to openapi-typescript
3. If no: fall back to the current server-based approach (start uvicorn, wait 2s, hit
   localhost:18765, kill server)
4. Either path must produce `frontend/js/types.d.ts`

The updated script should:
- Echo which mode it is using ("Verwende contracts/api-contract.yaml" or "Starte lokalen Server...")
- Be backward-compatible (if contracts file is missing, old behavior unchanged)
- Handle the YAML→JSON conversion with the python3 one-liner (no new dependencies)
- Clean up any temp files in a `trap` block

Preserve the existing `set -e` and `echo "Done: frontend/js/types.d.ts"` at the end.
  </action>
  <verify>
    <automated>cd /Users/stefan/Code/Travelman3 && bash -n scripts/generate-types.sh && grep -q "api-contract.yaml" scripts/generate-types.sh && grep -q "uvicorn" scripts/generate-types.sh && echo "OK: generate-types.sh is valid and has both paths"</automated>
  </verify>
  <done>
    - `scripts/generate-types.sh` passes `bash -n` (syntax check)
    - File contains reference to `contracts/api-contract.yaml` (preferred path)
    - File retains uvicorn fallback path
    - Script echoes which mode it uses
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| script → filesystem | dump-openapi.py writes to contracts/ — no user input involved |
| contract files → workers | Workers read contracts/ files as read-only reference — no execution |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-nwc-01 | Information Disclosure | contracts/api-contract.yaml | accept | File contains endpoint schema only — no secrets, keys, or user data. Safe to commit. |
| T-nwc-02 | Tampering | dump-openapi.py | accept | Script is dev tooling, not production code. Runs under developer account only. |
</threat_model>

<verification>
After all tasks complete, verify the full contract layer is in place:

```bash
# 1. Contract file exists and has endpoints
test -f /Users/stefan/Code/Travelman3/contracts/api-contract.yaml && echo "YAML exists"
python3 -c "import yaml; d=yaml.safe_load(open('contracts/api-contract.yaml')); print(f'{len(d[\"paths\"])} endpoints documented')"

# 2. SSE reference exists
test -f /Users/stefan/Code/Travelman3/contracts/sse-events.md && wc -l /Users/stefan/Code/Travelman3/contracts/sse-events.md

# 3. Dump script is idempotent
cd /Users/stefan/Code/Travelman3 && python3 scripts/dump-openapi.py

# 4. generate-types.sh syntax is valid
bash -n /Users/stefan/Code/Travelman3/scripts/generate-types.sh
```
</verification>

<success_criteria>
- `contracts/api-contract.yaml` exists, committed, contains 30+ endpoint paths
- `contracts/sse-events.md` exists, committed, documents all ~20 SSE events
- `scripts/dump-openapi.py` runs from repo root without a running server, regenerates YAML
- `scripts/generate-types.sh` uses YAML contract file when present, falls back to localhost
- Both contract files are readable offline by worker Claude instances
</success_criteria>

<output>
After completion, create `.planning/quick/260408-nwc-phase-2-api-contract-layer-create-contra/260408-nwc-SUMMARY.md`

Include:
- Files created/modified
- Endpoint count in api-contract.yaml
- SSE event count in sse-events.md
- How to regenerate: `python3 scripts/dump-openapi.py`
- How to use in generate-types.sh: automatic (prefers contract file)
</output>
