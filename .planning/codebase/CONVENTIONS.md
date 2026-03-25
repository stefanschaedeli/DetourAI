# Coding Conventions

**Analysis Date:** 2026-03-25

## Naming Patterns

**Python Files:**
- snake_case for all modules: `route_architect.py`, `travel_request.py`, `debug_logger.py`
- Agent modules match their class name in snake_case: `AccommodationResearcherAgent` lives in `accommodation_researcher.py`
- Utility modules are descriptive nouns: `retry_helper.py`, `json_parser.py`, `maps_helper.py`
- Private/internal prefixed with underscore: `_client.py` (shared Anthropic client factory)

**Python Classes:**
- PascalCase for all classes: `TravelRequest`, `RouteArchitectAgent`, `DebugLogger`
- Agent classes suffixed with `Agent`: `RouteArchitectAgent`, `AccommodationResearcherAgent`, `DayPlannerAgent`
- Pydantic models are plain nouns: `TravelStop`, `CostEstimate`, `BudgetState`, `StopOption`
- Request/Response models suffixed accordingly: `StopSelectRequest`, `AccommodationResearchRequest`

**Python Functions/Methods:**
- snake_case throughout: `find_options()`, `build_maps_url()`, `parse_agent_json()`
- Private methods prefixed with underscore: `_build_booking_url()`, `_get_conn()`, `_init_db()`
- Async methods use same naming (no special prefix): `async def run()`, `async def find_options()`
- Sync DB helpers prefixed `_sync_`: `_sync_save()`, `_sync_list()`, `_sync_get()`, `_sync_delete()` in `utils/travel_db.py`

**Python Variables:**
- snake_case: `job_id`, `token_accumulator`, `budget_per_night`
- Constants are UPPER_SNAKE_CASE: `REDIS_URL`, `SYSTEM_PROMPT`, `AGENT_KEY`
- Module-level maps use UPPER_SNAKE_CASE: `VERBOSITY_FILTER`, `_COMPONENT_MAP` (private constant)

**JavaScript Files:**
- kebab-case: `route-builder.js`, `sse-overlay.js`, `travel-guide.js`
- Exception: `state.js`, `api.js`, `form.js` (single-word names)

**JavaScript Functions:**
- camelCase: `goToStep()`, `showTravelGuide()`, `renderGuide()`, `buildPayload()`
- Private/internal prefixed with underscore: `_fetchWithAuth()`, `_authHeader()`, `_initGuideMap()`
- API wrappers prefixed `api`: `apiLogin()`, `apiLogout()`, `apiGetMe()`, `apiLogError()`

**JavaScript Variables:**
- camelCase for locals and state: `activeTab`, `selectedStops`, `loadingOptions`
- Global state object is single letter `S` (defined in `state.js`)
- Constants are UPPER_CASE: `API`, `TRAVEL_STYLES`, `FLAGS`
- Private module-level vars prefixed with underscore: `_guideMarkers`, `_guidePolyline`, `_activeStopId`

**CSS Classes:**
- kebab-case: `form-step`, `step-indicator`, `flag-badge`, `guide-tab`, `guide-content`

## Code Patterns

### Agent Pattern (Backend)

All agents in `backend/agents/` follow a consistent structure:

```python
# backend/agents/route_architect.py (representative pattern)

from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "route_architect"  # Used for settings lookup

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner... "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. "
    "Kein Markdown, keine Erklärungen, nur JSON."
)

class RouteArchitectAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self) -> dict:
        # 1. Log start
        await debug_logger.log(LogLevel.AGENT, "RouteArchitect startet", ...)
        # 2. Build prompt
        prompt = f"..."
        # 3. Log API call
        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", ...)
        await debug_logger.log_prompt("RouteArchitect", self.model, prompt, ...)
        # 4. Call with retry
        response = await call_with_retry(
            lambda: self.client.messages.create(...),
            job_id=self.job_id, agent_name="RouteArchitect",
            token_accumulator=self.token_accumulator,
        )
        # 5. Parse JSON response
        result = parse_agent_json(response.content[0].text)
        return result
```

**Key rules for new agents:**
1. Define `AGENT_KEY` constant for settings lookup
2. Use `get_client()` and `get_model()` from `agents/_client.py`
3. System prompt in German, requiring JSON-only output
4. All Claude API calls go through `call_with_retry()` from `utils/retry_helper.py`
5. Parse responses with `parse_agent_json()` from `utils/json_parser.py`
6. Log with `debug_logger.log()` at appropriate levels before and after API calls
7. Accept `token_accumulator: list = None` and pass it to `call_with_retry()`

### Error Handling

**Python:**
- HTTP errors use FastAPI's `HTTPException` with German detail messages:
  ```python
  raise HTTPException(status_code=404, detail=f"Reise {travel_id} nicht gefunden")
  ```
- Rate limits handled by `call_with_retry()` with exponential backoff (`utils/retry_helper.py`)
- Truncated JSON from Claude detected by brace counting in `parse_agent_json()` (`utils/json_parser.py`)
- Agent errors logged with `LogLevel.ERROR` and re-raised

**JavaScript:**
- `_fetch()` wrapper in `api.js` throws `Error` with `HTTP {status}: {detail}` format
- 401 responses trigger one silent token refresh attempt before throwing
- `window.onerror` and `window.onunhandledrejection` auto-report errors to backend via `apiLogError()`
- User-content HTML interpolation uses `esc()` function for XSS prevention

### Logging

**Framework:** Custom `DebugLogger` singleton in `backend/utils/debug_logger.py`

**Log levels (use appropriate level):**
| Level | When to use |
|-------|------------|
| `ERROR` / `WARNING` | Problems (always logged) |
| `INFO` / `SUCCESS` / `AGENT` | Normal flow (logged at Normal+) |
| `API` | External API calls (logged at Verbose+) |
| `DEBUG` / `PROMPT` | Detailed debug info (logged at Debug only) |

**Pattern:**
```python
from utils.debug_logger import debug_logger, LogLevel

# Before API call
await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}",
                       job_id=self.job_id, agent="AgentName")

# Prompt logging
await debug_logger.log_prompt("AgentName", self.model, prompt, job_id=self.job_id)

# Success
await debug_logger.log(LogLevel.SUCCESS, "Vorgang abgeschlossen",
                       job_id=self.job_id, agent="AgentName")
```

**Log file routing:** The `agent` parameter maps to a file via `_COMPONENT_MAP` in `debug_logger.py`. When adding a new agent, add an entry there.

### API Response Formats

**Success responses** return JSON dicts directly (FastAPI auto-serialization):
```python
return {"job_id": job_id, "status": "building_route", "options": [...]}
```

**Error responses** use `HTTPException`:
```python
raise HTTPException(status_code=404, detail="Job nicht gefunden")
raise HTTPException(status_code=409, detail="Kein Regionsplan vorhanden")
```

**SSE events** pushed via `debug_logger.push_event()`:
```python
await debug_logger.push_event(job_id, "stop_options", agent_id, data, percent)
```

### Common Abstractions

- **`call_with_retry(fn, ...)`** (`utils/retry_helper.py`): Wraps blocking Anthropic calls with exponential backoff on 429/529
- **`parse_agent_json(text)`** (`utils/json_parser.py`): Strips markdown fences, detects truncation
- **`get_client()`** / **`get_model(prod, key)`** (`agents/_client.py`): Anthropic client factory + TEST_MODE model switching
- **`_InMemoryStore`** (`main.py`): Drop-in Redis replacement for local dev without Redis
- **`_fire_task(name, job_id)`** (`main.py`): Dispatches Celery tasks or inline asyncio fallback

## Style & Formatting

**Indentation:**
- Python: 4 spaces
- JavaScript: 2 spaces
- HTML/CSS: 2 spaces

**Line Length:**
- No enforced limit (no linting config detected)
- Practical convention: ~100-120 chars, but long strings/prompts are not wrapped

**Linting/Formatting Tools:**
- None detected (no `.eslintrc`, `.prettierrc`, `.flake8`, `pyproject.toml` with tool config, or `biome.json`)
- Code style is enforced by convention only

**Import Organization (Python):**
```python
# 1. Standard library
import asyncio
import json
import os
from datetime import date, timedelta
from typing import List, Optional

# 2. Third-party packages
from fastapi import HTTPException
from pydantic import BaseModel, Field
import anthropic

# 3. Local/project imports
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from agents._client import get_client, get_model
```

No blank lines between groups (inconsistently applied). Imports are not sorted alphabetically.

**Import Organization (JavaScript):**
- No import system; all JS files loaded via `<script>` tags in `index.html`
- Files rely on globals (`S`, `API`, `esc()`, etc.) being available from previously loaded scripts
- Load order matters (e.g., `state.js` before `api.js` before `form.js`)

**Path Aliases:**
- Python: `sys.path.insert(0, ...)` used in test files to add backend to path
- No Python package structure (`__init__.py` files are empty)
- JavaScript: No path aliases; direct `<script src="js/file.js">` loading

## Language

**All user-facing text in German.** This includes:
- Error messages: `"Reise nicht gefunden"`, `"Sitzung abgelaufen"`
- Log messages: `"RouteArchitect startet"`, `"Rate limit — retry in..."`
- System prompts to Claude: `"Du bist ein Reiseplaner..."`
- UI labels in HTML/JS: `"Anfrage läuft…"`, `"Zurück zu Schritt {n}"`
- **Prices always in CHF**

**Code identifiers in English:**
- Variable/function names, class names, module names are English
- Exception: some domain terms kept in German when they are product concepts (e.g., `is_geheimtipp`, `geheimtipp_hinweis`)

## Documentation

**Docstrings:**
- Used sparingly; not required on all functions
- When present, single-line format preferred:
  ```python
  def _build_booking_url(...) -> str:
      """Geheimtipp: Suchlink nur mit Stadt/Region, kein konkreter Hotelname."""
  ```
- Module-level docstrings present on some files:
  ```python
  """Shared Anthropic client factory — reads env vars at call time, not import time."""
  ```

**Comments:**
- Section dividers using `# ---------------------------------------------------------------------------`
- Inline comments for non-obvious logic
- German and English mixed in comments (German for domain, English for technical)

**Type Hints:**
- Required on all function signatures (per CLAUDE.md convention)
- Pydantic models handle validation at API boundaries
- `Optional[X]` used for nullable fields
- `List[X]` from `typing` (not `list[X]` builtin syntax)

## Pydantic Model Conventions

**Location:** `backend/models/` directory, one file per domain area

**Pattern:**
```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class ModelName(BaseModel):
    required_field: str
    optional_field: Optional[str] = None
    list_with_default: List[str] = []
    constrained_field: int = Field(default=2, ge=1, le=20)

    @field_validator('field_name')
    @classmethod
    def validate_field(cls, v):
        if not valid(v):
            raise ValueError('description')
        return v
```

**Defaults:** Always provide sensible defaults where possible.
**Validation:** Use `Field(ge=, le=, max_length=)` for simple constraints; `@field_validator` for complex logic.

## Frontend State Management

**Global state object `S`** defined in `frontend/js/state.js`:
- All mutable app state lives on `S`
- Accessed globally from all JS modules
- LocalStorage keys prefixed `tp_v1_*`
- No reactivity system; UI updates are imperative DOM manipulation

**API calls exclusively in `api.js`:**
- Never use `fetch()` directly outside `api.js`
- Use `_fetch()` for requests with loading overlay
- Use `_fetchQuiet()` for background requests (skeleton cards provide feedback)
- All requests go through `_fetchWithAuth()` which injects Bearer tokens

---

*Convention analysis: 2026-03-25*
