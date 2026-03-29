# Phase 13: Architect Pre-Plan for Interactive Flow - Research

**Researched:** 2026-03-29
**Domain:** Python/FastAPI agent pattern, async timeout, Redis job state, prompt injection
**Confidence:** HIGH

## Summary

Phase 13 adds a lightweight pre-planning step before the first StopOptionsFinder call: a new `ArchitectPrePlanAgent` generates a region list with recommended nights per region and drive-time constraints. The result is stored in `job["architect_plan"]` in Redis and injected as a labeled context block into every subsequent `StopOptionsFinderAgent._build_prompt()` call.

All decisions are fully locked in CONTEXT.md (D-01 through D-14). The implementation is entirely additive: new file `backend/agents/architect_pre_plan.py`, modifications to `stop_options_finder.py`, `main.py`, `debug_logger.py`, and `settings_store.py`. No new libraries are needed — all patterns already exist in the codebase.

The one technical choice left to Claude's discretion is JSON schema design and exact German prompt wording. Research below provides concrete recommendations for both.

**Primary recommendation:** Copy `backend/agents/route_architect.py` as the new agent template. Use `asyncio.wait_for()` (not `asyncio.timeout()`) to wrap the agent's `run()` coroutine in `_start_leg_route_building()` for the 5-second timeout, since it works on Python 3.11 and is already used in this codebase.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Pre-plan output is an ordered list of regions with recommended nights per region and drive-time constraints. E.g. "Provence (2N, ~3h) → Côte d'Azur (3N, ~2h) → Paris (3N, ~4h)"
- **D-02:** No themes, key attractions, or driving logic in the pre-plan. Keep it lean for fast Sonnet response.
- **D-03:** Pre-plan includes max_drive_hours_per_day enforcement — no proposed region transition exceeds the user's limit.
- **D-04:** Sonnet judges destination potential using combined context: `travel_description`, `travel_styles`, `preferred_activities`, `mandatory_activities`. No new form field.
- **D-05:** Night recommendations are advisory, not binding. StopOptionsFinder sees "empfohlen: 2 Nächte" but user still picks final nights.
- **D-06:** Total nights across all regions must sum to `total_days - 1`. Sonnet gets this as a hard constraint.
- **D-07:** New `ArchitectPrePlanAgent` class in separate file `backend/agents/architect_pre_plan.py`, using Sonnet model. Existing `RouteArchitectAgent` stays untouched.
- **D-08:** Agent follows established pattern: German system prompt, `call_with_retry()`, `parse_agent_json()`, debug_logger logging.
- **D-09:** Pre-plan runs once before the first StopOptionsFinder call, inside `_start_leg_route_building()` in `main.py`.
- **D-10:** Result stored in `job["architect_plan"]` in Redis job state. All subsequent StopOptionsFinder calls for the same job read from it.
- **D-11:** StopOptionsFinder gets a new `architect_context` parameter on `_build_prompt()`. Injected as a labeled section: "ARCHITECT-EMPFEHLUNG: ..." — clean separation from route geometry data.
- **D-12:** 5-second timeout on the pre-plan call.
- **D-13:** Silent fallback on any failure (timeout, parse error, API error): log warning, set `job["architect_plan"] = None`. StopOptionsFinder runs exactly as today without architect context. User never sees the failure.
- **D-14:** No retry on failure — single attempt with 5s timeout, then fallback.

### Claude's Discretion

- Exact German system prompt wording for the new agent
- JSON output schema for the pre-plan (region names, nights, drive hours structure)
- Exact wording of the ARCHITECT-EMPFEHLUNG section injected into StopOptionsFinder prompts
- Whether to add the new agent to `_COMPONENT_MAP` in `debug_logger.py` (yes, per CLAUDE.md logging rules)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RTE-01 | Vor der Stopauswahl erstellt ein Architect Pre-Plan die Regionen und Nächte-Verteilung | New `ArchitectPrePlanAgent` — D-07, D-09 |
| RTE-02 | StopOptionsFinder erhält Architect-Kontext (Regionen, empfohlene Nächte, Route-Logik) | `architect_context` parameter on `_build_prompt()` — D-10, D-11 |
| RTE-05 | Nächte-Verteilung basiert auf Ort-Potenzial statt immer Minimum | Sonnet infers city vs scenic from existing fields — D-04, D-05, D-06 |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | >=0.28.0 | Claude API calls | Already installed; all agents use it |
| asyncio (stdlib) | Python 3.11 | `asyncio.wait_for()` for 5s timeout | Already used in codebase (line 1999 in main.py) |
| json (stdlib) | Python 3.11 | JSON parse/serialize | All agents use it |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | >=2.7.0 | Optional typed output model | Only if planner wants strong typing for the pre-plan dict |

No new dependencies needed. This phase is purely new code using existing infrastructure.

**Installation:** None required.

---

## Architecture Patterns

### Recommended Project Structure

The new agent follows the identical file layout of existing agents:

```
backend/agents/
├── _client.py                  # unchanged
├── architect_pre_plan.py       # NEW — ArchitectPrePlanAgent
├── stop_options_finder.py      # MODIFIED — architect_context parameter
├── route_architect.py          # unchanged
└── ...
```

### Pattern 1: New Agent Class

Copy `backend/agents/route_architect.py` as the closest structural analog — it's also a strategic planning agent that consumes `TravelRequest` and returns a JSON plan before any interactive steps.

**What:** Stateless agent class with `__init__(request, job_id)` and single `async def run() -> dict` method.

**When to use:** Exactly one call site in `_start_leg_route_building()`.

**Example (from route_architect.py pattern — HIGH confidence, read directly from codebase):**
```python
AGENT_KEY = "architect_pre_plan"

SYSTEM_PROMPT = (
    "Du bist ein strategischer Reiseplaner. Deine Aufgabe ist es, eine kompakte "
    "Regionsübersicht für eine Rundreise zu erstellen — geordnete Liste von Regionen "
    "mit empfohlenen Nächten und maximalen Fahrzeiten zwischen den Regionen. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

class ArchitectPrePlanAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    def _build_prompt(self) -> str:
        ...  # see Code Examples section

    async def run(self) -> dict:
        prompt = self._build_prompt()
        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="ArchitectPrePlan")
        await debug_logger.log_prompt("ArchitectPrePlan", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 1024),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ArchitectPrePlan")
        return parse_agent_json(response.content[0].text)
```

### Pattern 2: Timeout + Graceful Fallback in `_start_leg_route_building()`

**What:** `asyncio.wait_for()` wraps the agent's `run()` coroutine with a 5-second deadline. Any exception → log warning → store `None` in `job["architect_plan"]`.

**When to use:** Exactly as specified in D-12/D-13/D-14.

**Example (verified pattern from main.py line 1999 — HIGH confidence):**
```python
from agents.architect_pre_plan import ArchitectPrePlanAgent

# Inside _start_leg_route_building(), before StopOptionsFinderAgent instantiation:
architect_plan = None
# Only run pre-plan on the very first stop (job["stop_counter"] == 0) and when
# architect_plan not already cached in job state
if job.get("architect_plan") is None and job["stop_counter"] == 0:
    try:
        pre_plan_agent = ArchitectPrePlanAgent(request, job_id)
        architect_plan = await asyncio.wait_for(pre_plan_agent.run(), timeout=5.0)
        job["architect_plan"] = architect_plan
        await debug_logger.log(LogLevel.AGENT, "Architect Pre-Plan erstellt", job_id=job_id, agent="ArchitectPrePlan")
    except Exception as exc:
        await debug_logger.log(
            LogLevel.WARNING,
            f"Architect Pre-Plan fehlgeschlagen ({type(exc).__name__}) — StopOptionsFinder läuft ohne Kontext",
            job_id=job_id, agent="ArchitectPrePlan",
        )
        job["architect_plan"] = None
else:
    architect_plan = job.get("architect_plan")
```

Note: `asyncio.wait_for()` raises `asyncio.TimeoutError` (a subclass of `Exception`), so the broad `except Exception` catches it. No special import needed for `asyncio.TimeoutError`.

### Pattern 3: Architect Context Injection in `_build_prompt()`

**What:** Add optional `architect_context: dict = None` parameter. When present, inject formatted region plan before the rules block.

**When to use:** Always passed through `find_options()` / `find_options_streaming()` → `_build_prompt()`.

**Example (modeled on CTX-02/CTX-03 conditional injection already in stop_options_finder.py lines 203-205):**
```python
# New parameter added to _build_prompt():
def _build_prompt(
    self,
    ...
    route_geometry: dict,
    architect_context: dict = None,  # NEW
) -> str:
    ...
    # New block after geo_block, before rules_block:
    architect_block = ""
    if architect_context:
        regions = architect_context.get("regions", [])
        if regions:
            region_lines = []
            for r in regions:
                nights_hint = f"{r['recommended_nights']}N"
                drive_hint = f"~{r['max_drive_hours']}h" if r.get('max_drive_hours') else ""
                sep = f", {drive_hint}" if drive_hint else ""
                region_lines.append(f"{r['name']} ({nights_hint}{sep})")
            summary = " → ".join(region_lines)
            architect_block = f"\nARCHITECT-EMPFEHLUNG: {summary}\nDie Nächteangaben sind Empfehlungen — du kannst davon abweichen.\n"
```

### Pattern 4: Job State Storage for `architect_plan`

**What:** Store pre-plan dict in Redis job state using existing `save_job()` / `get_job()` pattern.

**Example (modeled on `job["region_plan"]` at main.py line 294 and 376 — HIGH confidence):**
```python
# Initial job creation — add to the job dict alongside region_plan:
"architect_plan": None,

# After successful pre-plan:
job["architect_plan"] = architect_plan
save_job(job_id, job)

# All subsequent StopOptionsFinder calls:
architect_context = job.get("architect_plan")
```

Note: `job["architect_plan"]` is set at job creation (alongside `region_plan` in line 457 of main.py). The job dict already initializes `region_plan` to `None` at line 294 and 457.

### Pattern 5: Register Agent in `_COMPONENT_MAP`

Per CLAUDE.md convention, add entry to `debug_logger.py`:

```python
"ArchitectPrePlan": "agents/architect_pre_plan",
"ArchitectPrePlanAgent": "agents/architect_pre_plan",
```

### Pattern 6: Register Agent in `settings_store.py`

Following the established agent entry pattern (lines 20-39 of settings_store.py):

```python
# In DEFAULTS dict:
"agent.architect_pre_plan.model": "claude-sonnet-4-5",
"agent.architect_pre_plan.max_tokens": 1024,

# In _RANGES dict:
"agent.architect_pre_plan.max_tokens": (512, 4096),
```

### Anti-Patterns to Avoid

- **Using `asyncio.timeout()` context manager:** Although valid in Python 3.11, `asyncio.wait_for()` is the project's established pattern (main.py line 1999) and works identically. Use `wait_for`.
- **Adding retry logic to the pre-plan:** D-14 explicitly forbids retry. `call_with_retry()` has max_attempts=5 by default — override with `max_attempts=1` OR bypass by calling the blocking function directly with `asyncio.wait_for(asyncio.to_thread(call_fn), timeout=5.0)`. But using `call_with_retry` with max_attempts=1 is cleanest and retains token logging.
- **Modifying `RouteArchitectAgent`:** D-07 locks this — existing agent is untouched.
- **Threading `architect_context` via a new agent constructor parameter:** The context is per-job, not per-agent. Pass it through `find_options()` and `find_options_streaming()` method parameters, not `__init__`.
- **Raising an exception on pre-plan failure:** D-13 requires silent fallback. Never let pre-plan failure surface to the user.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async timeout | Custom polling loop | `asyncio.wait_for(coro, timeout=5.0)` | Single line, correct cancellation semantics |
| JSON schema validation | Custom dict checker | `parse_agent_json()` + minimal key access | Already handles truncated JSON, markdown fences |
| Agent model selection | os.getenv directly | `get_model("claude-sonnet-4-5", AGENT_KEY)` | Respects TEST_MODE and settings_store overrides |
| Log routing | New logging setup | `debug_logger.log(LogLevel.X, ..., agent="ArchitectPrePlan")` | Existing component map routing |

---

## Common Pitfalls

### Pitfall 1: Pre-plan runs on every stop, not just the first

**What goes wrong:** If the pre-plan condition is not guarded, it runs before every `_start_leg_route_building()` call including subsequent stops and legs. This wastes tokens and adds 1-5s latency to every stop selection.

**Why it happens:** `_start_leg_route_building()` is called once per stop selection cycle, not just at trip start.

**How to avoid:** Guard with `if job.get("architect_plan") is None and job["stop_counter"] == 0:`. For subsequent stops, read from `job["architect_plan"]` which was already set (even if `None` on fallback).

**Warning signs:** Log shows "Architect Pre-Plan erstellt" appearing multiple times per trip.

### Pitfall 2: `asyncio.wait_for()` timeout must be correct type

**What goes wrong:** Passing `timeout=5` (int) works, but `timeout="5"` (str) raises TypeError silently caught by the broad except. Use float `5.0` to match the aiohttp pattern used everywhere else in the codebase.

**Why it happens:** `asyncio.wait_for` accepts both int and float but the codebase convention uses float (e.g., `timeout=1.0` at main.py:1999).

**How to avoid:** Always `timeout=5.0`.

### Pitfall 3: `architect_context` not passed through `find_options_streaming()`

**What goes wrong:** If `_build_prompt()` gets the new parameter but `find_options_streaming()` doesn't accept and forward it, the streaming path (which is the one actually used in `_find_and_stream_options()`) silently uses no architect context.

**Why it happens:** Both `find_options()` and `find_options_streaming()` independently call `_build_prompt()`. Both must be updated.

**How to avoid:** Add `architect_context: dict = None` to BOTH method signatures and both `_build_prompt()` call sites.

### Pitfall 4: `job["architect_plan"]` not initialized in job creation dict

**What goes wrong:** `job.get("architect_plan")` returns `None` for old jobs and new jobs alike — but `None` is also the fallback value, so the guard condition `if job.get("architect_plan") is None and job["stop_counter"] == 0` would re-trigger the pre-plan on each first-stop call for a new leg. For multi-leg trips this is a problem.

**Why it happens:** The guard must distinguish "pre-plan not yet run" (first leg) from "pre-plan ran but returned None due to failure" (fallback case). Both are `None`.

**How to avoid:** Use a sentinel: initialize job with `"architect_plan": None` and add a separate flag `"architect_plan_attempted": False`. Set flag to `True` after any attempt (success or failure). Guard becomes: `if not job.get("architect_plan_attempted") and job["stop_counter"] == 0`.

**Alternative:** Only run pre-plan for `leg_index == 0 and stop_counter == 0`. This is simpler and fits the intended use case — pre-plan is for the whole trip, not per-leg.

### Pitfall 5: `total_days - 1` constraint may not account for multi-leg trips

**What goes wrong:** The Sonnet prompt tells it nights must sum to `total_days - 1`, but for a 2-leg trip (`transit` → `transit`), only the current leg's days should constrain the night distribution for that leg's region plan.

**Why it happens:** D-06 references `total_days - 1` globally, but each `_start_leg_route_building()` call handles one leg.

**How to avoid:** Pass the current leg's days (`leg.total_days - 1`) as the nights budget constraint in the prompt, not `request.total_days - 1`. Verify by checking `request.legs[job["leg_index"]].total_days`.

### Pitfall 6: Sonnet's max_tokens set too high (wasted cost) or too low (truncation)

**What goes wrong:** The pre-plan is intentionally lean (D-02). A 10-region pre-plan JSON is ~300-500 tokens output. Setting max_tokens=4096 wastes budget; setting 256 risks truncation on longer trips.

**How to avoid:** Set `max_tokens=1024` in DEFAULTS. This is sufficient for any realistic trip (20 regions at ~50 tokens each = 1000 tokens max).

---

## Code Examples

Verified patterns from codebase (read directly from source files):

### Recommended JSON Output Schema for Pre-Plan

Based on D-01 requirements and the existing `region_plan` pattern in the codebase:

```json
{
  "regions": [
    {
      "name": "Provence",
      "recommended_nights": 2,
      "max_drive_hours": 3.0
    },
    {
      "name": "Côte d'Azur",
      "recommended_nights": 3,
      "max_drive_hours": 2.0
    },
    {
      "name": "Paris",
      "recommended_nights": 3,
      "max_drive_hours": 4.0
    }
  ],
  "total_nights": 8
}
```

Rationale: minimal schema, directly matches D-01 example format, `max_drive_hours` field enables D-03 enforcement, `total_nights` for verification. No complex nested objects.

### Recommended System Prompt for ArchitectPrePlanAgent

```python
SYSTEM_PROMPT = (
    "Du bist ein strategischer Reiseplaner. Deine Aufgabe ist es, eine kompakte "
    "Regionsübersicht für eine Reise zu erstellen: eine geordnete Liste von Regionen "
    "mit empfohlenen Übernachtungsnächten und maximalen Fahrzeiten zwischen den Regionen. "
    "KRITISCH — Nächte pro Region: Verteile die Nächte nach Potential des Ortes. "
    "Wichtige Städte und schöne Regionen bekommen mehr Nächte als reine Transitstopps. "
    "KRITISCH — Fahrzeiten: Kein Regionswechsel darf die angegebene maximale Fahrzeit überschreiten. "
    "KRITISCH — Nächtebudget: Die Summe aller empfohlenen Nächte muss exakt gleich dem angegebenen Nächtebudget sein. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)
```

### Recommended `_build_prompt()` for ArchitectPrePlanAgent

```python
def _build_prompt(self) -> str:
    req = self.request
    leg_index = 0  # Pre-plan is only called for the first transit leg
    leg = req.legs[leg_index]
    nights_budget = leg.total_days - 1

    styles_str = ", ".join(req.travel_styles) if req.travel_styles else "allgemein"
    desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
    pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
    mandatory_line = (
        f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}"
        if req.mandatory_activities else ""
    )

    return f"""Erstelle einen Regionsplan für folgende Reise:

Von: {leg.start_location}
Nach: {leg.end_location}
Nächtebudget: {nights_budget} Nächte (Summe aller Regionen MUSS exakt {nights_budget} ergeben)
Maximale Fahrzeit pro Etappe: {req.max_drive_hours_per_day}h
Reisestile: {styles_str}{desc_line}{pref_line}{mandatory_line}

Gib exakt dieses JSON zurück:
{{
  "regions": [
    {{"name": "Regionname", "recommended_nights": 2, "max_drive_hours": 3.0}},
    {{"name": "Regionname", "recommended_nights": 3, "max_drive_hours": 2.5}}
  ],
  "total_nights": {nights_budget}
}}

Regeln:
1. Summe aller recommended_nights = {nights_budget}
2. max_drive_hours pro Region <= {req.max_drive_hours_per_day}h
3. Regionen müssen logisch auf der Route zwischen {leg.start_location} und {leg.end_location} liegen
4. Verteile Nächte nach Potential: attraktive Orte bekommen mehr Nächte als Transitstopps"""
```

### How `architect_context` is Read and Passed in `_find_and_stream_options()`

The function currently has no `architect_context` parameter. It must be added as an optional kwarg and threaded through to the agent calls:

```python
# In _find_and_stream_options() signature — add:
architect_context: dict = None,

# When calling find_options_streaming():
async for item in agent.find_options_streaming(
    ...
    architect_context=architect_context,
):
```

All call sites for `_find_and_stream_options()` must also be updated to pass `architect_context=job.get("architect_plan")`.

---

## Environment Availability

Step 2.6: SKIPPED — this phase makes no changes outside the Python codebase. No external tools, services, or new CLI utilities required.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-mock + pytest-asyncio |
| Config file | None (pyproject.toml has no pytest config; tests use sys.path.insert) |
| Quick run command | `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v` |
| Full suite command | `cd backend && python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RTE-01 | `ArchitectPrePlanAgent.run()` returns valid dict with `regions` list | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_agent -x` | ❌ Wave 0 |
| RTE-01 | Pre-plan stored in `job["architect_plan"]` on success | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_stored_in_job -x` | ❌ Wave 0 |
| RTE-02 | `StopOptionsFinderAgent._build_prompt()` includes ARCHITECT-EMPFEHLUNG when context provided | unit | `pytest tests/test_agents_mock.py::test_stop_options_finder_architect_context_in_prompt -x` | ❌ Wave 0 |
| RTE-02 | `StopOptionsFinderAgent._build_prompt()` omits block when no context | unit | `pytest tests/test_agents_mock.py::test_stop_options_finder_no_architect_context -x` | ❌ Wave 0 |
| RTE-05 | Pre-plan prompt includes travel_styles and travel_description | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_prompt_includes_context -x` | ❌ Wave 0 |
| RTE-01+D-13 | Timeout/failure on pre-plan → `job["architect_plan"] = None`, no exception raised | unit | `pytest tests/test_agents_mock.py::test_architect_pre_plan_graceful_fallback -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python3 -m pytest tests/test_agents_mock.py -x -v`
- **Per wave merge:** `cd backend && python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New test functions in `backend/tests/test_agents_mock.py` — covers RTE-01, RTE-02, RTE-05, D-13
  - `test_architect_pre_plan_agent` — mock Anthropic, verify `run()` returns dict with `regions` list
  - `test_architect_pre_plan_prompt_includes_context` — verify `_build_prompt()` output contains travel_description and styles
  - `test_stop_options_finder_architect_context_in_prompt` — verify `_build_prompt()` with architect_context includes "ARCHITECT-EMPFEHLUNG"
  - `test_stop_options_finder_no_architect_context` — verify `_build_prompt()` without context does not include "ARCHITECT-EMPFEHLUNG"
  - `test_architect_pre_plan_graceful_fallback` — mock raises TimeoutError, verify no exception escapes and job["architect_plan"] is None

No new test files needed — all tests extend existing `test_agents_mock.py`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No pre-plan — StopOptionsFinder gets only geometry | Pre-plan adds regional nights-distribution context | Phase 13 | StopOptionsFinder can suggest appropriate nights for high-potential destinations |
| RouteArchitect call before interactive flow (slow, Opus) | ArchitectPrePlanAgent with 5s timeout, Sonnet, lean JSON | Phase 13 | Faster, cheaper, graceful on failure |

---

## Open Questions

1. **Multi-leg trips: should the pre-plan cover the whole trip or just the current leg?**
   - What we know: D-09 says pre-plan runs inside `_start_leg_route_building()` (per-leg entry point). D-06 references `total_days - 1`.
   - What's unclear: For a 2-leg trip (e.g., transit Liestal→Lyon, then transit Lyon→Paris), should the pre-plan cover both legs or just the active leg?
   - Recommendation: Scope to the current leg (`leg.total_days - 1`). Each leg is independent route-building. The pre-plan stored in `job["architect_plan"]` persists across stops within the same leg. When `_advance_leg()` resets job state, reset `architect_plan` and `architect_plan_attempted` too.

2. **`_find_and_stream_options()` is called from 7+ call sites — all need `architect_context` threaded through**
   - What we know: `_find_and_stream_options()` is called at main.py lines 321, 1176, 1330, 1439, 1517, 1652, 2343, 2734.
   - What's unclear: Which call sites represent "first stop of a leg" (should have context) vs. "stop replacement" or "replan" flows (may not need context).
   - Recommendation: Default `architect_context=None` at all call sites. Only `_start_leg_route_building()` passes the actual plan. All other call sites use `None`, which produces identical behavior to today.

---

## Sources

### Primary (HIGH confidence)
- Direct code read: `backend/agents/stop_options_finder.py` — `_build_prompt()` signature, existing conditional injection pattern at lines 203-205
- Direct code read: `backend/main.py` lines 301-362 — `_start_leg_route_building()` insertion point, `asyncio.wait_for()` at line 1999
- Direct code read: `backend/agents/_client.py` — `get_model()`, `get_max_tokens()` patterns
- Direct code read: `backend/utils/debug_logger.py` — `_COMPONENT_MAP` entries for new agent registration
- Direct code read: `backend/utils/settings_store.py` — `DEFAULTS` dict for new agent model/max_tokens entries
- Direct code read: `backend/utils/retry_helper.py` — `call_with_retry()` signature including `max_attempts` override
- Direct code read: `backend/tests/test_agents_mock.py` — existing test structure and `_make_single_transit_req()` helper

### Secondary (MEDIUM confidence)
- Python 3.11 stdlib docs (training knowledge, verified via local Python version check): `asyncio.wait_for()` available and used at main.py:1999

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all patterns read directly from codebase
- Architecture: HIGH — agent pattern, job state storage, and prompt injection patterns all have direct equivalents in codebase
- Pitfalls: HIGH — identified by reading `_start_leg_route_building()`, `find_options_streaming()`, and job initialization code

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (codebase-internal research; valid until codebase changes)
