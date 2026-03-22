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
travelman3/
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
│   │   ├── trip_analysis_agent.py       # claude-sonnet-4-5 (replan analysis)
│   │   └── output_generator.py          # PDF/PPTX (fpdf2 + pptx)
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
└── outputs/                 # generated PDF/PPTX files
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
