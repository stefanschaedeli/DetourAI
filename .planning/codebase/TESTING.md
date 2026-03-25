# Testing Patterns

**Analysis Date:** 2026-03-25

## Test Framework

**Runner:**
- pytest >= 8.0.0
- No config file (no `pytest.ini`, `pyproject.toml [tool.pytest]`, or `conftest.py` at root)
- Config via `backend/tests/conftest.py` (shared fixtures)

**Key Plugins:**
- `pytest-mock` >= 3.12.0 — `mocker` fixture for patching
- `pytest-asyncio` >= 0.23.0 — async test support (though most tests use `asyncio.run()` manually)
- `httpx` >= 0.27.0 — required by FastAPI TestClient

**Assertion Library:**
- Built-in `assert` statements (no third-party assertion library)
- `pytest.raises()` for exception testing

**Run Commands:**
```bash
cd backend && python3 -m pytest tests/ -v           # Run all tests
cd backend && python3 -m pytest tests/test_models.py # Pydantic validation only
cd backend && python3 -m pytest tests/test_endpoints.py  # API routes
cd backend && python3 -m pytest tests/test_agents_mock.py # Agents with mocked Anthropic
cd backend && python3 -m pytest tests/test_travel_db.py   # Travel persistence
cd backend && python3 -m pytest tests/test_auth.py        # Authentication
cd backend && python3 -m pytest tests/test_migrations.py  # DB migrations
cd backend && python3 -m pytest tests/test_mcp_utils.py   # MCP utility tests
```

## Test File Organization

**Location:** All tests in `backend/tests/` (separate directory, not co-located)

**Naming:** `test_*.py` prefix convention

**Structure:**
```
backend/tests/
├── __init__.py              # Empty
├── conftest.py              # Shared fixtures (91 lines)
├── test_models.py           # Pydantic model validation (788 lines)
├── test_agents_mock.py      # Agent tests with mocked Anthropic (649 lines)
├── test_endpoints.py        # FastAPI endpoint tests (474 lines)
├── test_auth.py             # Authentication tests (335 lines)
├── test_mcp_utils.py        # MCP utility tests (302 lines)
├── test_migrations.py       # DB migration tests (167 lines)
└── test_travel_db.py        # SQLite persistence tests (144 lines)
```

**Total: 192 tests across 7 test files (2,950 lines)**

## Test Structure

### Suite Organization

Tests use both plain functions and classes:

**Plain functions (most common):**
```python
# backend/tests/test_models.py
def test_travel_request_valid(sample_request):
    req = TravelRequest(**sample_request)
    assert req.adults == 2
    assert req.budget_chf == 5000.0

def test_child_age_invalid_too_old():
    with pytest.raises(ValueError):
        Child(age=18)
```

**Test classes (for related groups):**
```python
# backend/tests/test_models.py
class TestZoneBBox:
    def test_valid_bbox(self):
        bbox = ZoneBBox(north=42.0, south=36.0, east=28.0, west=20.0, zone_label="Griechenland")
        assert bbox.zone_label == "Griechenland"

    def test_south_must_be_less_than_north(self):
        with pytest.raises(ValueError, match="south must be less than north"):
            ZoneBBox(north=36.0, south=42.0, east=28.0, west=20.0, zone_label="X")
```

**Section dividers** separate test groups within files:
```python
# ---------------------------------------------------------------------------
# TravelRequest
# ---------------------------------------------------------------------------
```

### Naming Convention

- Test functions: `test_<subject>_<scenario>` e.g., `test_child_age_invalid_negative`
- Test classes: `Test<Subject>` e.g., `TestZoneBBox`, `TestRegionPlannerAgent`
- Helper functions: `_sample_plan()`, `_make_single_transit_req()`, `_transit_legs_payload()`

## Fixtures

### Shared Fixtures (`backend/tests/conftest.py`)

```python
@pytest.fixture
def client(mocker):
    """FastAPI TestClient with mocked Redis."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.keys.return_value = []
    mocker.patch('main.redis_client', mock_redis)
    from main import app
    return TestClient(app)

@pytest.fixture
def mock_job(mocker):
    """A minimal job dict stored in mocked Redis, returns the job dict for mutation."""
    # Creates a job_id, configures mock_redis.get to return job JSON
    # Returns mutable job dict so tests can modify state before calling endpoints

@pytest.fixture
def sample_request():
    """Standard travel request payload dict for API tests."""
```

### Per-File Fixtures

**test_travel_db.py:**
```python
@pytest.fixture(autouse=True)
def use_tmp_db(tmp_path, monkeypatch):
    """Redirect DB to a temp directory for each test."""
    monkeypatch.setattr(tdb, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(tdb, 'DB_PATH', tmp_path / 'travels.db')
    tdb._init_db()
```

**test_auth.py:**
```python
@pytest.fixture(autouse=True)
def patch_jwt_secret(monkeypatch):
    """Ensure the in-memory JWT_SECRET constant is set for every test."""

@pytest.fixture(autouse=True)
def use_tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a temp directory for each test."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from utils.migrations import run_migrations
    run_migrations(str(tmp_path / "travels.db"))
```

**test_endpoints.py:**
```python
@pytest.fixture
def client(mock_redis):
    """FastAPI TestClient with auth dependency overridden."""
    from main import app
    from utils.auth import CurrentUser, get_current_user
    mock_user = CurrentUser(id=1, username="testuser", is_admin=False)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()
```

## Mocking Strategies

### Anthropic API Mocking

All agent tests mock the Anthropic client to avoid real API calls:

```python
# backend/tests/test_agents_mock.py
def test_route_architect_json_parsing(mocker):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"stops": [], "total_drive_days": 2}')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create.return_value = mock_response

    mocker.patch('agents.route_architect.get_client', return_value=mock_client)
    mocker.patch('utils.retry_helper.asyncio.to_thread', new=AsyncMock(return_value=mock_response))
```

**Pattern for mocking `call_with_retry`:** Patch `asyncio.to_thread` in `utils.retry_helper` since `call_with_retry` wraps the sync SDK call via `to_thread`.

### Redis Mocking

Redis is always mocked in tests — no real Redis required:

```python
mock_redis = MagicMock()
mock_redis.get.return_value = None          # No job found
mock_redis.setex.return_value = True        # Save succeeds
mock_redis.keys.return_value = []           # No active jobs
mocker.patch('main.redis_client', mock_redis)
```

For tests needing specific job state, use `mock_redis.get.side_effect` to return job JSON:
```python
mock_redis.get.side_effect = lambda key: (
    json.dumps(job).encode() if key == f"job:{job_id}" else None
)
```

### Authentication Mocking

Endpoint tests override FastAPI's `get_current_user` dependency:
```python
mock_user = CurrentUser(id=1, username="testuser", is_admin=False)
app.dependency_overrides[get_current_user] = lambda: mock_user
```

### External Service Mocking

```python
# Google Maps APIs
mocker.patch('main.geocode_google', return_value=(47.5, 7.6, 'ChIJMz5dPRdMkEcR...'))
mocker.patch('main.google_directions_simple', return_value=(1.0, 80.0))
mocker.patch('main.google_directions', return_value=(1.0, 80.0, 'encodedPolyline123'))

# Image fetcher
mocker.patch('utils.image_fetcher.fetch_unsplash_images', new=AsyncMock(
    return_value={"image_overview": None, "image_mood": None, "image_customer": None}
))
```

### Async Test Pattern

Most async tests use `asyncio.run()` rather than `@pytest.mark.asyncio`:
```python
def test_accommodation_find_options_structure(mocker):
    # ... setup mocks ...
    async def _run():
        return await agent.find_options(stop, budget_per_night=150.0)
    result = asyncio.run(_run())
    assert len(result.get("options", [])) == 4
```

## Test Categories

### Unit Tests

**Model validation (`test_models.py`):** ~60+ tests
- Valid input construction
- Default values
- Field constraints (min/max, valid values)
- Validation errors (`pytest.raises(ValueError)`)
- Nested model construction
- Derived property computation

**Utility function tests (`test_agents_mock.py`):**
- `parse_agent_json()` — plain JSON, fenced JSON, whitespace, invalid input
- `build_maps_url()` — single/multiple/empty/filtered stops
- `debug_logger` — singleton identity, subscribe/unsubscribe
- `_reorder_regions()` — pure function route optimization tests

### Integration Tests (with mocks)

**Endpoint tests (`test_endpoints.py`):** ~24 tests
- Happy path for each endpoint
- 404/422 error cases
- Request validation (missing required fields)
- CRUD operations for travels
- Region plan endpoints (409 conflict, 400 bad index, 200 success)

**Agent tests (`test_agents_mock.py`):** ~20 tests
- Agent instantiation
- JSON response parsing
- Retry on rate limit
- Response structure validation (correct fields present/absent)

**Auth tests (`test_auth.py`):** ~35 tests
- Password hashing and verification
- JWT creation and validation
- Login/logout/refresh flow
- User CRUD operations

**DB tests (`test_travel_db.py`):** ~13 tests
- CRUD operations on SQLite
- Duplicate handling
- User scoping (multi-tenant isolation)
- Async wrapper tests

**Migration tests (`test_migrations.py`):** ~18 tests
- Schema creation
- Column additions
- Idempotent re-runs

### E2E Tests

**Not present.** No browser-based testing (Playwright, Cypress, etc.) or full-stack integration tests.

## Coverage

**What IS tested (192 tests):**
- All Pydantic models — valid inputs, invalid inputs, edge cases, defaults
- All API endpoints — happy path + common error cases
- Agent instantiation and JSON parsing (mocked Anthropic)
- Retry logic for rate limits
- SQLite persistence — CRUD + user scoping
- Authentication — JWT, password hashing, login/logout
- DB migrations — schema creation and column additions
- Utility functions — JSON parser, maps URL builder, region reordering

**What is NOT tested (gaps):**

| Gap | Files | Risk |
|-----|-------|------|
| Orchestrator end-to-end flow | `backend/orchestrator.py` | High — core business logic combining all agents |
| Celery task execution | `backend/tasks/run_planning_job.py`, `prefetch_accommodations.py`, `replace_stop_job.py` | Medium — task dispatch and error handling |
| SSE streaming | `main.py` SSE endpoints, `utils/debug_logger.py` push_event | Medium — real-time progress delivery |
| Frontend JavaScript | All `frontend/js/*.js` files | Medium — no JS testing framework at all |
| Agent prompt quality | All `backend/agents/*.py` | Low — prompts tested indirectly via mock responses |
| Google Maps integration | `utils/maps_helper.py` (real API calls) | Low — always mocked in tests |
| Brave Search / Wikipedia | `utils/brave_search.py`, `utils/wikipedia.py` | Low — external service wrappers |
| Hotel price fetching | `utils/hotel_price_fetcher.py` | Low — external scraping |
| Weather data | `utils/weather.py` | Low — external API |
| PDF/PPTX generation | `agents/output_generator.py` | Medium — only instantiation tested |
| Currency conversion | `utils/currency.py` | Low — utility |
| Google Places | `utils/google_places.py` | Low — external API |
| Settings store | `utils/settings_store.py` | Low — simple KV store |

## Environment Setup for Tests

**No external services required.** All tests mock Redis, Anthropic, and Google APIs.

**Environment variables set in test files:**
- `DATA_DIR` → temp directory (via `monkeypatch` or `os.environ`)
- `JWT_SECRET` → `"test_secret_that_is_exactly_32chars!"` (set before imports in `test_endpoints.py` and `test_auth.py`)

**Path setup:** Each test file adds backend to Python path manually:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
```

**Install test dependencies:**
```bash
cd backend && pip3 install -r requirements.txt  # includes pytest, pytest-mock, pytest-asyncio, httpx
```

## CI/CD Test Integration

**No CI/CD pipeline detected.** No `.github/workflows/`, `Jenkinsfile`, `.gitlab-ci.yml`, or similar configuration files present.

Tests are run manually via `python3 -m pytest`.

## Adding New Tests

**For a new Pydantic model:**
- Add tests to `backend/tests/test_models.py`
- Test valid construction, defaults, validation errors
- Use section divider comment block

**For a new API endpoint:**
- Add tests to `backend/tests/test_endpoints.py`
- Use the `client` fixture (includes mocked Redis + auth override)
- Test happy path, 404, 422 validation errors

**For a new agent:**
- Add tests to `backend/tests/test_agents_mock.py`
- Mock `get_client` and `asyncio.to_thread` in `retry_helper`
- Test instantiation and JSON response parsing
- Use `_make_single_transit_req()` helper for creating test requests

**For new DB operations:**
- Add tests to `backend/tests/test_travel_db.py`
- Use `use_tmp_db` autouse fixture (auto-applied)
- Test both sync (`_sync_*`) and async wrappers

---

*Testing analysis: 2026-03-25*
