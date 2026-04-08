# backend/CLAUDE.md

This worker owns `backend/main.py`, `backend/routers/`, `backend/models/`,
`backend/utils/`, `backend/services/`, and `backend/tests/`.
Do NOT modify `backend/agents/`, `frontend/`, or `infra/`.
Reads (not modifies): `backend/agents/` (to understand contracts).

## Directory Structure

```
backend/
├── main.py                          # FastAPI app, 40+ endpoints (~2600 lines)
├── orchestrator.py                  # TravelPlannerOrchestrator (read-only for this worker)
├── tasks/                           # Celery tasks (read-only for this worker)
│   ├── run_planning_job.py
│   ├── prefetch_accommodations.py
│   └── replace_stop_job.py
├── services/                        # Shared services (redis_store, etc.)
│   └── redis_store.py               # Redis client singleton, get_job, save_job
├── agents/                          # AI agents — see backend/agents/CLAUDE.md
├── models/
│   ├── travel_request.py            # TravelRequest Pydantic model
│   ├── travel_response.py           # TravelPlan, TravelStop, DayPlan, CostEstimate
│   ├── stop_option.py               # StopOption, StopOptionsResponse
│   ├── accommodation_option.py      # AccommodationOption, BudgetState
│   ├── trip_leg.py                  # TripLeg model
│   └── via_point.py                 # ViaPoint model
├── utils/
│   ├── debug_logger.py              # Singleton DebugLogger, SSE subscriber manager
│   ├── maps_helper.py               # geocode_google(), google_directions(), build_maps_url()
│   ├── retry_helper.py              # call_with_retry() with exponential backoff
│   ├── json_parser.py               # parse_agent_json() strips markdown fences
│   ├── travel_db.py                 # SQLite persistence for saved travels
│   ├── hotel_price_fetcher.py       # hotel price scraping/fetching
│   ├── image_fetcher.py             # destination image fetching
│   ├── auth.py                      # authentication logic
│   ├── auth_db.py                   # authentication database
│   ├── brave_search.py              # Brave search integration
│   ├── currency.py                  # currency conversion
│   ├── google_places.py             # Google Places API
│   ├── migrations.py                # database migrations
│   ├── settings_store.py            # settings persistence
│   ├── weather.py                   # weather data fetching
│   └── wikipedia.py                 # Wikipedia enrichment
└── tests/
    ├── conftest.py
    ├── test_models.py               # 38 Pydantic validation tests
    ├── test_endpoints.py            # 24 API route tests
    ├── test_agents_mock.py          # 20 agent tests with mocked Anthropic
    └── test_travel_db.py            # travel persistence tests
```

## Python Conventions

- Type hints on ALL function signatures (no exceptions)
- Pydantic models for all API request/response boundaries
- `async/await` throughout; blocking SDK calls wrapped in `asyncio.to_thread()`
- `Optional[X]` for nullable fields, `List[X]` from `typing` (not `list[X]`)
- snake_case modules: `travel_request.py`, `maps_helper.py`
- PascalCase classes: `TravelRequest`, `RouteArchitectAgent`, `DebugLogger`
- Private methods prefixed `_`: `_build_booking_url()`, `_get_conn()`
- Sync DB helpers prefixed `_sync_`: `_sync_save()`, `_sync_list()` in `travel_db.py`
- Constants UPPER_SNAKE_CASE: `REDIS_URL`, `SYSTEM_PROMPT`, `AGENT_KEY`
- 4 spaces indentation
- Section dividers: `# ---------------------------------------------------------------------------`

## FastAPI Patterns

- All HTTP errors: `raise HTTPException(status_code=X, detail="German message")`
- Protected endpoints use `user: User = Depends(get_current_user)` dependency
- SSE endpoints use `user: User = Depends(get_current_user_sse)` (reads `?token=` query param)
- Response models declared on endpoint decorator: `response_model=TravelPlan`
- Pydantic v2 throughout — use `model_validate()`, not `parse_obj()`

## Redis Job State

- Key pattern: `job:{job_id}` (hex UUID, 32 chars), TTL 24h
- Job statuses: `building_route` → `awaiting_region_confirmation` → `selecting_accommodations`
  → `running` → `complete` | `error`
- SSE event list key: `sse:{job_id}` (Redis list, drained by SSE endpoint)
- Without Redis: `_InMemoryStore` in `main.py` provides drop-in replacement for local dev

## Authentication

- JWT tokens: 15-minute access tokens, httpOnly refresh cookies
- Token flow: Login → access token (in-memory) + refresh cookie → silent refresh on 401
- SSE auth: `?token=...` query param (EventSource doesn't support headers)
- Password hashing: Argon2id via passlib

## Logging (REQUIRED)

Add to `_COMPONENT_MAP` in `debug_logger.py` for every new component:
```python
"NewComponentName": "agents/new_component",  # or "api/", "orchestrator/"
```

Call pattern:
```python
debug_logger.log(LogLevel.INFO, "message", job_id=job_id, agent="ComponentName")
debug_logger.log_prompt(agent_name, model, prompt, job_id=job_id)
```

| Level | Use |
|-------|-----|
| `ERROR` / `WARNING` | Problems (always logged) |
| `INFO` / `SUCCESS` / `AGENT` | Normal flow |
| `API` | External API calls (log before calling) |
| `DEBUG` / `PROMPT` | Debug-only detail |

Log files: `backend/logs/agents/<name>.log`, `orchestrator/orchestrator.log`, `api/api.log`

## Testing

```bash
cd backend && python3 -m pytest tests/ -v                           # all tests
cd backend && python3 -m pytest tests/test_models.py               # Pydantic validation (38 tests)
cd backend && python3 -m pytest tests/test_endpoints.py            # API routes (24 tests)
cd backend && python3 -m pytest tests/test_agents_mock.py          # mocked agents (20 tests)
cd backend && python3 -m pytest tests/test_travel_db.py            # SQLite persistence
```

- `test_models.py`: valid inputs, invalid inputs, edge cases
- `test_endpoints.py`: FastAPI TestClient, happy path + error cases
- `test_agents_mock.py`: mock `anthropic.Anthropic`, verify prompts + JSON parsing + retry logic
- `test_travel_db.py`: CRUD operations and data integrity
- Agents must be testable without API keys

## Local API Debugging

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

## Test Trip (for development)

- Start: Liestal, Schweiz
- Destination: Französische Alpen → Paris
- Duration: 10 days, 2 adults, CHF 5'000
- Max drive time/day: 4.5h
