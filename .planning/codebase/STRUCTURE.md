# Codebase Structure

**Analysis Date:** 2026-03-25

## Directory Layout

```
DetourAI/
├── backend/                     # Python FastAPI backend
│   ├── main.py                  # FastAPI app, 40+ endpoints, route geometry helpers
│   ├── orchestrator.py          # TravelPlannerOrchestrator — agent pipeline coordinator
│   ├── agents/                  # 9 AI agents + output generator
│   │   ├── _client.py           # Shared Anthropic client factory + model selection
│   │   ├── route_architect.py   # Route planning (opus)
│   │   ├── stop_options_finder.py # Stop option generation (sonnet)
│   │   ├── region_planner.py    # Explore-mode region planning (opus)
│   │   ├── accommodation_researcher.py # Accommodation search (sonnet)
│   │   ├── activities_agent.py  # Activity research (sonnet)
│   │   ├── restaurants_agent.py # Restaurant research (sonnet)
│   │   ├── day_planner.py       # Day-by-day schedule (opus)
│   │   ├── travel_guide_agent.py # Narrative travel guide (sonnet)
│   │   ├── trip_analysis_agent.py # Plan quality analysis (sonnet)
│   │   └── output_generator.py  # PDF/PPTX generation
│   ├── models/                  # Pydantic models for API boundaries
│   │   ├── travel_request.py    # TravelRequest (input)
│   │   ├── travel_response.py   # TravelPlan, TravelStop, DayPlan, CostEstimate (output)
│   │   ├── stop_option.py       # StopOption, StopSelectRequest
│   │   ├── accommodation_option.py # AccommodationOption, BudgetState
│   │   ├── trip_leg.py          # TripLeg, RegionPlan models
│   │   └── via_point.py         # ViaPoint model
│   ├── tasks/                   # Celery background tasks
│   │   ├── __init__.py          # Celery app configuration
│   │   ├── run_planning_job.py  # Full planning orchestration task
│   │   ├── prefetch_accommodations.py # Parallel accommodation fetch task
│   │   └── replace_stop_job.py  # Stop replacement task
│   ├── routers/                 # FastAPI sub-routers
│   │   ├── auth.py              # Login, logout, refresh, session endpoints
│   │   └── admin.py             # Admin-only endpoints (users, quotas)
│   ├── utils/                   # Shared utilities
│   │   ├── debug_logger.py      # Centralized logging + SSE event system
│   │   ├── maps_helper.py       # Google Maps API wrappers
│   │   ├── retry_helper.py      # Anthropic API retry with backoff
│   │   ├── json_parser.py       # Agent JSON response parser
│   │   ├── travel_db.py         # SQLite CRUD for saved travels
│   │   ├── auth.py              # JWT + password hashing
│   │   ├── auth_db.py           # User storage SQLite
│   │   ├── settings_store.py    # Runtime settings key-value store
│   │   ├── image_fetcher.py     # Unsplash image fetching
│   │   ├── brave_search.py      # Brave Search API
│   │   ├── google_places.py     # Google Places API
│   │   ├── hotel_price_fetcher.py # Hotel price data
│   │   ├── weather.py           # Weather data fetching
│   │   ├── wikipedia.py         # Wikipedia enrichment
│   │   ├── currency.py          # Currency conversion
│   │   ├── http_session.py      # Shared aiohttp session
│   │   └── migrations.py        # Database schema migrations
│   ├── tests/                   # pytest test suite
│   │   ├── conftest.py          # Shared fixtures
│   │   ├── test_models.py       # Pydantic model validation (38 tests)
│   │   ├── test_endpoints.py    # API endpoint tests (24 tests)
│   │   ├── test_agents_mock.py  # Agent tests with mocked Anthropic (20 tests)
│   │   └── test_travel_db.py    # Travel DB persistence tests
│   ├── logs/                    # Runtime log files (daily rotation)
│   ├── requirements.txt         # Python dependencies
│   ├── .env                     # Environment variables (never commit)
│   └── .env.example             # Environment variable template
├── frontend/                    # Vanilla JS SPA (no build step)
│   ├── index.html               # Single HTML page with all sections
│   ├── styles.css               # Complete CSS (Apple-inspired design system)
│   └── js/                      # JavaScript modules
│       ├── state.js             # Global S object, esc(), localStorage, lightbox
│       ├── api.js               # All fetch() calls, openSSE(), JWT injection
│       ├── form.js              # 5-step trip configuration form
│       ├── route-builder.js     # Interactive stop selection UI + SSE
│       ├── accommodation.js     # Accommodation selection UI + SSE
│       ├── progress.js          # Planning progress UI + SSE handlers
│       ├── guide.js             # Travel guide result rendering
│       ├── travels.js           # Saved travels list/management
│       ├── router.js            # Client-side URL routing
│       ├── auth.js              # Login/logout, token management
│       ├── sidebar.js           # Sidebar navigation
│       ├── settings.js          # Admin settings page
│       ├── maps.js              # Google Maps rendering
│       ├── loading.js           # Loading overlay
│       ├── sse-overlay.js       # SSE progress overlay component
│       └── types.d.ts           # Auto-generated TypeScript definitions
├── infra/                       # Docker & deployment config
│   ├── Dockerfile.backend       # Python backend image
│   ├── Dockerfile.frontend      # Nginx + static files image
│   └── nginx.conf               # Nginx reverse proxy config
├── scripts/                     # Development scripts
│   ├── generate-types.sh        # OpenAPI → TypeScript type generation
│   └── dev-token.py             # Generate dev JWT token for local API debugging
├── outputs/                     # Generated PDF/PPTX files
├── docker-compose.yml           # 4 services: redis, backend, celery, frontend
├── CLAUDE.md                    # AI assistant instructions
└── DESIGN_GUIDELINE.md          # Apple-inspired design system spec
```

## Directory Purposes

### `backend/agents/`
- **Purpose:** AI agent implementations, one per planning domain
- **Contains:** Python classes, each with a `run()` or domain-specific method
- **Key pattern:** All agents import from `_client.py`, use `call_with_retry()`, return parsed JSON dicts
- **File naming:** `snake_case.py` matching the agent's domain

### `backend/models/`
- **Purpose:** Pydantic models for API request/response validation
- **Contains:** Pydantic BaseModel subclasses with field validators
- **Key files:** `travel_request.py` (input), `travel_response.py` (output), `trip_leg.py` (leg/region models)

### `backend/tasks/`
- **Purpose:** Celery background tasks for long-running operations
- **Contains:** Task functions decorated with `@celery_app.task`, each wrapping an async function in `asyncio.run()`
- **Pattern:** Each task file has a private `async _run_*()` function + a public synchronous task wrapper

### `backend/utils/`
- **Purpose:** Shared utility modules used across agents, endpoints, and tasks
- **Contains:** Database access, API helpers, logging, auth, external service integrations
- **Key pattern:** Most utils are module-level functions (not classes), imported directly

### `backend/routers/`
- **Purpose:** FastAPI sub-routers for cleanly separated endpoint groups
- **Contains:** Auth and admin routers, included in main app via `app.include_router()`

### `backend/tests/`
- **Purpose:** pytest test suite
- **Contains:** Test modules organized by test target (models, endpoints, agents, DB)
- **Run:** `cd backend && python3 -m pytest tests/ -v`

### `frontend/js/`
- **Purpose:** Modular vanilla JavaScript, each file handles one UI concern
- **Contains:** ES2020 modules loaded via `<script>` tags (no import/export, global scope)
- **Key pattern:** Global functions, global `S` state object, all API calls through `api.js`

### `infra/`
- **Purpose:** Docker build files and Nginx configuration
- **Contains:** Two Dockerfiles (backend, frontend) and nginx.conf

### `outputs/`
- **Purpose:** Generated PDF and PPTX travel documents
- **Generated:** Yes (at runtime)
- **Committed:** No (empty directory, files created on demand)

## Key File Locations

### Entry Points
- `backend/main.py`: FastAPI application, all API endpoints
- `backend/tasks/__init__.py`: Celery app definition
- `frontend/index.html`: SPA entry point
- `frontend/js/router.js`: Client-side routing init

### Configuration
- `backend/.env` / `backend/.env.example`: Environment variables (API keys, Redis URL, JWT secret)
- `docker-compose.yml`: Service definitions, environment variable passthrough
- `infra/nginx.conf`: Reverse proxy and SSE settings
- `backend/utils/settings_store.py`: Runtime settings with defaults (agent models, budget, API config)

### Core Logic
- `backend/orchestrator.py`: Planning pipeline coordinator
- `backend/main.py` (lines 670-946): `_find_and_stream_options()` — the streaming stop finder
- `backend/main.py` (lines 478-548): `_calc_route_geometry()` — route geometry calculation
- `backend/agents/_client.py`: Model selection logic (test mode vs production)

### Data Layer
- `backend/utils/travel_db.py`: SQLite CRUD for travels
- `backend/utils/auth_db.py`: User management
- `backend/utils/settings_store.py`: Settings persistence
- `backend/utils/migrations.py`: Schema migrations

### Testing
- `backend/tests/conftest.py`: Shared pytest fixtures
- `backend/tests/test_models.py`: Model validation tests
- `backend/tests/test_endpoints.py`: API endpoint tests
- `backend/tests/test_agents_mock.py`: Agent tests with mocked Anthropic
- `backend/tests/test_travel_db.py`: Database tests

## Naming Conventions

### Files
- **Python:** `snake_case.py` — e.g., `route_architect.py`, `travel_db.py`
- **JavaScript:** `kebab-case.js` — e.g., `route-builder.js`, `sse-overlay.js`
- **Models:** Named after the domain concept — e.g., `travel_request.py`, `stop_option.py`
- **Tests:** `test_` prefix — e.g., `test_models.py`, `test_endpoints.py`

### Directories
- **Lowercase, single word or underscore:** `agents/`, `models/`, `utils/`, `tasks/`, `routers/`
- **Frontend JS:** Flat structure in `frontend/js/` (no subdirectories)

## Module Dependencies

### Backend Import Graph
```
main.py
├── models/* (Pydantic validation)
├── utils/auth.py (JWT, password)
├── utils/auth_db.py (user storage)
├── utils/debug_logger.py (SSE + logging)
├── utils/maps_helper.py (Google APIs)
├── utils/travel_db.py (SQLite persistence)
├── utils/settings_store.py (runtime config)
├── routers/auth.py, routers/admin.py
└── agents/stop_options_finder.py (inline for route building)

orchestrator.py
├── agents/* (all agents)
├── models/travel_request.py
├── utils/debug_logger.py
└── utils/image_fetcher.py

agents/*
├── agents/_client.py (Anthropic client + model)
├── utils/retry_helper.py (call_with_retry)
├── utils/json_parser.py (parse_agent_json)
└── utils/debug_logger.py (logging)

tasks/*
├── tasks/__init__.py (celery_app)
├── orchestrator.py
├── agents/* (for prefetch/replace tasks)
└── utils/* (debug_logger, travel_db, settings_store)
```

### Frontend Dependency Order (script loading)
All scripts are globals, loaded in this order in `index.html`:
1. `state.js` — defines `S`, `esc()`, `FLAGS`, `TRAVEL_STYLES`
2. `api.js` — defines all `api*()` functions and `openSSE()`
3. `auth.js` — defines auth functions used by api.js
4. `loading.js` — loading overlay
5. `form.js` — form UI
6. `route-builder.js` — route building UI
7. `accommodation.js` — accommodation UI
8. `sse-overlay.js` — progress overlay component
9. `progress.js` — progress handlers
10. `guide.js` — result rendering
11. `travels.js` — saved travels
12. `maps.js` — Google Maps
13. `sidebar.js` — sidebar
14. `settings.js` — settings page
15. `router.js` — routing (must be last, dispatches on load)

## Where to Add New Code

### New AI Agent
1. Create `backend/agents/new_agent.py` following the pattern in `route_architect.py`
2. Add `AGENT_KEY` constant, use `get_client()` and `get_model()` from `_client.py`
3. Use `call_with_retry()` for all Claude API calls
4. Add component mapping in `backend/utils/debug_logger.py` `_COMPONENT_MAP`
5. Add default model/max_tokens in `backend/utils/settings_store.py` `DEFAULTS`
6. Call from `backend/orchestrator.py` or create a new task in `backend/tasks/`

### New API Endpoint
1. Add to `backend/main.py` (for trip-related endpoints) or create a new router in `backend/routers/`
2. Use `Depends(get_current_user)` for authentication
3. Use Pydantic models for request/response validation
4. Add corresponding API function in `frontend/js/api.js`

### New Frontend Feature
1. Create `frontend/js/new-feature.js` (kebab-case)
2. Add `<script>` tag in `frontend/index.html` (before `router.js`)
3. Add route pattern in `frontend/js/router.js` `_routes` array if URL-routable
4. Add section `<div>` in `frontend/index.html` with class `section`
5. Use `S` object for state, `esc()` for user content, api functions from `api.js`

### New Pydantic Model
1. Create in `backend/models/` or add to existing file matching the domain
2. Import in `backend/main.py` if used in endpoints
3. Add validation tests in `backend/tests/test_models.py`

### New Utility
1. Add to `backend/utils/` as a module-level function file
2. Use `async def` for any I/O operations
3. Log via `debug_logger.log()` with appropriate `LogLevel`

### New Celery Task
1. Create `backend/tasks/new_task.py` following the pattern in `run_planning_job.py`
2. Add task import to `backend/tasks/__init__.py` `include` list
3. Add dispatch case in `_fire_task()` in `backend/main.py` (both Celery and asyncio paths)

### New Test
1. Add to appropriate existing test file, or create `backend/tests/test_new.py`
2. Use fixtures from `conftest.py`
3. Run: `cd backend && python3 -m pytest tests/test_new.py -v`

## Special Directories

### `backend/logs/`
- **Purpose:** Runtime log files, organized by component
- **Structure:** `agents/*.log`, `orchestrator/orchestrator.log`, `api/api.log`, `frontend/frontend.log`
- **Generated:** Yes (at runtime)
- **Committed:** No
- **Rotation:** Daily, 30-day retention

### `outputs/`
- **Purpose:** Generated PDF and PPTX travel documents
- **Generated:** Yes (on demand via `/api/generate-output/`)
- **Committed:** No (directory only)

### `data/` (Docker volume `travel_data`)
- **Purpose:** SQLite databases (travels.db, settings.db)
- **Generated:** Yes (at startup)
- **Committed:** No (persisted via Docker volume)

---

*Structure analysis: 2026-03-25*
