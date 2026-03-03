# Travelman2 — Claude Multi-Agent Travel Planner

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
python3 -m pytest tests/test_models.py        # Pydantic validation only
python3 -m pytest tests/test_endpoints.py     # API routes
python3 -m pytest tests/test_agents_mock.py   # agents with mocked Anthropic
```

### Dependencies
```bash
cd backend && pip3 install -r requirements.txt
```

---

## Project Architecture

```
travelman2/
├── CLAUDE.md
├── docker-compose.yml
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── backend/
│   ├── main.py                      # FastAPI app, 11 endpoints
│   ├── orchestrator.py              # TravelPlannerOrchestrator
│   ├── tasks/
│   │   ├── run_planning_job.py      # Celery task: full orchestration
│   │   └── prefetch_accommodations.py # Celery task: parallel acc fetch
│   ├── agents/
│   │   ├── route_architect.py       # claude-opus-4-5
│   │   ├── stop_options_finder.py   # claude-sonnet-4-5
│   │   ├── accommodation_researcher.py # claude-sonnet-4-5
│   │   ├── activities_agent.py      # claude-sonnet-4-5 + WikipediaEnricher
│   │   ├── restaurants_agent.py     # claude-sonnet-4-5
│   │   ├── day_planner.py           # claude-opus-4-5 + OSRM
│   │   └── output_generator.py      # PDF/PPTX (fpdf2 + pptx)
│   ├── models/
│   │   ├── travel_request.py        # TravelRequest Pydantic model
│   │   ├── travel_response.py       # TravelPlan, TravelStop, DayPlan, CostEstimate
│   │   ├── stop_option.py           # StopOption, StopOptionsResponse
│   │   └── accommodation_option.py  # AccommodationOption, BudgetState
│   ├── utils/
│   │   ├── debug_logger.py          # Singleton DebugLogger, SSE subscriber manager
│   │   ├── maps_helper.py           # geocode_nominatim(), osrm_route(), build_maps_url()
│   │   ├── retry_helper.py          # call_with_retry() with exponential backoff
│   │   └── json_parser.py           # parse_agent_json() strips markdown fences
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_models.py
│   │   ├── test_endpoints.py
│   │   └── test_agents_mock.py
│   ├── .env                         # never commit
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
│       └── types.d.ts       # generated from OpenAPI — do not edit manually
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
- **TEST_MODE=false** → Opus for route+planner, Sonnet for research, Haiku for output
- **Job state in Redis** — key pattern `job:{job_id}`, TTL 24h
- **SSE stream closes** on `job_complete` or `job_error` event
- **Budget split:** 45% accommodation · 15% food · ~CHF 80/stop activities · CHF 12/h fuel
- **OSRM replaces Claude drive estimates** — always enrich with real routing data
- **Nominatim rate limit:** max 1 req/s — enforce 350ms sleep between geocode calls

---

## Agent Model Assignments

| Agent | Production | Test (TEST_MODE=true) |
|-------|-----------|----------------------|
| RouteArchitectAgent | claude-opus-4-5 | claude-haiku-4-5 |
| StopOptionsFinderAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| AccommodationResearcherAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |

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

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...     # required
TEST_MODE=true                   # true=haiku, false=opus/sonnet
REDIS_URL=redis://localhost:6379 # job state store
```

---

## Testing Standards

- **test_models.py:** Pydantic validation — valid inputs, invalid inputs, edge cases
- **test_endpoints.py:** FastAPI TestClient — all 11 endpoints, happy path + error cases
- **test_agents_mock.py:** Mock `anthropic.Anthropic` — verify prompt structure, JSON parsing, retry logic
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
git commit -m "type: beschreibung\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag vX.X.Y        # increment patch number from latest tag
git push && git push --tags
```

- Version scheme: `x.x.y` — only increment `y` for each change
- Check current version with `git tag --sort=-v:refname | head -1`
- Commit message in German, type prefix in English (fix/feat/perf/docs/refactor)
