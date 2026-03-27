# Architecture

**Analysis Date:** 2026-03-25

## System Overview

DetourAI is a full-stack AI-powered road trip planner. Users configure a trip via a multi-step form; specialized Claude AI agents collaboratively build the route, research accommodations/activities/restaurants, and produce a day-by-day travel guide. All long-running operations use Server-Sent Events (SSE) for real-time progress streaming.

**Pattern:** Monolithic backend with Celery task offloading. The system follows an interactive orchestration pattern where the user and AI agents collaborate step-by-step (not a single fire-and-forget job).

**Key Characteristics:**
- Multi-agent AI orchestration with 9 specialized Claude agents
- Interactive route building: user selects stops one-by-one from AI-generated options
- SSE-based real-time streaming from backend to frontend
- Redis for ephemeral job state (24h TTL), SQLite for persistent travel storage
- Celery workers for the final planning phase (research + day planning)
- JWT authentication with Argon2id password hashing

## Component Map

### FastAPI Backend (`backend/main.py`)
- **Responsibility:** HTTP API (40+ endpoints), SSE streaming, job lifecycle management, route geometry calculations
- **Key files:** `backend/main.py` (2600+ lines, the central hub)
- **Dependencies:** Redis, SQLite (via `utils/travel_db.py`), all agents, Celery tasks
- **Note:** `main.py` contains endpoint definitions, helper functions for route geometry, Google Directions enrichment, and the streaming option finder. It is the largest single file.

### Orchestrator (`backend/orchestrator.py`)
- **Responsibility:** Runs the full planning pipeline after route + accommodations are confirmed. Coordinates agents in sequence: route -> research (parallel) -> travel guide (parallel) -> day planner -> trip analysis.
- **Key files:** `backend/orchestrator.py`
- **Dependencies:** All agents, Redis (for job state), `debug_logger` (for SSE events)
- **Used by:** Celery task `run_planning_job`

### AI Agents (`backend/agents/`)
- **Responsibility:** Each agent handles one domain of travel planning via Claude API calls
- **Key files:**
  - `backend/agents/_client.py` — shared Anthropic client factory + model selection
  - `backend/agents/route_architect.py` — overall route planning (claude-opus-4-5)
  - `backend/agents/stop_options_finder.py` — generates 3 stop options per step (claude-sonnet-4-5)
  - `backend/agents/region_planner.py` — plans regions for "explore" mode legs (claude-opus-4-5)
  - `backend/agents/accommodation_researcher.py` — finds accommodation options (claude-sonnet-4-5)
  - `backend/agents/activities_agent.py` — researches activities per stop (claude-sonnet-4-5)
  - `backend/agents/restaurants_agent.py` — researches restaurants per stop (claude-sonnet-4-5)
  - `backend/agents/day_planner.py` — creates day-by-day schedule (claude-opus-4-5)
  - `backend/agents/travel_guide_agent.py` — writes narrative travel guide per stop (claude-sonnet-4-5)
  - `backend/agents/trip_analysis_agent.py` — analyzes completed plan quality (claude-sonnet-4-5)
  - `backend/agents/output_generator.py` — generates PDF/PPTX output (fpdf2 + python-pptx)
- **Pattern:** Every agent follows the same structure:
  1. Build a German-language system prompt + user prompt
  2. Call `call_with_retry()` which wraps `asyncio.to_thread(client.messages.create(...))`
  3. Parse response JSON via `parse_agent_json()`
  4. Log via `debug_logger.log()`
- **Dependencies:** `_client.py`, `retry_helper.py`, `json_parser.py`, `debug_logger.py`

### Celery Tasks (`backend/tasks/`)
- **Responsibility:** Background execution of long-running orchestration
- **Key files:**
  - `backend/tasks/__init__.py` — Celery app config (broker=Redis, backend=Redis)
  - `backend/tasks/run_planning_job.py` — runs `TravelPlannerOrchestrator.run()` in asyncio
  - `backend/tasks/prefetch_accommodations.py` — parallel accommodation fetching per stop
  - `backend/tasks/replace_stop_job.py` — replaces a single stop with full re-research
- **Pattern:** Each task wraps an async function in `asyncio.run()`. Events are pushed to Redis lists (`sse:{job_id}`) for the SSE endpoint to drain.

### Utilities (`backend/utils/`)
- **Key files:**
  - `backend/utils/debug_logger.py` — singleton `DebugLogger`, manages SSE subscriber queues + Redis pubsub + file logging
  - `backend/utils/maps_helper.py` — Google Maps Geocoding, Directions, Places APIs
  - `backend/utils/retry_helper.py` — `call_with_retry()` with exponential backoff for Anthropic 429/529
  - `backend/utils/json_parser.py` — `parse_agent_json()` strips markdown fences from agent output
  - `backend/utils/travel_db.py` — SQLite CRUD for saved travels (data/travels.db)
  - `backend/utils/auth.py` — JWT creation/validation, password hashing (Argon2id)
  - `backend/utils/auth_db.py` — user storage in SQLite
  - `backend/utils/settings_store.py` — SQLite key-value store for runtime settings
  - `backend/utils/image_fetcher.py` — Unsplash image fetching
  - `backend/utils/brave_search.py` — Brave Search API integration
  - `backend/utils/google_places.py` — Google Places API
  - `backend/utils/weather.py` — weather data
  - `backend/utils/wikipedia.py` — Wikipedia enrichment
  - `backend/utils/currency.py` — currency conversion
  - `backend/utils/migrations.py` — database schema migrations

### Frontend (`frontend/`)
- **Responsibility:** Vanilla JS SPA with client-side routing, no build step
- **Key files:**
  - `frontend/index.html` — single HTML page with all sections
  - `frontend/styles.css` — Apple-inspired design system
  - `frontend/js/state.js` — global `S` object, `esc()` XSS helper, localStorage layer
  - `frontend/js/api.js` — all `fetch()` calls + `openSSE()` helper, JWT token injection
  - `frontend/js/form.js` — 5-step trip configuration form
  - `frontend/js/route-builder.js` — interactive stop selection with SSE streaming
  - `frontend/js/accommodation.js` — parallel accommodation loading + selection
  - `frontend/js/progress.js` — SSE progress handlers, stops timeline
  - `frontend/js/guide.js` — travel guide tabs + render functions
  - `frontend/js/travels.js` — saved travels list + management
  - `frontend/js/router.js` — client-side routing via `history.pushState`
  - `frontend/js/auth.js` — login/logout, JWT token management
  - `frontend/js/sidebar.js` — sidebar navigation
  - `frontend/js/settings.js` — admin settings page
  - `frontend/js/maps.js` — Google Maps rendering
  - `frontend/js/loading.js` — loading overlay
  - `frontend/js/sse-overlay.js` — SSE progress overlay component
  - `frontend/js/types.d.ts` — auto-generated TypeScript definitions from OpenAPI

### Infrastructure (`infra/`)
- **Key files:**
  - `infra/Dockerfile.backend` — Python backend image
  - `infra/Dockerfile.frontend` — Nginx + static files image
  - `infra/nginx.conf` — reverse proxy config (static files + `/api/` proxy to backend)
  - `docker-compose.yml` — 4 services: redis, backend, celery, frontend

### Routers (`backend/routers/`)
- **Key files:**
  - `backend/routers/auth.py` — login, logout, token refresh, session endpoints
  - `backend/routers/admin.py` — admin-only endpoints (user management, quotas)

## Data Flow

### Trip Planning Lifecycle

The trip planning process is **interactive and multi-phase**, not a single background job:

**Phase 1: Route Building (interactive, synchronous)**
1. Frontend submits `TravelRequest` → `POST /api/plan-trip`
2. Backend creates job in Redis (`job:{id}`, TTL 24h)
3. `StopOptionsFinderAgent` generates 3 stop options
4. Each option is enriched with Google Directions (drive time/distance) and geocoded
5. Options are streamed as individual `route_option_ready` SSE events
6. User selects a stop → `POST /api/select-stop/{job_id}`
7. Process repeats until route is complete (days exhausted or user confirms)
8. User confirms route → `POST /api/confirm-route/{job_id}`

**Phase 1b: Explore Mode (for "explore" legs)**
1. `RegionPlannerAgent` generates a region plan with sub-regions
2. User reviews/modifies regions → `POST /api/confirm-regions/{job_id}`
3. Each region becomes a transit segment, building route interactively

**Phase 2: Accommodation Selection (parallel, interactive)**
1. `POST /api/start-accommodations/{job_id}` → fires Celery task `prefetch_accommodations_task`
2. `AccommodationResearcherAgent` finds 3 options per stop in parallel (Semaphore-limited)
3. Each stop's options are streamed via `accommodation_loaded` SSE events
4. User selects accommodation per stop
5. User confirms → `POST /api/confirm-accommodations/{job_id}`

**Phase 3: Full Planning (background, Celery)**
1. `POST /api/start-planning/{job_id}` → fires Celery task `run_planning_job_task`
2. `TravelPlannerOrchestrator.run()` executes:
   - Activities research (parallel, all stops)
   - Restaurant research (parallel, all stops)
   - Image fetching (parallel, all stops)
   - Travel guide writing (parallel, all stops)
   - Day planning (sequential, uses all data)
   - Trip analysis (sequential)
3. Progress streamed via SSE events: `stop_research_started`, `activities_loaded`, `restaurants_loaded`, `stop_done`, `job_complete`
4. Result saved to SQLite via `travel_db.save_travel()`

**Phase 4: Post-Planning (on-demand)**
- Replace individual stops: `POST /api/travels/{id}/replace-stop` → Celery task
- Replan trip: `POST /api/travels/{id}/replan`
- Generate PDF/PPTX: `POST /api/generate-output/{job_id}/{type}`

### SSE Event System

The SSE system bridges Celery workers (separate process) and the FastAPI SSE endpoint:

```
Celery Worker                    Redis                     FastAPI SSE Endpoint
     |                            |                              |
     |-- push_event() ---------->|  rpush(sse:{job_id}, event)  |
     |                            |                              |
     |                            |<--- lpop(sse:{job_id}) -----|  (_drain_redis)
     |                            |                              |
     |                            |              yield SSE event --> EventSource (browser)
```

- **In-process events** (when running without Celery): `debug_logger._local_push()` → `asyncio.Queue` → SSE generator
- **Cross-process events** (Celery workers): `debug_logger._redis_push()` → Redis list `sse:{job_id}` → SSE endpoint drains via `_drain_redis()`
- **Event types:** `debug_log`, `route_ready`, `route_option_ready`, `route_options_done`, `stop_done`, `stop_research_started`, `activities_loaded`, `restaurants_loaded`, `accommodation_loading`, `accommodation_loaded`, `accommodations_all_loaded`, `region_plan_ready`, `region_updated`, `leg_complete`, `replace_stop_progress`, `replace_stop_complete`, `job_complete`, `job_error`, `ping`

### Task Dispatch Pattern

`main.py` uses `_fire_task()` which adapts to the environment:
- **With Redis:** dispatches via Celery `.delay()` (separate worker process)
- **Without Redis:** runs as `asyncio.ensure_future()` in the same process (dev mode)

This enables local development without Redis/Celery.

## State Management

### Redis (ephemeral job state)
- **Key pattern:** `job:{job_id}` (hex UUID, 32 chars)
- **TTL:** 24 hours
- **Contains:** Full job state including request, selected stops, accommodations, options, leg tracking, route geometry cache, result
- **Job statuses:** `building_route` → `awaiting_region_confirmation` → `selecting_accommodations` → `running` → `complete` | `error`

### SQLite (persistent storage)
- **Travels DB:** `data/travels.db` — completed trip plans with full JSON, token usage
- **Auth DB:** `data/travels.db` (same file) — users table with Argon2id hashed passwords
- **Settings DB:** `data/settings.db` — key-value store for runtime configuration (agent models, budget defaults, API settings)
- **Schema migrations:** `backend/utils/migrations.py`

### Frontend State
- **In-memory:** Global `S` object in `frontend/js/state.js` — current step, job ID, selected stops, accommodations, results
- **localStorage:** Prefixed `tp_v1_*` keys for form data, route state, accommodations, result cache
- **URL state:** Client-side router (`frontend/js/router.js`) with pattern-matched routes like `/travel/{id}`, `/route-builder/{jobId}`, `/form/step/{n}`

### Authentication
- **JWT tokens:** 15-minute access tokens, httpOnly refresh cookies
- **Token flow:** Login → access token (in-memory) + refresh cookie → silent refresh on 401
- **SSE auth:** Token passed as query parameter (`?token=...`) since EventSource doesn't support headers
- **Password hashing:** Argon2id via passlib

## Entry Points

### FastAPI Application
- **Location:** `backend/main.py`
- **Start:** `python3 -m uvicorn main:app --reload --port 8000`
- **Lifespan:** `lifespan()` context manager starts periodic subscriber cleanup, cleans up HTTP sessions on shutdown

### Celery Worker
- **Location:** `backend/tasks/__init__.py` (app definition)
- **Start:** `celery -A tasks worker --loglevel=info --max-tasks-per-child=50`
- **Tasks registered:** `tasks.run_planning_job.run_planning_job_task`, `tasks.prefetch_accommodations.prefetch_accommodations_task`, `tasks.replace_stop_job.replace_stop_job_task`

### Nginx Frontend
- **Location:** `infra/nginx.conf`
- **Serves:** Static files from `/usr/share/nginx/html`, proxies `/api/` to `backend:8000`
- **SSE support:** `proxy_buffering off`, 600s timeout, chunked transfer encoding

### Frontend SPA
- **Location:** `frontend/index.html`
- **Router init:** `Router.init()` in `frontend/js/router.js` dispatches on `popstate` and initial load
- **Routes:** `/`, `/form/step/{n}`, `/route-builder/{jobId}`, `/accommodation/{jobId}`, `/progress/{jobId}`, `/travel/{id}`, `/travels`, `/settings`

## Error Handling

**Strategy:** Graceful degradation with German error messages

**Backend Patterns:**
- `call_with_retry()` handles Anthropic 429 (rate limit) and 529 (overloaded) with exponential backoff + jitter
- Orchestrator catches non-critical failures (trip analysis) and continues
- Job errors saved to Redis and pushed as `job_error` SSE event
- FastAPI validation errors return structured 422 responses
- All exceptions logged via `debug_logger` with job context

**Frontend Patterns:**
- `_fetchWithAuth()` auto-retries on 401 with silent token refresh
- `window.onerror` and `window.onunhandledrejection` report to backend via `POST /api/log`
- `esc()` function for XSS prevention on all user content
- `safeUrl()` blocks non-http(s) URLs

## Cross-Cutting Concerns

**Logging:**
- Centralized `DebugLogger` singleton (`backend/utils/debug_logger.py`)
- Dual output: file logging (daily rotation, 30-day retention) + SSE streaming
- Per-job verbosity levels: minimal, normal, verbose, debug
- Component-based log routing (each agent gets its own log file)
- Frontend errors reported via `POST /api/log` → `frontend/frontend.log`

**Validation:**
- Pydantic models for all API request/response boundaries
- `TravelRequest` validates leg chains (locations match, dates chain), budget percentages sum to 100
- Field validators on individual models (Child age 0-17, budget ranges, etc.)

**Authentication:**
- JWT-based with 15-minute access tokens
- `get_current_user` dependency on all protected endpoints
- `get_current_user_sse` for SSE endpoints (reads from query param)
- Admin bootstrap on startup from env vars

**Budget Calculation:**
- Configurable split: accommodation_pct / food_pct / activities_pct (must sum to 100)
- All prices in CHF
- Budget state tracked through accommodation selection phase

---

*Architecture analysis: 2026-03-25*
