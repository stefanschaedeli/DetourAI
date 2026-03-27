# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Full-stack AI-powered road trip planner. Users configure a trip in a 5-step form; specialized
Claude agents interactively build the route, research accommodations/activities/restaurants,
and produce a day-by-day travel guide. All communication uses Server-Sent Events (SSE) for
real-time progress streaming.

**Stack:** Python/FastAPI backend · Vanilla JS frontend · Redis job state · Celery workers ·
Nginx serving static files · Docker Compose deployment

---

## Build & Dev Commands

### Backend (FastAPI)
```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

### Frontend (static)
Open `frontend/index.html` directly, or let Nginx serve it via Docker.

### Docker (full stack)
```bash
docker compose up --build          # start everything
docker compose up -d               # background
docker compose down                # stop
docker compose logs -f backend     # follow backend logs
```

### Type Generation (OpenAPI → TypeScript)
```bash
cd scripts && ./generate-types.sh  # emits frontend/js/types.d.ts
```

### Tests
```bash
cd backend && python3 -m pytest tests/ -v
cd backend && python3 -m pytest tests/test_models.py        # Pydantic validation only
cd backend && python3 -m pytest tests/test_endpoints.py     # API routes
cd backend && python3 -m pytest tests/test_agents_mock.py   # agents with mocked Anthropic
cd backend && python3 -m pytest tests/test_travel_db.py     # travel persistence DB
```

### Dependencies
```bash
cd backend && pip3 install -r requirements.txt
```

---

## Project Architecture

```
DetourAI/
├── CLAUDE.md
├── docker-compose.yml
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── backend/
│   ├── main.py                          # FastAPI app, 25 endpoints
│   ├── orchestrator.py                  # TravelPlannerOrchestrator
│   ├── tasks/
│   │   ├── run_planning_job.py          # Celery task: full orchestration
│   │   ├── prefetch_accommodations.py   # Celery task: parallel acc fetch
│   │   └── replace_stop_job.py          # Celery task: stop replacement
│   ├── agents/
│   │   ├── _client.py                   # shared Anthropic client factory
│   │   ├── route_architect.py           # claude-opus-4-5
│   │   ├── stop_options_finder.py       # claude-sonnet-4-5
│   │   ├── region_planner.py            # claude-opus-4-5 (region route planning)
│   │   ├── accommodation_researcher.py  # claude-sonnet-4-5
│   │   ├── activities_agent.py          # claude-sonnet-4-5 + WikipediaEnricher
│   │   ├── restaurants_agent.py         # claude-sonnet-4-5
│   │   ├── day_planner.py               # claude-opus-4-5 + Google Directions
│   │   ├── travel_guide_agent.py        # claude-sonnet-4-5 (narrative guide)
│   │   └── trip_analysis_agent.py       # claude-sonnet-4-5 (replan analysis)
│   ├── models/
│   │   ├── travel_request.py            # TravelRequest Pydantic model
│   │   ├── travel_response.py           # TravelPlan, TravelStop, DayPlan, CostEstimate
│   │   ├── stop_option.py               # StopOption, StopOptionsResponse
│   │   ├── accommodation_option.py      # AccommodationOption, BudgetState
│   │   ├── trip_leg.py                  # TripLeg model
│   │   └── via_point.py                 # ViaPoint model
│   ├── utils/
│   │   ├── debug_logger.py              # Singleton DebugLogger, SSE subscriber manager
│   │   ├── maps_helper.py               # geocode_google(), google_directions(), build_maps_url()
│   │   ├── retry_helper.py              # call_with_retry() with exponential backoff
│   │   ├── json_parser.py               # parse_agent_json() strips markdown fences
│   │   ├── travel_db.py                 # SQLite persistence for saved travels
│   │   ├── hotel_price_fetcher.py       # hotel price scraping/fetching
│   │   ├── image_fetcher.py             # destination image fetching
│   │   ├── auth.py                      # authentication logic
│   │   ├── auth_db.py                   # authentication database
│   │   ├── brave_search.py              # Brave search integration
│   │   ├── currency.py                  # currency conversion
│   │   ├── google_places.py             # Google Places API
│   │   ├── migrations.py               # database migrations
│   │   ├── settings_store.py            # settings persistence
│   │   ├── weather.py                   # weather data fetching
│   │   └── wikipedia.py                 # Wikipedia enrichment
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_models.py               # 38 Pydantic validation tests
│   │   ├── test_endpoints.py            # 24 API route tests
│   │   ├── test_agents_mock.py          # 20 agent tests with mocked Anthropic
│   │   └── test_travel_db.py            # travel persistence tests
│   ├── .env                             # never commit
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── js/
│       ├── state.js         # S-object, TRAVEL_STYLES, FLAGS, localStorage layer
│       ├── api.js           # fetch wrappers + openSSE()
│       ├── form.js          # 5-step form, buildPayload(), tag-input, via-points
│       ├── route-builder.js # interactive stop selection
│       ├── accommodation.js # parallel acc loading + selection grid
│       ├── progress.js      # SSE progress handlers, stops timeline
│       ├── guide.js         # travel guide tabs + render functions
│       ├── travels.js       # saved travels list + management
│       ├── maps.js          # map rendering helpers
│       ├── loading.js       # loading state UI
│       ├── sse-overlay.js   # SSE progress overlay component
│       ├── auth.js          # authentication / access control
│       ├── router.js        # client-side routing
│       ├── sidebar.js       # sidebar navigation component
│       ├── settings.js      # settings page / preferences
│       └── types.d.ts       # generated from OpenAPI — do not edit manually
├── DESIGN_GUIDELINE.md              # Apple-inspired design system
├── scripts/
│   └── generate-types.sh
```

---

## Critical Rules

- **Never commit `.env`** — use `.env.example` as template
- **Agents always return valid JSON** — no markdown wrappers, no explanations
- **All user-facing text in German** — error messages, log entries, UI labels
- **Prices always in CHF**
- **TEST_MODE=true** → all agents use `claude-haiku-4-5` (cheap dev mode)
- **TEST_MODE=false** → Opus for route+planner, Sonnet for research
- **Job state in Redis** — key pattern `job:{job_id}`, TTL 24h
- **SSE stream closes** on `job_complete` or `job_error` event
- **Budget split:** 45% accommodation · 15% food · ~CHF 80/stop activities · CHF 12/h fuel
- **Google Maps APIs** for Geocoding, Directions, Places — `GOOGLE_MAPS_API_KEY` env var required
- **Frontend API prefix:** `/api` (Nginx proxy to backend:8000) — never use `localhost:8000` in JS

---

## Agent Model Assignments

| Agent | Production | Test (TEST_MODE=true) |
|-------|-----------|----------------------|
| RouteArchitectAgent | claude-opus-4-5 | claude-haiku-4-5 |
| StopOptionsFinderAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RegionPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |
| AccommodationResearcherAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |
| TravelGuideAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| TripAnalysisAgent | claude-sonnet-4-5 | claude-haiku-4-5 |

---

## Code Conventions

### Python
- Type hints on all function signatures
- Pydantic models for all API boundaries
- `async/await` throughout; blocking SDK calls wrapped in `asyncio.to_thread()`
- All Claude calls go through `call_with_retry()` (handles 429 with exponential backoff)
- Agent JSON parsing via `parse_agent_json()` (strips markdown fences if present)
- Log every API call with `debug_logger.log(LogLevel.API, ...)` before calling

### JavaScript
- Vanilla ES2020, no build step, no frameworks
- Global state in `S` object (state.js)
- API calls in api.js only — no `fetch()` calls outside api.js
- `esc()` for all user-content interpolation into HTML (XSS prevention)
- localStorage keys prefixed `tp_v1_*`

### File-Based Logging (REQUIRED for new code)

All backend code **must** use the centralized file-logging system in `utils/debug_logger.py`.
Log files are written to `backend/logs/` with daily rotation (30-day retention).

**When adding a new agent or backend component:**
1. Add an entry to `_COMPONENT_MAP` in `debug_logger.py`:
   ```python
   "NewAgentName": "agents/new_agent",
   ```
2. Use `debug_logger.log(LogLevel.X, "message", job_id=self.job_id, agent="NewAgentName")`
   for all log calls — the `agent` parameter routes the message to the correct log file.
3. Use appropriate `LogLevel`:
   - `ERROR` / `WARNING` — problems (always logged)
   - `INFO` / `SUCCESS` / `AGENT` — normal flow (logged at Normal+)
   - `API` — external API calls (logged at Verbose+)
   - `DEBUG` / `PROMPT` — detailed debug info (logged at Debug only)
4. For prompt logging: `debug_logger.log_prompt(agent, model, prompt, job_id=job_id)`

**Log file structure:**
```
backend/logs/
  agents/<agent_name>.log      — one file per agent
  orchestrator/orchestrator.log — orchestration flow
  api/api.log                  — general API / endpoint logs
  frontend/frontend.log        — errors reported by the browser
```

**Frontend error reporting:**
- All `console.error()` calls in JS should also call `apiLogError('error', msg, source, stack)`
  (defined in `api.js`) to persist errors in `frontend/frontend.log`.
- `window.onerror` and `window.onunhandledrejection` already auto-report to backend.

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...     # required
GOOGLE_MAPS_API_KEY=...          # required — Geocoding, Directions, Places APIs
TEST_MODE=true                   # true=haiku, false=opus/sonnet
REDIS_URL=redis://localhost:6379 # job state store
LOGS_DIR=/app/logs               # file logging dir (default: backend/logs/)
```

---

## Local API Debugging (for Claude Code)

All API endpoints require JWT authentication. To call protected endpoints locally:

```bash
# Token generieren (15 Min gültig, kein laufender Server nötig)
TOKEN=$(cd /Users/stefan/Code/Travelman3 && python3 scripts/dev-token.py)

# Geschützte Endpoints aufrufen
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/auth/me
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/travels

# SSE-Endpoints mit Query-Parameter
curl -s "http://localhost:8000/api/progress/{job_id}/stream?token=$TOKEN"
```

- Bei 401-Fehler: Token neu generieren (gleicher Befehl)
- Das Script liest `JWT_SECRET` aus `backend/.env` — kein DB-Zugriff nötig
- Öffentliche Endpoints ohne Token: `/health`, `/api/maps-config`, `/api/log`

---

## Testing Standards

- **test_models.py:** Pydantic validation — valid inputs, invalid inputs, edge cases
- **test_endpoints.py:** FastAPI TestClient — all endpoints, happy path + error cases
- **test_agents_mock.py:** Mock `anthropic.Anthropic` — verify prompt structure, JSON parsing, retry logic
- **test_travel_db.py:** SQLite travel persistence — CRUD operations and data integrity
- Target: all critical paths covered; agents testable without API keys

---

## Test Trip (for development)
- Start: Liestal, Schweiz
- Destination: Französische Alpen → Paris
- Duration: 10 days, 2 adults, CHF 5'000
- Max drive time/day: 4.5h

---

## Git Workflow (REQUIRED)
After **every** change, commit immediately as a patch release and push:

```bash
git add <changed files>
git commit -m "type: beschreibung"
git tag vX.X.Y        # increment patch number from latest tag
git push && git push --tags
```

- Version scheme: `x.x.y` — only increment `y` for each change
- Check current version with `git tag --sort=-v:refname | head -1`
- Commit message in German, type prefix in English (fix/feat/perf/docs/refactor)

<!-- GSD:project-start source:PROJECT.md -->
## Project

**DetourAI**

AI-powered road trip planner for friends and family. Users configure a trip (start, destination, duration, budget, travel style), then specialized Claude agents collaboratively build the route, research accommodations/activities/restaurants, and produce a day-by-day travel guide. Real-time progress via SSE. Currently deployed via Docker Compose with FastAPI backend and vanilla JS frontend.

**Core Value:** Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type — mainland, coastal, and island regions alike.

### Constraints

- **Stack**: Python/FastAPI backend, vanilla JS frontend — no framework migration
- **Deployment**: Docker Compose on TrueNAS — must stay containerized
- **AI Provider**: Anthropic Claude — all agents use claude-opus-4-5/claude-sonnet-4-5
- **Maps**: Google Maps APIs — geocoding, directions, places
- **Budget**: Personal project — optimize AI token costs (TEST_MODE=true for dev)
- **Language**: All user-facing text in German, prices in CHF
- **Auth**: JWT-based, existing system stays
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - Backend (FastAPI, agents, orchestrator, Celery workers)
- JavaScript ES2020 - Frontend (vanilla, no build step, no framework)
- HTML/CSS - Frontend UI (`frontend/index.html`, `frontend/styles.css`)
## Runtime
- Python 3.11 (pinned in `infra/Dockerfile.backend` via `python:3.11-slim`)
- Node.js is NOT used - frontend is plain JS served as static files
- pip (Python) - `backend/requirements.txt`
- Lockfile: Not present (no `requirements.lock` or `Pipfile.lock`)
- No npm/yarn - frontend has zero build dependencies
## Frameworks
- FastAPI >=0.111.0 - HTTP API framework (`backend/main.py`)
- Pydantic >=2.7.0 - Data validation for all API boundaries (`backend/models/`)
- Celery >=5.4.0 - Async task queue for long-running planning jobs (`backend/tasks/`)
- sse-starlette >=1.8.2 - Server-Sent Events for real-time progress streaming
- pytest >=8.0.0 - Test runner (`backend/tests/`)
- pytest-mock >=3.12.0 - Mocking support
- pytest-asyncio >=0.23.0 - Async test support
- httpx >=0.27.0 - FastAPI TestClient HTTP transport
- uvicorn[standard] >=0.29.0 - ASGI server
- Docker + Docker Compose 3.9 - Containerization (`docker-compose.yml`)
- Nginx (alpine) - Static file serving + reverse proxy (`infra/nginx.conf`)
## Key Dependencies
- anthropic >=0.28.0 - Claude AI SDK for all 9 planning agents (`backend/agents/_client.py`)
- aiohttp >=3.9.5 - Async HTTP client for all external API calls (`backend/utils/http_session.py`)
- redis >=5.0.4 - Job state storage, Celery broker (`backend/main.py`)
- PyJWT >=2.8.0 - JWT token creation/validation (`backend/utils/auth.py`)
- passlib[argon2] >=1.7.4 - Argon2id password hashing (`backend/utils/auth.py`)
- python-dotenv >=1.0.1 - Environment variable loading from `.env`
## Data & Storage
- SQLite - Application data (travels, users, settings)
- Redis 7 (Alpine) - Job state store + Celery message broker
- Geocode cache: OrderedDict, max 2000 entries, FIFO eviction (`backend/utils/maps_helper.py`)
- Currency rate cache: 24h TTL per currency (`backend/utils/currency.py`)
- Settings cache: 60s TTL (`backend/utils/settings_store.py`)
## Configuration
- `.env` file loaded via python-dotenv at startup (`backend/main.py`)
- `.env.example` provides template - never commit `.env`
- Key vars: `ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`, `JWT_SECRET`, `REDIS_URL`, `TEST_MODE`
- See INTEGRATIONS.md for full env var reference
- `docker-compose.yml` - 4 services: redis, backend, celery, frontend
- `infra/Dockerfile.backend` - Python 3.11-slim, non-root user (uid 568)
- `infra/Dockerfile.frontend` - nginx-unprivileged:alpine, static file copy
- `infra/nginx.conf` - Reverse proxy `/api/` to `backend:8000`, SSE support (600s timeout)
- SQLite-based settings store with defaults, validation ranges, and model allowlists
- Configurable per-agent: model selection, max_tokens
- Configurable: budget percentages, API timeouts, retry counts
- All defaults defined in `backend/utils/settings_store.py` `DEFAULTS` dict
## Infrastructure
- Docker Compose 3.9 with 4 services
- Services: `redis`, `backend`, `celery` (shared image), `frontend`
- Health checks on redis (ping), backend (HTTP /health)
- Celery worker limits: `--max-tasks-per-child=50 --max-memory-per-child=512000`
- Frontend exposed on port 80 (mapped to nginx 8080)
- Backend internal on port 8000 (not directly exposed)
- Redis internal on port 6379 (also mapped to host for local dev)
- Nginx proxies `/api/` to backend with SSE buffering disabled
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `server_tokens off`
## HTTP Client
- Single `aiohttp.ClientSession` with connection pooling (`backend/utils/http_session.py`)
- Connector: 100 total connections, 10 per host
- Lazy-initialized, shared across FastAPI and Celery workers
- All external API calls route through `get_session()`
## Platform Requirements
- Python 3.11+
- Redis (optional - falls back to in-memory store)
- Google Maps API key (Geocoding, Directions, Places APIs enabled)
- Anthropic API key
- Run: `cd backend && python3 -m uvicorn main:app --reload --port 8000`
- Docker + Docker Compose
- All env vars set (see `.env.example`)
- `COOKIE_SECURE=true` for HTTPS
- `TEST_MODE=false` for production Claude models
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- snake_case for all modules: `route_architect.py`, `travel_request.py`, `debug_logger.py`
- Agent modules match their class name in snake_case: `AccommodationResearcherAgent` lives in `accommodation_researcher.py`
- Utility modules are descriptive nouns: `retry_helper.py`, `json_parser.py`, `maps_helper.py`
- Private/internal prefixed with underscore: `_client.py` (shared Anthropic client factory)
- PascalCase for all classes: `TravelRequest`, `RouteArchitectAgent`, `DebugLogger`
- Agent classes suffixed with `Agent`: `RouteArchitectAgent`, `AccommodationResearcherAgent`, `DayPlannerAgent`
- Pydantic models are plain nouns: `TravelStop`, `CostEstimate`, `BudgetState`, `StopOption`
- Request/Response models suffixed accordingly: `StopSelectRequest`, `AccommodationResearchRequest`
- snake_case throughout: `find_options()`, `build_maps_url()`, `parse_agent_json()`
- Private methods prefixed with underscore: `_build_booking_url()`, `_get_conn()`, `_init_db()`
- Async methods use same naming (no special prefix): `async def run()`, `async def find_options()`
- Sync DB helpers prefixed `_sync_`: `_sync_save()`, `_sync_list()`, `_sync_get()`, `_sync_delete()` in `utils/travel_db.py`
- snake_case: `job_id`, `token_accumulator`, `budget_per_night`
- Constants are UPPER_SNAKE_CASE: `REDIS_URL`, `SYSTEM_PROMPT`, `AGENT_KEY`
- Module-level maps use UPPER_SNAKE_CASE: `VERBOSITY_FILTER`, `_COMPONENT_MAP` (private constant)
- kebab-case: `route-builder.js`, `sse-overlay.js`, `travel-guide.js`
- Exception: `state.js`, `api.js`, `form.js` (single-word names)
- camelCase: `goToStep()`, `showTravelGuide()`, `renderGuide()`, `buildPayload()`
- Private/internal prefixed with underscore: `_fetchWithAuth()`, `_authHeader()`, `_initGuideMap()`
- API wrappers prefixed `api`: `apiLogin()`, `apiLogout()`, `apiGetMe()`, `apiLogError()`
- camelCase for locals and state: `activeTab`, `selectedStops`, `loadingOptions`
- Global state object is single letter `S` (defined in `state.js`)
- Constants are UPPER_CASE: `API`, `TRAVEL_STYLES`, `FLAGS`
- Private module-level vars prefixed with underscore: `_guideMarkers`, `_guidePolyline`, `_activeStopId`
- kebab-case: `form-step`, `step-indicator`, `flag-badge`, `guide-tab`, `guide-content`
## Code Patterns
### Agent Pattern (Backend)
### Error Handling
- HTTP errors use FastAPI's `HTTPException` with German detail messages:
- Rate limits handled by `call_with_retry()` with exponential backoff (`utils/retry_helper.py`)
- Truncated JSON from Claude detected by brace counting in `parse_agent_json()` (`utils/json_parser.py`)
- Agent errors logged with `LogLevel.ERROR` and re-raised
- `_fetch()` wrapper in `api.js` throws `Error` with `HTTP {status}: {detail}` format
- 401 responses trigger one silent token refresh attempt before throwing
- `window.onerror` and `window.onunhandledrejection` auto-report errors to backend via `apiLogError()`
- User-content HTML interpolation uses `esc()` function for XSS prevention
### Logging
| Level | When to use |
|-------|------------|
| `ERROR` / `WARNING` | Problems (always logged) |
| `INFO` / `SUCCESS` / `AGENT` | Normal flow (logged at Normal+) |
| `API` | External API calls (logged at Verbose+) |
| `DEBUG` / `PROMPT` | Detailed debug info (logged at Debug only) |
### API Response Formats
### Common Abstractions
- **`call_with_retry(fn, ...)`** (`utils/retry_helper.py`): Wraps blocking Anthropic calls with exponential backoff on 429/529
- **`parse_agent_json(text)`** (`utils/json_parser.py`): Strips markdown fences, detects truncation
- **`get_client()`** / **`get_model(prod, key)`** (`agents/_client.py`): Anthropic client factory + TEST_MODE model switching
- **`_InMemoryStore`** (`main.py`): Drop-in Redis replacement for local dev without Redis
- **`_fire_task(name, job_id)`** (`main.py`): Dispatches Celery tasks or inline asyncio fallback
## Style & Formatting
- Python: 4 spaces
- JavaScript: 2 spaces
- HTML/CSS: 2 spaces
- No enforced limit (no linting config detected)
- Practical convention: ~100-120 chars, but long strings/prompts are not wrapped
- None detected (no `.eslintrc`, `.prettierrc`, `.flake8`, `pyproject.toml` with tool config, or `biome.json`)
- Code style is enforced by convention only
- No import system; all JS files loaded via `<script>` tags in `index.html`
- Files rely on globals (`S`, `API`, `esc()`, etc.) being available from previously loaded scripts
- Load order matters (e.g., `state.js` before `api.js` before `form.js`)
- Python: `sys.path.insert(0, ...)` used in test files to add backend to path
- No Python package structure (`__init__.py` files are empty)
- JavaScript: No path aliases; direct `<script src="js/file.js">` loading
## Language
- Error messages: `"Reise nicht gefunden"`, `"Sitzung abgelaufen"`
- Log messages: `"RouteArchitect startet"`, `"Rate limit — retry in..."`
- System prompts to Claude: `"Du bist ein Reiseplaner..."`
- UI labels in HTML/JS: `"Anfrage läuft…"`, `"Zurück zu Schritt {n}"`
- **Prices always in CHF**
- Variable/function names, class names, module names are English
- Exception: some domain terms kept in German when they are product concepts (e.g., `is_geheimtipp`, `geheimtipp_hinweis`)
## Documentation
- Used sparingly; not required on all functions
- When present, single-line format preferred:
- Module-level docstrings present on some files:
- Section dividers using `# ---------------------------------------------------------------------------`
- Inline comments for non-obvious logic
- German and English mixed in comments (German for domain, English for technical)
- Required on all function signatures (per CLAUDE.md convention)
- Pydantic models handle validation at API boundaries
- `Optional[X]` used for nullable fields
- `List[X]` from `typing` (not `list[X]` builtin syntax)
## Pydantic Model Conventions
## Frontend State Management
- All mutable app state lives on `S`
- Accessed globally from all JS modules
- LocalStorage keys prefixed `tp_v1_*`
- No reactivity system; UI updates are imperative DOM manipulation
- Never use `fetch()` directly outside `api.js`
- Use `_fetch()` for requests with loading overlay
- Use `_fetchQuiet()` for background requests (skeleton cards provide feedback)
- All requests go through `_fetchWithAuth()` which injects Bearer tokens
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
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
- **Pattern:** Every agent follows the same structure:
- **Dependencies:** `_client.py`, `retry_helper.py`, `json_parser.py`, `debug_logger.py`
### Celery Tasks (`backend/tasks/`)
- **Responsibility:** Background execution of long-running orchestration
- **Key files:**
- **Pattern:** Each task wraps an async function in `asyncio.run()`. Events are pushed to Redis lists (`sse:{job_id}`) for the SSE endpoint to drain.
### Utilities (`backend/utils/`)
- **Key files:**
### Frontend (`frontend/`)
- **Responsibility:** Vanilla JS SPA with client-side routing, no build step
- **Key files:**
### Infrastructure (`infra/`)
- **Key files:**
### Routers (`backend/routers/`)
- **Key files:**
## Data Flow
### Trip Planning Lifecycle
- Replace individual stops: `POST /api/travels/{id}/replace-stop` → Celery task
- Replan trip: `POST /api/travels/{id}/replan`
### SSE Event System
```
```
- **In-process events** (when running without Celery): `debug_logger._local_push()` → `asyncio.Queue` → SSE generator
- **Cross-process events** (Celery workers): `debug_logger._redis_push()` → Redis list `sse:{job_id}` → SSE endpoint drains via `_drain_redis()`
- **Event types:** `debug_log`, `route_ready`, `route_option_ready`, `route_options_done`, `stop_done`, `stop_research_started`, `activities_loaded`, `restaurants_loaded`, `accommodation_loading`, `accommodation_loaded`, `accommodations_all_loaded`, `region_plan_ready`, `region_updated`, `leg_complete`, `replace_stop_progress`, `replace_stop_complete`, `job_complete`, `job_error`, `ping`
### Task Dispatch Pattern
- **With Redis:** dispatches via Celery `.delay()` (separate worker process)
- **Without Redis:** runs as `asyncio.ensure_future()` in the same process (dev mode)
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
- `call_with_retry()` handles Anthropic 429 (rate limit) and 529 (overloaded) with exponential backoff + jitter
- Orchestrator catches non-critical failures (trip analysis) and continues
- Job errors saved to Redis and pushed as `job_error` SSE event
- FastAPI validation errors return structured 422 responses
- All exceptions logged via `debug_logger` with job context
- `_fetchWithAuth()` auto-retries on 401 with silent token refresh
- `window.onerror` and `window.onunhandledrejection` report to backend via `POST /api/log`
- `esc()` function for XSS prevention on all user content
- `safeUrl()` blocks non-http(s) URLs
## Cross-Cutting Concerns
- Centralized `DebugLogger` singleton (`backend/utils/debug_logger.py`)
- Dual output: file logging (daily rotation, 30-day retention) + SSE streaming
- Per-job verbosity levels: minimal, normal, verbose, debug
- Component-based log routing (each agent gets its own log file)
- Frontend errors reported via `POST /api/log` → `frontend/frontend.log`
- Pydantic models for all API request/response boundaries
- `TravelRequest` validates leg chains (locations match, dates chain), budget percentages sum to 100
- Field validators on individual models (Child age 0-17, budget ranges, etc.)
- JWT-based with 15-minute access tokens
- `get_current_user` dependency on all protected endpoints
- `get_current_user_sse` for SSE endpoints (reads from query param)
- Admin bootstrap on startup from env vars
- Configurable split: accommodation_pct / food_pct / activities_pct (must sum to 100)
- All prices in CHF
- Budget state tracked through accommodation selection phase
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
