# backend/agents/CLAUDE.md

This worker owns `backend/agents/`, `backend/orchestrator.py`, and `backend/tasks/`.
Do NOT modify `backend/main.py`, `backend/models/`, `backend/utils/` (exception: `debug_logger.py` for component registration only), or `frontend/`.
Reads (not modifies): `backend/models/` for Pydantic type contracts.

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

## Agent Class Pattern

Every agent follows this structure:

```python
class MyAgent:
    AGENT_KEY = "MyAgent"
    SYSTEM_PROMPTS = {
        "de": "Du bist ...",
        "en": "You are ...",
        "hi": "आप ...",
    }

    def __init__(self, job_id: str, locale: str = "de"):
        self.job_id = job_id
        self.locale = locale
        self.client = get_client()
        self.model = get_model(prod="claude-sonnet-4-5", key=self.AGENT_KEY)

    async def run(self, ...) -> dict:
        prompt = self._build_prompt(...)
        debug_logger.log(LogLevel.API, "Calling Claude", job_id=self.job_id, agent=self.AGENT_KEY)
        response = await call_with_retry(
            self.client.messages.create,
            model=self.model,
            system=self.SYSTEM_PROMPTS[self.locale],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return parse_agent_json(response.content[0].text)
```

## Key Utilities

- `get_client()` — returns shared `anthropic.Anthropic` instance (`agents/_client.py`)
- `get_model(prod, key)` — returns `prod` model in production, `claude-haiku-4-5` when `TEST_MODE=true`
- `call_with_retry(fn, ...)` — wraps blocking Claude calls with exponential backoff on 429/529
- `parse_agent_json(text)` — strips markdown fences, detects + repairs truncated JSON

## Logging Registration

For every new agent, add to `_COMPONENT_MAP` in `backend/utils/debug_logger.py`:
```python
"MyAgentName": "agents/my_agent",
```

Then log via:
```python
debug_logger.log(LogLevel.AGENT, "startet", job_id=self.job_id, agent=self.AGENT_KEY)
debug_logger.log_prompt(self.AGENT_KEY, self.model, prompt, job_id=self.job_id)
```

## Orchestration Pipeline

`TravelPlannerOrchestrator` runs after route + accommodations confirmed:

```
RouteArchitect (route building — interactive, per stop)
    ↓
RegionPlanner (region-based routing, if needed)
    ↓ (parallel)
AccommodationResearcher × N stops
    ↓ (parallel)
ActivitiesAgent + RestaurantsAgent + TravelGuideAgent × N stops
    ↓
DayPlannerAgent (sequential, per leg, uses Google Directions)
    ↓
TripAnalysisAgent (optional, non-blocking — failure continues pipeline)
```

## Celery Task Pattern

Each Celery task wraps an async orchestration function:

```python
@celery_app.task(name="tasks.run_planning_job.run_planning_job_task")
def run_planning_job_task(job_id: str) -> None:
    asyncio.run(_run_async(job_id))
```

Events pushed to Redis list `sse:{job_id}` for the SSE endpoint to drain.
Without Redis: events go to `asyncio.Queue` via `debug_logger._local_push()`.

## Agent Output Rules

- Agents ALWAYS return valid JSON — no markdown wrappers, no explanations
- System prompts to Claude: use `SYSTEM_PROMPTS[locale]` dict (de/en/hi)
- `parse_agent_json()` handles stripping fences if Claude wraps output anyway
- Truncated JSON (brace count mismatch) is detected and repair is attempted

## Prompt Language

- System prompts written in German (de), English (en), and Hindi (hi)
- Match locale to `self.locale` passed at construction time
- Default locale is `"de"` if not specified
