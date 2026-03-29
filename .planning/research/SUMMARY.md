# Project Research Summary

**Project:** DetourAI — v1.2 AI-Qualitat & Routenplanung
**Domain:** Multi-agent AI trip planner — pipeline quality improvements on an existing production system
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Summary

DetourAI v1.2 is a quality milestone on a fully-built, production-deployed multi-agent AI trip planner. The existing stack (FastAPI, Celery, Redis, vanilla JS, 9 Claude agents, Docker Compose) requires zero new libraries — all v1.2 improvements are achievable via Python arithmetic, prompt engineering, and frontend JavaScript changes. The research confirms a clean upgrade path: the hardest problems are architectural gaps in the interactive route-builder that were never addressed in v1.1 — no architect pre-planning step in the interactive flow, incomplete context forwarding to most agents, and no day-plan recalculation after nights edits.

The recommended approach follows a strict dependency order: fix context forwarding first (pure prompt changes, no structural risk), then introduce the architect pre-plan step for the interactive flow, then improve night distribution using that plan, then add the day recalculation endpoint, and finally ship the frontend-only UI fixes. This order ensures each phase builds on stable foundations and the riskiest architectural change (adding a new async step to the plan-trip critical path) is isolated in the middle of the sequence with graceful degradation built in from the start.

The primary risks are arithmetic correctness (arrival_day must be recomputed after every nights change or the entire downstream pipeline produces wrong booking dates), streaming fragility (the brace-counting parser in StopOptionsFinder breaks if richer prompts cause Claude to add any non-JSON preamble), and Redis concurrency (a recalculation endpoint writing concurrently with an active Celery job causes a phantom-data race). All three risks have clear, inexpensive mitigations that must be built into the relevant phases as hard requirements, not afterthoughts.

---

## Key Findings

### Recommended Stack

No new packages or libraries are required. The full v1.2 feature set is implemented using: Python `math` stdlib (night distribution arithmetic, haversine distance validation), the existing `anthropic>=0.28.0` SDK (prompt caching via `cache_control` blocks on static system prompts), the Google Maps JS SDK already in the codebase (`fitBounds()` with padding object, `idle` event listener for correct timing), and Pydantic v2 field extensions (`Optional[str]` on `TravelRequest`). The only new backend files are an optional `backend/utils/route_utils.py` for the night distribution helper and one new Celery task file `backend/tasks/recalculate_days.py`.

**Core technologies (extend, do not replace):**
- `Python math stdlib`: Night distribution weighting and haversine distance check — no scipy/numpy needed, 6-line formula is sufficient
- `anthropic>=0.28.0` SDK: Prompt caching on static system prompts — 90% cost reduction on repeated stop-finder calls, no version bump required
- `Google Maps JS SDK` (`fitBounds`, `idle` event): Auto-fit map viewport on trip open and route builder — already used at 3 locations in maps.js, only correct timing missing
- `Pydantic>=2.7.0`: `Optional[str] global_wishes` field on `TravelRequest` — trivial model extension, high downstream impact
- `CSS [data-tooltip]::after` pseudo-element: Zero-dependency tooltip for edit buttons — 15 lines of CSS, no JS library needed

**Explicitly rejected (with rationale):**
- `scipy` / `numpy` / OR-Tools for night distribution — stdlib math handles bounded integer allocation; these add 50MB+ to the Docker image
- `langchain` / agent frameworks — clean custom agent pattern is already in production; abstractions would obscure logic and add a large dependency graph
- `tippy.js` or any tooltip library — zero benefit over CSS `[data-tooltip]::after`; the project has zero frontend JS dependencies
- WebSockets to replace SSE — SSE is simpler, unidirectional, already deployed; no bidirectional communication is needed for v1.2

See `.planning/research/STACK.md` for full rationale and version compatibility table.

### Expected Features

Based on codebase analysis, multi-agent AI system research, and competitor feature review (Wanderlog, TripPlanner AI, Roadtrippers).

**Must have (P1 — correctness failures):**
- `travel_description` / `preferred_activities` / `mandatory_activities` forwarded to all 9 agents — user form inputs currently silently ignored by most agents
- Stop history awareness in StopOptionsFinder — duplicate city suggestions are a correctness bug, not a UX issue
- Day plan recalculation on nights change — plan/reality mismatch after a nights edit is a hard failure
- Map auto-fit on trip open — blank or wrong-zoom map on load is disorienting
- Correct stop images in overview — wrong images undermine trust in AI output quality

**Should have (P2 — quality uplift):**
- Strategic night distribution by destination potential — assign 3 nights to Paris, 1 night to a transit town; biggest differentiator over commodity planners
- Hotel Geheimtipp distance enforcement — currently prompt-only; add server-side haversine validation to prevent 40-60 km "secret tips"
- Route-builder map shows all previous stops plus new options with correct zoom

**Defer (v2+):**
- Real-time conversational night negotiation (conflicts with existing form flow; chatbot UX adds latency)
- Global visited-places database across trips (over-engineering for friends-and-family audience; current-trip scope is correct)
- Parallel day-plan regeneration for all stops after any edit (hammers Anthropic API simultaneously; lazy recalculation is correct)
- Fuzzy hotel deduplication across stops (false positives outweigh benefit; within-stop exact dedup is sufficient)

See `.planning/research/FEATURES.md` for full dependency graph and competitor feature comparison.

### Architecture Approach

The codebase has two separate code paths: an interactive route-builder (`main.py`) that uses StopOptionsFinder only, and a Celery background planning path (`orchestrator.py`) that uses RouteArchitect and all agents in sequence. The v1.2 architectural gap is that the interactive path has no equivalent pre-planning step — StopOptionsFinder has no architect context, no wishes forwarding, and no stop history beyond a flat name list. The recommended approach inserts a lightweight Sonnet-based pre-plan call at the start of the interactive flow (stored in `job["architect_plan"]`), enriches StopOptionsFinder's prompt with that context and the missing wishes fields, and adds a new recalculate-days endpoint that re-runs DayPlannerAgent using research data from SQLite (not Redis, which may have expired).

**Major components changed by v1.2:**
1. `main.py` `/api/plan-trip` — add architect pre-plan step before the first StopOptionsFinder call
2. `StopOptionsFinderAgent._build_prompt()` — add architect context, wishes fields, enriched history block
3. `DayPlannerAgent` — expose recalculate path via new Celery task and endpoint
4. `AccommodationResearcherAgent` — add lat/lon to Geheimtipp JSON schema + haversine post-processing
5. `RestaurantsAgent`, `TravelGuideAgent`, `DayPlannerAgent` — add missing `travel_description` / `preferred_activities` prompt blocks

**New files:**
- `backend/tasks/recalculate_days.py` — Celery task for lightweight day plan re-run
- `backend/utils/route_utils.py` — `recompute_arrival_days()` and `distribute_nights()` helpers (optional extraction; logic may stay inline)

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, build order, and component responsibility table.

### Critical Pitfalls

1. **Nights arithmetic / arrival_day cascade** — When nights change at any stop, `arrival_day` for all subsequent stops must be recomputed. Currently no utility does this. Wrong arrival_day silently corrupts hotel booking URLs and day plan headings throughout the guide. Mitigation: write `recompute_arrival_days(stops)` utility before any redistribution logic is added anywhere.

2. **Streaming parser fragile under prompt growth** — `find_options_streaming()` uses a brace-counting parser anchored to `"options"\s*:\s*\[`. Any non-JSON preamble from Claude breaks it, causing options to appear all at once instead of streamed. Mitigation: test streaming in TEST_MODE after every prompt change; add timeout-based `stream_slow` SSE fallback if no option appears within N seconds.

3. **Redis concurrency on recalculation** — `_load_job()` / `_save_job()` use plain GET/SETEX with no locking. A recalculation endpoint writing concurrently with an active Celery worker causes phantom data. Mitigation: gate the recalculation endpoint behind `job["status"] == "complete"` check; return HTTP 409 if the job is still running.

4. **Stale job state after partial updates** — Research cached in Redis for a 2-night stop is silently reused after nights change to 4. Mitigation: treat recalculation as full invalidation of the affected stop's cached research; use `needs_replan: true` flags to scope what gets re-run.

5. **Activity wishes silently ignored** — `preferred_activities` and `travel_description` do not reach StopOptionsFinder, RestaurantsAgent, DayPlannerAgent, or TravelGuideAgent. No existing test verifies that wishes appear in agent prompts. Mitigation: audit all 9 agents' `_build_prompt()` before shipping the UI field; add `test_agents_mock.py` assertions that wishes text appears in each captured prompt.

See `.planning/research/PITFALLS.md` for all 8 critical pitfalls with detection signs, recovery strategies, and a pitfall-to-phase mapping.

---

## Implications for Roadmap

Research points to a 5-phase structure where each phase builds on the previous one's stable foundation. Phases 1 and 5 are bookends of pure, low-risk changes; Phases 2-4 contain the architectural work in dependency order.

### Phase 1: Context Infrastructure and Wishes Forwarding

**Rationale:** Pure prompt changes — lowest risk, no structural code changes. All other improvements (night distribution, stop history, Geheimtipp quality) produce better output when the agents receive proper context. This is the prerequisite foundation for everything else. Shipping this first also means the form field and backend model change are tested in isolation before more complex work starts.
**Delivers:** All 9 agents receive `travel_description`, `preferred_activities`, `mandatory_activities` consistently. New optional global wishes textarea added to the trip form.
**Addresses:** P1 feature "Activity preferences respected by all agents"; Architecture Gap 5 (wishes not consistently forwarded)
**Avoids:** Pitfall 5 (field exists on TravelRequest but agents don't read it — audit all 9 agents before shipping the UI field)
**Research flag:** Skip research-phase — changes are pure prompt additions in well-understood agent files.

### Phase 2: Architect Pre-Plan for Interactive Flow

**Rationale:** Depends on Phase 1 context-forwarding pattern being established. This is the most architecturally significant change — it inserts a new async step into the critical path of `/api/plan-trip`. Must use Sonnet (not Opus) to stay under 2-3 second latency budget. Must degrade gracefully — StopOptionsFinder continues without architect context on timeout or error. Pre-plan runs in parallel with SSE connection setup; `planning_started` event fires immediately so the client does not see silence.
**Delivers:** `job["architect_plan"]` in Redis job state containing region recommendations and suggested nights. StopOptionsFinder uses this context for all subsequent calls in the same session.
**Addresses:** Architecture Gap 1 (no architect context in interactive flow); P2 feature "full route context in stop-selection UI"
**Avoids:** Anti-pattern "running Opus in the interactive critical path" (use Sonnet for pre-plan, 2-3s not 10-15s); Anti-pattern "blocking SSE during pre-plan" (fire `planning_started` immediately, run pre-plan asynchronously)
**Research flag:** Needs latency validation before finalizing approach — measure how long a lightweight Sonnet pre-plan takes in TEST_MODE; if it exceeds 3 seconds, apply architect context starting from stop 2 instead.

### Phase 3: Stop History Awareness and Night Distribution

**Rationale:** Depends on Phase 2 architect_plan being available in job state. History enrichment and night distribution both feed off the same new job state field and both live in `StopOptionsFinderAgent._build_prompt()`. Grouped together to minimize the number of times the streaming validation test must be run.
**Delivers:** StopOptionsFinder receives enriched history (names + travel style tag coverage + architect remaining recommendations). Night allocation uses architect plan's suggested nights per region. Post-processing dedup prevents duplicate city suggestions.
**Addresses:** P1 "No repeated stop suggestions"; P2 "Strategic night distribution"; Architecture Gaps 2 and 3
**Avoids:** Pitfall 3 (streaming parser breaks under richer prompts — run streaming validation as definition-of-done gate); Pitfall 4 (duplicate city proposals — add post-processing dedup guard in `find_options()` in addition to prompt constraint); Pitfall 8 (token cost spike — cap history to last 5 stops in full detail, summarize older ones to `region (country)` tuples)

### Phase 4: Hotel Geheimtipp Quality and Day Plan Recalculation

**Rationale:** Two independent improvements bundled here because they both require new backend code (haversine validation and a new Celery task) but neither depends on Phases 2-3. Day recalculation is placed after the pipeline is stable because it must load existing research data from SQLite correctly and must not conflict with active Celery jobs.
**Delivers:** Geheimtipp options include lat/lon in JSON schema; haversine post-processing drops options exceeding `hotel_radius_km * 1.5`. New `POST /api/travels/{id}/recalculate-days` endpoint and `tasks/recalculate_days.py` Celery task. Frontend triggers recalculation after nights edit and shows SSE progress feedback.
**Addresses:** P1 "Day plan reflects actual nights"; P2 "Hotel secret tips distance enforcement"; Architecture Gaps 4 and 6
**Avoids:** Pitfall 1 (`recompute_arrival_days()` utility must exist before this phase ships — write it first); Pitfall 2 (stale Redis state — invalidate affected stop research; use `needs_replan: true` flags); Pitfall 6 (race condition — gate recalculation on `status == "complete"`, return 409 otherwise); Pitfall 7 (Geheimtipp distance prompt-only — add server-side haversine in `enrich_option()`)
**Research flag:** Skip research-phase — Celery task pattern has three existing templates in the codebase. Haversine is stdlib math.

### Phase 5: Frontend UI Fixes and Polish

**Rationale:** All frontend-only changes. No backend dependencies. Placed last so the backend pipeline is fully stable before UI work begins. Each fix is independent and can be shipped incrementally within this phase.
**Delivers:** Map auto-fit on trip open (`fitBounds` with `idle` listener for correct timing). Route-builder shows all previous stops with correct zoom to latest selection plus new options. Stop overview images verified against correct stop. CSS `[data-tooltip]` on edit buttons. Dedicated nights edit button replacing `prompt()` dialog with proper validation (clamp to min/max_nights_per_stop).
**Addresses:** P1 "Map auto-fit on trip open", "Correct stop images"; P3 "Edit button tooltips", "Dedicated nights edit button"; P2 "Stop selection map context"
**Avoids:** UX pitfall "map auto-fit animates before stops are rendered" (wait for `idle` event, not a timeout); UX pitfall "stop-finder shows all previous stops creating clutter for 8+ stop trips" (dim previously selected markers using existing opacity logic from guide-map module)
**Research flag:** Skip research-phase — `fitBounds` with padding object confirmed in official Google Maps docs and already used at 3 locations in maps.js.

### Phase Ordering Rationale

- **Phase 1 before all others:** Context forwarding is the dependency of dependencies. Adding a form field that has no effect on agent output is a trust-destroying anti-pattern. Build the plumbing first; the form field ships last in Phase 1 after the agent changes are tested.
- **Phase 2 before Phase 3:** Night distribution requires architect_plan in job state. Stop history enrichment is more powerful when it can reference architect remaining recommendations. Both feed from the same new data structure established in Phase 2.
- **Phase 4 independent:** Day recalculation and Geheimtipp validation have no dependency on Phases 2-3. They are placed sequentially here to keep Celery task complexity from overlapping with Phase 3's streaming validation risk.
- **Phase 5 last:** Pure UI — zero backend risk, zero regression surface on the pipeline. Any phase can be safely delivered while Phase 5 work is in progress.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Architect Pre-Plan):** The new async step's latency characteristics and SSE interaction need empirical validation before committing to the implementation. Specifically: how long does a lightweight Sonnet pre-plan call take in TEST_MODE, and does the existing SSE connection setup tolerate a 2-3 second upstream delay without client-side timeout retries triggering?

Phases with standard patterns (skip research-phase):
- **Phase 1 (Context Forwarding):** Pure prompt engineering in existing files. Established pattern in the codebase and in multi-agent AI literature.
- **Phase 3 (History/Nights):** Extension of existing `_build_prompt()` patterns in StopOptionsFinder. Token-cap heuristic (last 5 stops in full detail) is empirical, not a research question.
- **Phase 4 (Recalculation/Geheimtipp):** Celery task pattern has three existing templates to mirror. Haversine is stdlib math. SQLite update path needs careful review but no external research needed.
- **Phase 5 (UI Fixes):** All patterns confirmed in official Google Maps docs and already present in the codebase.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies; all implementation uses existing library features confirmed in official docs and verified in codebase |
| Features | HIGH | Grounded in direct codebase analysis; competitor feature comparison anchors prioritization; dependency graph traced to specific Redis keys and agent files |
| Architecture | HIGH | All findings based on direct source reading of affected files with line-level evidence; no inference or speculation |
| Pitfalls | HIGH | All 8 pitfalls derived from direct codebase analysis of known fragile code paths (`_load_job`/`_save_job`, streaming parser, `arrival_day` field); no speculative risks |

**Overall confidence:** HIGH

### Gaps to Address

- **Architect pre-plan latency budget:** Research recommends Sonnet for the pre-plan step but does not provide a measured baseline. Validate that the first stop option still appears within 3-4 seconds total (pre-plan + StopOptionsFinder) before committing to the Phase 2 approach. If latency is unacceptable, the fallback is to run the pre-plan in parallel with the first StopOptionsFinder call and apply its context starting from stop 2.
- **`stop["lat"]` / `stop["lon"]` availability:** Architecture research flags that Route Architect stops may not have lat/lon until DayPlannerAgent enrichment runs. For Geheimtipp haversine validation (Phase 4), the stop coordinates must come from the stop-finder selection (which always geocodes), not from the Route Architect. Verify the `selected_stops` dict structure confirms lat/lon is always present before writing the validation code.
- **arrival_day in existing saved travels:** If the `recompute_arrival_days()` utility reveals that existing SQLite travels have incorrect arrival_day values due to v1.1 nights edits, a one-time migration script may be needed. Scope this at the start of Phase 4 implementation.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — `backend/agents/stop_options_finder.py`, `backend/agents/accommodation_researcher.py`, `backend/orchestrator.py`, `backend/main.py`, `backend/models/travel_request.py`, `frontend/js/maps.js`, `frontend/js/route-builder.js`
- [Anthropic Prompt Caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — `cache_control: {"type": "ephemeral"}`, 5-min TTL, 90% cost reduction on static system prompt prefixes
- [Anthropic Context Engineering blog](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — structured history injection in user turn as canonical stateless pattern
- [Google Maps JS API `Map.fitBounds()`](https://developers.google.com/maps/documentation/javascript/reference/map#Map.fitBounds) — padding object `{top, right, bottom, left}` confirmed; `idle` event as correct timing hook

### Secondary (MEDIUM confidence)
- [Personalized Tour Itinerary Recommendation (MDPI 2024)](https://www.mdpi.com/2076-3417/14/12/5195) — POI attractiveness scoring; supports prompt-based scoring approach over algorithmic optimization
- [Context Engineering in Multi-Agent Systems (Agno)](https://www.agno.com/blog/context-engineering-in-multi-agent-systems) — per-invocation context injection as preferred pattern over shared memory bus
- [Hotel Recommendation System (ResearchGate / Springer 2024)](https://medium.com/@manishsingh99923/hotel-recommendation-system-with-machine-learning-e2424f144238) — distance as primary booking-conversion feature; validates 15 km threshold for Geheimtipp filtering

### Tertiary (LOW confidence — not relied upon for roadmap decisions)
- Commercial competitor analysis (Wanderlog, TripPlanner AI, Roadtrippers) — feature baseline; confirms stop history deduplication is an unsolved gap in the market, which supports building it as a differentiator

---
*Research completed: 2026-03-28*
*Ready for roadmap: yes*
