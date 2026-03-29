# Architecture Research

**Domain:** AI agent pipeline improvements for trip planning
**Researched:** 2026-03-28
**Confidence:** HIGH — based on direct source reading of all affected files

---

## System Overview

### Current Pipeline (v1.1 baseline)

```
Frontend Form
    │ POST /api/plan-trip (TravelRequest)
    ▼
init-job / plan-trip endpoint (main.py)
    │ Calls StopOptionsFinderAgent → streams 3 options
    │ Stores options in Redis job state
    ▼
User selects stop (POST /api/select-stop/{job_id})
    │ Appends to job["selected_stops"]
    │ Calls StopOptionsFinderAgent again for next stop
    │ Repeats until route_could_be_complete
    ▼
POST /api/confirm-route/{job_id}
    ▼
POST /api/start-accommodations/{job_id}
    │ Parallel AccommodationResearcherAgent per stop
    ▼
User selects accommodations
POST /api/select-accommodation/{job_id}
    ▼
POST /api/start-planning/{job_id}
    │ Fires Celery task: run_planning_job
    ▼
TravelPlannerOrchestrator.run()
    │ Phase 2: Parallel research
    │   ├── ActivitiesAgent (per stop)
    │   ├── RestaurantsAgent (per stop)
    │   └── fetch_unsplash_images (per stop)
    │ Phase 2b: TravelGuideAgent (per stop, parallel)
    │ Phase 3: DayPlannerAgent (entire route)
    │ Phase 4: TripAnalysisAgent (summary)
    ▼
SSE job_complete event → frontend renders guide
```

### Job State Structure (Redis key: `job:{job_id}`)

```
{
  "status": "building_route" | "selecting_accommodations" | "running" | "complete",
  "request": { ...TravelRequest serialized... },
  "selected_stops": [...],          // all stops confirmed so far
  "current_options": [...],         // 3 options currently shown to user
  "stop_counter": int,              // auto-increment stop id
  "leg_index": int,                 // which TripLeg is active
  "segment_index": int,             // which via-point segment within leg
  "segment_budget": int,            // days available for current segment
  "segment_stops": [...],           // stops in current segment only
  "route_geometry_cache": {...},    // Google Directions cached per leg
  "selected_accommodations": [...],
  "prefetched_accommodations": {},
  "all_accommodation_options": {},
  "region_plan": null | {...},      // for explore legs
  "explore_segment_budgets": [],
  "explore_regions": [],
  "result": null | {...}
}
```

---

## Identified Gaps (v1.2 Problems to Solve)

### Gap 1: RouteArchitect output not forwarded to StopOptionsFinder

**Current flow:**
- `RouteArchitectAgent` runs only in `_run_transit_leg()` inside the Orchestrator
- This path is used for the **background Celery job**, NOT for the interactive route builder
- The interactive route builder (`/api/plan-trip`, `/api/select-stop`) bypasses RouteArchitect entirely — it only uses `StopOptionsFinderAgent` with geometry context
- StopOptionsFinder gets: route geometry, corridor cities, bearing, segment budget
- StopOptionsFinder does NOT get: architect's region notes, intended day distribution, style rationale

**Root cause:** Two separate code paths exist:
1. Interactive route building (main.py) — StopOptionsFinder only
2. Celery background planning (orchestrator.py) — RouteArchitect + Orchestrator

The RouteArchitect plan was designed for the legacy non-interactive flow. The interactive flow has no equivalent planning step before stop selection starts.

### Gap 2: Nights assigned as `min_nights_per_stop` everywhere

**Current flow:**
- When a stop is selected via `/api/select-stop`, `selected["nights"]` comes directly from StopOptionsFinder's JSON output
- StopOptionsFinder hardcodes `"nights": {req.min_nights_per_stop}–{req.max_nights_per_stop}` in its prompt with no intelligence
- Via-points are hardcoded: `"nights": request.min_nights_per_stop`
- Segment budget calculation (`_calc_leg_segment_budget`) distributes total leg days evenly across segments with floor division — no quality-based weighting
- The destination stop is given leftover days: `min(days_left, request.max_nights_per_stop)`

**Root cause:** No intelligence anywhere assigns nights based on stop potential/type. All distribution is arithmetic.

### Gap 3: StopOptionsFinder has no stop history awareness

**Current flow:**
- `_build_prompt` receives `selected_stops` as a list and generates a text summary: "Stop 1: Lyon (FR, 2 nights, 280 km)"
- This is passed as a string in the prompt, which is used for backtracking prevention and distance calculations
- The model sees only a flat list — no information about overall trip theme, how the chosen stops relate to travel style, or what has already been covered

**Root cause:** History is summary-only (list of regions + nights + km). No semantic memory of: what categories of places were visited, what the architect recommended for subsequent stops, or what the user's style preferences actually produced.

### Gap 4: Budget/day tracking disconnected

**Current flow:**
- `segment_budget` tracks days for the current segment only
- `_calc_route_status` uses a single `min_nights_per_stop` constant for all occupancy estimates
- No running total of days-used vs days-remaining across the whole trip
- Day counter resets at segment boundaries

**Root cause:** Budget is segment-scoped, not trip-scoped. No per-stop day planning based on stop desirability.

### Gap 5: User wishes not consistently forwarded

**Current flow:**
- `travel_description` reaches: RouteArchitect (via `req.travel_description`), ActivitiesAgent
- `preferred_activities` reaches: ActivitiesAgent only
- `travel_styles` reaches: RouteArchitect, StopOptionsFinder (with emphasis block), ActivitiesAgent
- `mandatory_activities` reaches: RouteArchitect, ActivitiesAgent
- Gap: `travel_description` and `preferred_activities` do NOT reach StopOptionsFinder, RestaurantsAgent, DayPlannerAgent, TravelGuideAgent

**Root cause:** Each agent was built independently, selectively pulling from `TravelRequest`. No systematic "wishes forwarding" check was applied at build time.

### Gap 6: No recalculation when user changes nights or stops

**Current flow:**
- User can change `nights` on a stop via `prompt()` in the frontend (local state update only)
- No endpoint exists to recalculate DayPlannerAgent output after a change
- The `replan` endpoint (`/api/travels/{id}/replan`) re-runs full research, but that's expensive and not designed for incremental changes

**Root cause:** DayPlannerAgent is run once at the end of the pipeline. No lightweight re-trigger mechanism for day plan recalculation.

---

## Recommended Architecture Changes

### Component: `ArchitectPlan` in Job State

**New field in job state:** `"architect_plan": {...}`

Stores a lightweight pre-planning result before interactive stop selection begins. This is a NEW sub-step inserted into the interactive flow, not the existing Celery-path RouteArchitect.

```
POST /api/plan-trip
  ├── [NEW] Call RouteArchitectAgent (or lighter planning call)
  │   Returns: recommended regions, suggested nights per region, total stop count
  │   Stored in: job["architect_plan"]
  └── Then: StopOptionsFinder uses architect_plan as context
```

**Integration point:** `main.py` → `/api/plan-trip` handler, before calling `_find_and_stream_options`.

**What changes:**
- MODIFIED: `_new_job()` in `main.py` — add `architect_plan: None` field
- MODIFIED: `/api/plan-trip` handler in `main.py` — add architect pre-planning call
- MODIFIED: `StopOptionsFinderAgent._build_prompt()` — accept and use `architect_context` param
- MODIFIED: `_find_and_stream_options()` helper in `main.py` — pass architect context through
- NEW: Lightweight planning step (reuse RouteArchitectAgent with simplified prompt, or a new `trip_planner_mini.py` using Sonnet)

### Component: Intelligent Night Distribution

**Where it lives:** `_calc_leg_segment_budget()` and the night assignment in StopOptionsFinder.

**Approach B (prompt-only, recommended):** Extend StopOptionsFinder prompt to receive architect night recommendations as context. The model selects nights intelligently from that. No new data structure changes beyond `architect_plan` — only prompt expansion.

**Integration point:** `StopOptionsFinderAgent._build_prompt()`.

**What changes:**
- MODIFIED: `StopOptionsFinderAgent._build_prompt()` — add `nights_context` block derived from `architect_plan`
- MODIFIED: JSON output schema in StopOptionsFinder prompt — nights field becomes context-aware with explicit instructions

### Component: Stop History Context

**Current:** StopOptionsFinder receives `selected_stops` as a flat list, formatted as a string.

**Change:** Enrich the history context with:
1. List of stop names (existing)
2. List of covered travel style tags from `selected_stops[].tags`
3. Architect's remaining recommendations for subsequent stops (from `architect_plan`)

**Integration point:** `StopOptionsFinderAgent._build_prompt()`.

**What changes:**
- MODIFIED: `_build_prompt()` — generate a richer history block including tag coverage
- MODIFIED: prompt text — add explicit "do not repeat these place types" instruction derived from history
- NO new data structures required — all derived from existing `selected_stops` list at prompt build time

### Component: Wishes Forwarding Audit

**Missing connections to fix:**

| Field | Currently missing from |
|-------|----------------------|
| `travel_description` | StopOptionsFinder, RestaurantsAgent, DayPlannerAgent, TravelGuideAgent |
| `preferred_activities` | StopOptionsFinder, RestaurantsAgent |
| `mandatory_activities` | StopOptionsFinder |

**Integration points:** Each affected agent's prompt builder.

**What changes:**
- MODIFIED: `StopOptionsFinderAgent._build_prompt()` — add `preferred_activities`, `travel_description`, `mandatory_activities` blocks
- MODIFIED: `RestaurantsAgent` prompt — add `travel_description` and `preferred_activities`
- MODIFIED: `DayPlannerAgent` prompt — add `travel_description` (already has styles via req)
- MODIFIED: `TravelGuideAgent` prompt — add `travel_description`
- These are all prompt-only changes in existing agents — no structural changes

### Component: Global Wishes Field in Form

**New frontend field:** A free-text "Wünsche für die Reise" input on the form (step 2 or 4).

**What changes:**
- MODIFIED: `frontend/index.html` — add textarea for trip wishes
- MODIFIED: `frontend/js/form.js` → `buildPayload()` — map new field to `travel_description` (already exists in TravelRequest)
- NO backend changes required — `travel_description` already exists in TravelRequest and is stored/replayed correctly

### Component: Day Plan Recalculation

**Current:** DayPlannerAgent runs once in the Celery pipeline. No recalculate endpoint exists.

**New endpoint:** `POST /api/travels/{travel_id}/recalculate-days`

Accepts: updated nights per stop (optional body), or derives from current stop list.

Triggers: DayPlannerAgent call with existing research data (no re-research).

**Integration point:** New endpoint in `main.py`, new Celery task `tasks/recalculate_days.py`.

**What changes:**
- NEW: `backend/tasks/recalculate_days.py` — Celery task wrapping DayPlannerAgent.run()
- NEW: `POST /api/travels/{travel_id}/recalculate-days` endpoint in `main.py`
- MODIFIED: `frontend/js/guide/edit.js` — after nights change, call recalculate endpoint and refresh guide view
- The saved travel in SQLite is updated with the new day plan; all research data (activities, restaurants, guide text) is preserved

---

## Data Flow Changes

### New Interactive Planning Flow (with architect pre-planning)

```
POST /api/plan-trip
    │
    ▼
[NEW] Lightweight planning step (Sonnet, ~2s)
    │ Input: TravelRequest (full)
    │ Output: { recommended_stops: [{region, suggested_nights, notes}], style_rationale }
    │ Stored in: job["architect_plan"]
    ▼
StopOptionsFinderAgent._build_prompt()
    │ NEW inputs: architect_plan context, preferred_activities, travel_description
    │ NEW outputs: nights derived from architect plan, richer history block
    ▼
[unchanged] 3 options streamed to frontend
```

### Recalculation Flow (new)

```
Frontend: user changes nights on a stop
    │ POST /api/travels/{id}/recalculate-days
    │ Body: { stops: [{id, nights}] }
    ▼
Endpoint loads saved travel from SQLite
    │ Reconstructs TravelRequest + updated stops
    │ Loads existing activities/restaurants/accommodations (no re-research)
    ▼
Celery: recalculate_days_task
    │ DayPlannerAgent.run(route, accommodations, activities)
    │ SSE stream for progress
    ▼
SQLite: update travel with new day_plans
    │ Frontend receives job_complete event
    ▼
Frontend re-renders day tabs
```

### Context Forwarding (wishes)

```
TravelRequest.travel_description
    ├── RouteArchitect (existing)
    ├── StopOptionsFinder (NEW)
    ├── ActivitiesAgent (existing)
    ├── RestaurantsAgent (NEW)
    ├── DayPlannerAgent (NEW)
    └── TravelGuideAgent (NEW)

TravelRequest.preferred_activities
    ├── ActivitiesAgent (existing)
    ├── StopOptionsFinder (NEW)
    └── RestaurantsAgent (NEW)

TravelRequest.mandatory_activities
    ├── RouteArchitect (existing)
    ├── ActivitiesAgent (existing)
    └── StopOptionsFinder (NEW)
```

---

## Component Responsibilities

| Component | Responsibility | Changed by v1.2 |
|-----------|---------------|-----------------|
| `main.py` `/api/plan-trip` | Initiates interactive stop selection | YES — add architect pre-plan step |
| `main.py` `/api/select-stop` | Records stop selection, fetches next options | YES — passes architect context |
| `StopOptionsFinderAgent` | Suggests 3 stop options per position | YES — add architect/wishes/history context |
| `RouteArchitectAgent` | Plans full route (Celery path) | MAYBE — or new lightweight planner |
| `DayPlannerAgent` | Creates day-by-day schedule | YES — expose recalculate path |
| `ActivitiesAgent` | Researches activities per stop | NO |
| `RestaurantsAgent` | Researches restaurants per stop | YES — add wishes |
| `TravelGuideAgent` | Writes narrative guide per stop | YES — add travel_description |
| `TripAnalysisAgent` | Overall trip review | NO |
| `orchestrator.py` | Coordinates Celery pipeline | NO (architect pre-plan is interactive-path only) |
| `_new_job()` in main.py | Creates job state | YES — add `architect_plan` field |
| `frontend/form.js` | Builds trip request payload | YES — expose `travel_description` field |
| `frontend/guide/edit.js` | Handles nights/stop edits | YES — trigger recalculate after nights change |

---

## Build Order (Dependency-Aware)

### Phase 1: Context Infrastructure (prerequisite for everything)

**What:** Add `travel_description`, `preferred_activities`, `mandatory_activities` to StopOptionsFinder prompt. Add `travel_description` to RestaurantsAgent, DayPlannerAgent, TravelGuideAgent.

**Why first:** Zero structural changes. Pure prompt additions. All other improvements depend on consistent context flowing through the pipeline. Fast wins, immediately testable.

**Files:** `stop_options_finder.py`, `restaurants_agent.py`, `day_planner.py`, `travel_guide_agent.py`

**Risk:** LOW. Prompt-only changes. Worst case: slightly longer prompts, no regressions.

### Phase 2: Architect Pre-Plan for Interactive Flow

**What:** Before StopOptionsFinder runs the first time, call a lightweight planning step that produces a region/nights recommendation table. Store in `job["architect_plan"]`. Pass to all subsequent StopOptionsFinder calls.

**Why second:** Depends on Phase 1 having established the context-forwarding pattern. This is the most architecturally significant change — it adds a new async step to the critical path of `/api/plan-trip`.

**Files:** `main.py` (`_new_job`, `/api/plan-trip`, `/api/select-stop`), `stop_options_finder.py` (`_build_prompt`, `find_options`, `find_options_streaming`), new lightweight planning prompt

**Risk:** MEDIUM. Adds latency to `/api/plan-trip`. Must use Sonnet, not Opus. Must degrade gracefully if it fails (fallback to no architect context). Pre-plan runs in parallel with SSE connection setup.

### Phase 3: Night Distribution Intelligence

**What:** Use architect_plan nights recommendations in StopOptionsFinder's nights output. Add explicit nights guidance per region to prompt.

**Why third:** Depends on Phase 2 architect_plan being in job state.

**Files:** `stop_options_finder.py`, `main.py` (via-point night assignment)

**Risk:** LOW. Prompt change + reading from existing job state field.

### Phase 4: Day Plan Recalculation

**What:** New endpoint + Celery task for lightweight DayPlannerAgent re-run after nights/stops change. Frontend calls this after local nights edit.

**Why fourth:** Structurally independent of Phases 1-3. Can be built in parallel. Placed here because it requires a stable pipeline first.

**Files:** `tasks/recalculate_days.py` (new), `main.py` (new endpoint), `guide/edit.js`

**Risk:** MEDIUM. New Celery task registration required. Must handle SSE correctly for an update (not a full plan run). SQLite update path needs care to preserve research data.

### Phase 5: UI Fixes (Global Wishes Field, Map Focus, Stop Images, Tooltips)

**What:** Frontend-only changes. Add wishes textarea to form. Fix map initial focus. Fix stop image references. Add tooltips to edit buttons and nights-adjust button. Show all previous stops in stop selection view with zoom.

**Why last:** No backend dependency. Can be done incrementally without risk to pipeline.

**Files:** `index.html`, `form.js`, `route-builder.js`, `guide/map-sync.js`, `guide/stops.js`

**Risk:** LOW. UI-only.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Running RouteArchitect (Opus) in the Interactive Critical Path

**What people do:** Route the full Opus-level RouteArchitectAgent call through the interactive `/api/plan-trip` endpoint as the pre-planning step.

**Why it's wrong:** Opus calls take 5-15 seconds. The user is waiting for the first stop options to appear. A slow pre-plan step will make the UI feel broken. It also burns expensive tokens for a preliminary step.

**Do this instead:** Use a lightweight Sonnet call with a simplified prompt. The pre-plan only needs to output a region table and suggested nights — not a full optimized route with geometry. Consider running it in the background in parallel with the first StopOptionsFinder call and applying its context starting from stop 2.

### Anti-Pattern 2: Storing Full Stop Research in Job State

**What people do:** Cache activities/restaurants/guide data in Redis job state to avoid re-research during recalculation.

**Why it's wrong:** Redis job state has a 24h TTL. For recalculation of a saved travel (SQLite), the job state may no longer exist. The research data lives in the saved travel JSON in SQLite — use that.

**Do this instead:** For recalculate-days, load research data from the saved travel plan in SQLite, not from Redis job state.

### Anti-Pattern 3: Blocking SSE Connection During Pre-Plan Step

**What people do:** Open SSE, call architect pre-plan synchronously, then start streaming options.

**Why it's wrong:** SSE clients expect events quickly. A 5+ second silence before the first event can cause the client to assume the connection is dead and retry.

**Do this instead:** Fire a `planning_started` SSE event immediately. Run the pre-plan step asynchronously. Either stream partial options while pre-plan runs, or send a progress ping every 2-3 seconds.

### Anti-Pattern 4: Changing Nights Without Guarding Total Trip Days

**What people do:** Give StopOptionsFinder full freedom to set any nights value based on architect recommendations.

**Why it's wrong:** If architect suggests 5 nights for Paris but user's `max_nights_per_stop` is 3, or total nights across all stops exceeds `total_days`, the route breaks. The `_calc_route_status` budget logic depends on correct nights values.

**Do this instead:** Cap StopOptionsFinder's nights output at `min(suggested, req.max_nights_per_stop)`. Validate total nights on the server side after each selection. Keep budget validation in `_calc_route_status` as the authoritative guard.

---

## Integration Points Summary

| New Feature | Touch Point | Files |
|-------------|-------------|-------|
| Architect pre-plan | `plan-trip` endpoint | `main.py`, new prompt module |
| Architect context in StopFinder | `_build_prompt()` | `stop_options_finder.py` |
| Nights distribution | `_build_prompt()` nights block | `stop_options_finder.py` |
| History awareness | `_build_prompt()` history block | `stop_options_finder.py` |
| `travel_description` forwarding | Agent prompts | `stop_options_finder.py`, `restaurants_agent.py`, `day_planner.py`, `travel_guide_agent.py` |
| `preferred_activities` forwarding | Agent prompts | `stop_options_finder.py`, `restaurants_agent.py` |
| `mandatory_activities` forwarding | Agent prompts | `stop_options_finder.py` |
| Global wishes form field | Form UI + payload | `index.html`, `form.js` |
| Recalculate days endpoint | New endpoint + Celery task | `main.py`, `tasks/recalculate_days.py` |
| Frontend recalculate trigger | Nights edit handler | `guide/edit.js` |

---

## Sources

- Direct source reading: `backend/agents/stop_options_finder.py`, `backend/agents/route_architect.py`, `backend/orchestrator.py`, `backend/main.py` (all endpoints and job state), `backend/models/travel_request.py`, `frontend/js/form.js`
- Confidence: HIGH — all findings based on current codebase, no external documentation required

---

*Architecture research for: AI route planning pipeline improvements (v1.2)*
*Researched: 2026-03-28*
