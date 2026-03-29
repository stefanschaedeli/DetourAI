# Feature Research

**Domain:** AI-powered road trip planner — route quality, stop selection, day planning improvements (v1.2)
**Researched:** 2026-03-28
**Confidence:** HIGH (grounded in existing codebase + established trip-planner UX patterns)

---

## Context

This is a subsequent-milestone research document. The core pipeline is fully built (9 Claude agents,
interactive stop selection, accommodation/activity/restaurant research, day-by-day guide, route
editing, SSE streaming). The v1.2 milestone targets quality and correctness improvements, not new
capabilities. Features are evaluated against the existing system's extension points.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that users assume a working AI trip planner has. Missing them makes the product feel broken
relative to the quality bar DetourAI already sets for itself.

| Feature | Why Expected | Complexity | Existing Hook |
|---------|--------------|------------|---------------|
| Activity preferences respected by all agents | User inputs travel style + wishes in the form — any agent that ignores them makes the input feel discarded | MEDIUM | `TravelRequest` carries `travel_style`; needs `user_wishes` field added + plumbed through all 9 agent prompts in `orchestrator.py` |
| No repeated stop suggestions | Route builder shows options one-by-one; suggesting a place already in the route or close to a confirmed stop is a correctness bug | LOW | `StopOptionsFinderAgent` prompt must receive the full `selected_stops` list already in Redis job state |
| Day plan reflects actual nights at stop | If user changes a stop from 1 to 3 nights the day plan must expand — static plans that ignore nights edits are obviously wrong | MEDIUM | `DayPlannerAgent` runs once at orchestration time; needs a recalculate trigger keyed to nights/stop changes |
| Map shows full route when opening a saved trip | Opening a trip and seeing a blank or mis-zoomed map is disorienting; full route must be visible on load | LOW | `fitBounds()` call missing at trip-open time; Google Maps SDK supports this natively |
| Stop overview shows the correct stop image | Stop cards with wrong or mismatched photos break trust in AI output quality | LOW | `image_fetcher.py` exists; image-to-stop assignment needs verification at render time |

### Differentiators (Competitive Advantage)

Features that go beyond commodity trip planners (Wanderlog, TripPlanner AI, Mindtrip). These justify
building DetourAI over using an off-the-shelf tool.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Strategic night distribution by destination potential | Most planners assign nights uniformly (1 per stop). DetourAI can assign 2–3 nights to a rich destination (Paris, beach resort) and 1 night to a transit stop — how experienced travellers actually plan | HIGH | `RouteArchitectAgent` prompt scores each stop's activity density against user wishes, then allocates nights proportionally; no separate algorithm needed |
| User wishes as first-class signal in every agent | Most multi-agent systems inject preferences into the orchestrator and hope they propagate. Explicit injection into each agent's system prompt produces consistently personalized output across accommodations, activities, restaurants, guide text | MEDIUM | Add `user_wishes` field to `TravelRequest` Pydantic model; thread through `orchestrator.py` context dict to all 9 agents |
| Full route context in stop-selection UI | Showing all previously confirmed stops on the map while presenting new options gives the user spatial awareness of their route progress — no commercial planner does this well | MEDIUM | `route-builder.js` map rendering; `fitBounds()` on combined bounds of confirmed + candidate markers |
| Hotel secret tips with distance enforcement | Surfacing a "secret tip" hotel 80 km from the stop is worse than useless — it destroys trust. Distance-gated secret tips (max ~15 km from stop center) are a genuine differentiator | MEDIUM | `AccommodationResearcherAgent` prompt + post-processing geocode distance check before including a secret tip |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Better Approach |
|---------|---------------|-----------------|-----------------|
| Full itinerary regeneration on any edit | Feels like the "smart" AI response | Wastes Opus-class token budget, is slow, and discards user-validated choices | Surgical recalculation: only regenerate day plans for the affected stop when nights change; stop replacements already use `replace_stop_job` for scoped re-research |
| Real-time conversational night negotiation | Chatbot UX feels modern | Adds latency + a new UI paradigm that conflicts with the existing form + route-builder flow | Encode distribution logic as explicit scoring rules in `RouteArchitectAgent` system prompt; let the AI decide once with good heuristics |
| Fuzzy-match hotel deduplication across stops | Obvious solution to "same hotel appears twice" | False positives: two different hotels with similar names in different cities | Stop-scoped deduplication only: within one stop's accommodation list, exact-name dedup; across stops no dedup needed |
| Global visited-places database across trips | Avoid recommending a city visited last year | Over-engineering for a friends-and-family product; trips often intentionally repeat popular destinations | Scope history awareness to the current trip only — stops already in `selected_stops` in the current Redis job |
| Parallel day-plan regeneration for all stops after any edit | Sounds efficient | Hammers the Anthropic API simultaneously, high latency, most stops need no regeneration | Lazy: only regenerate the day plan for the stop whose nights changed |

---

## Feature Dependencies

```
[user_wishes field in TravelRequest]
    └──required by──> [Activity preferences forwarded to all agents]
    └──required by──> [Strategic night distribution (wishes inform stop scoring)]
    └──required by──> [Stop options finder with user wishes context]

[Stop history list from Redis job state]
    └──required by──> [No repeated stop suggestions in StopOptionsFinder]

[Nights-change event / trigger]
    └──required by──> [Day plan recalculation on nights/stop change]

[Hotel stop-center geocode]
    └──required by──> [Hotel distance limit enforcement]

[Map auto-fit on trip open]
    └──independent—— frontend-only, no backend dependency

[Stop overview image fix]
    └──independent—— image_fetcher.py already exists

[Stop selection UI: show previous stops + zoom]
    └──independent—— frontend-only change in route-builder.js

[Edit button tooltips + nights edit button]
    └──independent—— frontend-only polish
```

### Dependency Notes

- **user_wishes is the foundational change.** All preference propagation work depends on the Pydantic
  model having the field. Add it first; all agents then reference it.
- **Strategic night distribution enhances user_wishes.** Richer allocation when the agent knows what
  the user cares about (beaches vs castles vs playgrounds) and can score each stop against those wishes.
- **Stop history is scoped to current trip intentionally.** The `selected_stops` array is already in
  Redis job state — no new data model needed. Cross-trip history is an anti-feature for this audience.
- **Day plan recalculation is independent of stop replacements.** `replace_stop_job` already handles
  full re-research when a stop is swapped. The new trigger is nights-only edits, which currently
  produce no plan update.

---

## v1.2 Milestone Feature Prioritization

### Must Ship (P1 — Correctness)

These are correctness failures. The product is objectively wrong without them.

- [ ] **user_wishes global field in TravelRequest** — foundation for all preference propagation; low
  surface area, high downstream impact
- [ ] **Activity preferences forwarded to all agents** — without this, user form inputs are silently
  ignored by every agent
- [ ] **Stop history awareness in StopOptionsFinder** — repeated suggestions are a correctness bug
- [ ] **Day plan recalculation on nights change** — plan/reality mismatch is a hard correctness failure
- [ ] **Map auto-fit on trip open** — disorienting blank/wrong-zoom map on load; one-call fix
- [ ] **Correct images in stop overview** — wrong images undermine trust in AI quality

### Should Ship (P2 — Quality Uplift)

High user value, moderate complexity, no hard blockers.

- [ ] **Strategic night distribution by destination potential** — biggest differentiator; requires
  good prompt engineering in `RouteArchitectAgent` with explicit scoring criteria
- [ ] **Hotel secret tips: distance limit + within-stop deduplication** — currently a trust destroyer;
  bounded fix with geocode distance post-processing
- [ ] **Stop selection UI: all previous stops visible + zoom to latest + new options** — spatial
  context that no competitor matches

### Nice to Have (P3 — Polish)

Low complexity, low risk, improves perceived quality.

- [ ] **Edit button tooltips** — discoverability for less obvious actions
- [ ] **Dedicated nights edit button** — currently done via `prompt()`; a button improves affordance
- [ ] **StopOptionsFinder performance optimization** — parallel option generation where possible

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| user_wishes field + propagation to all agents | HIGH | LOW-MEDIUM | P1 |
| Stop history in StopOptionsFinder | HIGH | LOW | P1 |
| Day plan recalculation on nights change | HIGH | MEDIUM | P1 |
| Map auto-fit on trip open | MEDIUM | LOW | P1 |
| Correct stop images | MEDIUM | LOW | P1 |
| Strategic night distribution | HIGH | HIGH | P2 |
| Hotel distance limit + dedup | MEDIUM | MEDIUM | P2 |
| Stop selection map context | HIGH | MEDIUM | P2 |
| Tooltips + nights edit button | LOW | LOW | P3 |
| StopOptionsFinder performance | MEDIUM | MEDIUM | P3 |

---

## How Intelligent Day Distribution Works in Practice

**Research finding (MEDIUM confidence):** Academic itinerary optimization systems (MDPI 2024, genetic
algorithm approaches) score POIs by "attractiveness" — a composite of attraction count, review
sentiment, activity type diversity, and user preference match. Commercial planners (Wonderplan,
Mindtrip) use LLM-based heuristics rather than explicit scoring algorithms.

**Recommended approach for DetourAI:** Encode the scoring logic directly in `RouteArchitectAgent`'s
system prompt. No separate algorithm needed — the LLM is the scorer.

The prompt should instruct the agent to:

1. Classify each stop by type: transit hub / regional center / destination city / coastal resort / nature area
2. Score each stop's "activity density" relative to the user's stated wishes — if the user wants
   "Strände, Spielplätze" a beach resort scores higher than an inland transit town
3. Assign minimum 1 night per stop; distribute remaining nights proportionally to activity density score
4. Document the distribution rationale in the returned JSON for potential display to the user

This stays within the existing agent pattern, produces explainable results, and avoids new
infrastructure. Token cost is incremental (slightly longer prompts on existing Opus calls).

---

## How Activity Preference Propagation Works in Practice

**Research finding (HIGH confidence):** The established pattern in multi-agent travel systems
(LangGraph, Mastra, Agent2Agent protocol, OpenAI Agents SDK cookbook) is "context injection at each
agent invocation" — not a shared memory bus. Each agent receives the full user preferences in its
system prompt or first user message turn.

**Current DetourAI state:** `travel_style` is passed to some agents. `user_wishes` does not exist.
The gap is: (a) add the field to `TravelRequest`, (b) thread it through `orchestrator.py`'s context
dict, (c) update each of the 9 agent system prompts to reference it.

**Recommended injection pattern (consistent across all agents):**
```
Nutzerprofile: Reisestil="{travel_style}", Wünsche="{user_wishes}"
```

The orchestrator already passes a rich context dict to each agent. Adding `user_wishes` to that dict
is minimal and correct.

---

## How Stop History Tracking Works in Practice

**Research finding (MEDIUM confidence):** Commercial planners (Furkot, Roadtrippers, Wanderlog) do
not implement stop history deduplication — they rely on the user manually avoiding repeats. This is
an unsolved UX gap in the market.

**Current DetourAI state:** Redis job state (`job:{job_id}`) already contains the full list of
confirmed stops as `selected_stops`. `StopOptionsFinderAgent` does not currently receive this list.

**Recommended approach:** Pass `selected_stops` (names + coordinates) to `StopOptionsFinderAgent`
with the instruction: "Schlage keine Orte vor, die bereits in der Route enthalten sind oder in
unmittelbarer Nähe (<20 km) einer bereits ausgewählten Station liegen."

Scope is intentionally current-trip-only. The data is already in memory — no new persistence needed.

---

## How Hotel Quality + Distance Filtering Works in Practice

**Research finding (MEDIUM confidence):** Hotel recommendation systems (academic: Springer 2024,
ResearchGate) predominantly combine distance metrics with quality scoring. Distance is cited as the
most influential feature for booking conversion. Commercial systems filter by geographic proximity
before applying quality ranking.

**Current DetourAI state:** `AccommodationResearcherAgent` generates "secret tip" hotels without a
distance constraint. The same hotel name can appear in multiple stop lists (no within-stop dedup).

**Recommended approach:**
1. In the agent prompt, explicitly constrain: "Der Geheimtipp darf maximal 15 km vom Stadtzentrum
   der Station entfernt sein."
2. In post-processing, deduplicate by hotel name within a single stop's accommodation response
   (exact match, not fuzzy).
3. The 15 km threshold is a heuristic — adjustable via `settings_store.py` if needed.

---

## Competitor Feature Analysis

| Feature | Wanderlog | TripPlanner AI | Roadtrippers | DetourAI v1.1 | DetourAI v1.2 target |
|---------|-----------|----------------|--------------|---------------|----------------------|
| Activity preference input | Free-text prompt | Category checkboxes | Category filters | Travel style dropdown | + free-text wishes field |
| Night distribution | Manual | Uniform auto | Manual | AI-decided (opaque heuristics) | AI-decided + scored by user wishes |
| Stop history awareness | None | None | None | None | Current-trip scoped |
| Hotel quality filtering | Manual search | Basic category | Manual search | Research agent (no distance limit) | + 15 km distance limit + exact dedup |
| Map context on stop selection | Static map | None | Basic route | Route map | Route + all previous stops + zoom |
| Day plan update on nights edit | Manual rebuild | Manual rebuild | N/A | No update (bug) | Auto-recalculate on nights change |
| Map fit on trip open | Yes (Wanderlog auto-fits) | Partial | Yes | No (bug) | fitBounds() on trip open |

---

## Sources

- [Building an AI-Powered Smart Travel Planner with Multi-Agent AI and LangGraph (Towards AI)](https://pub.towardsai.net/building-an-ai-powered-smart-travel-planner-with-multi-agent-ai-and-langgraph-e5994e745733) — agent architecture patterns
- [Context Engineering in Multi-Agent Systems (Agno)](https://www.agno.com/blog/context-engineering-in-multi-agent-systems) — preference propagation patterns
- [OpenAI Agents SDK — Context Personalization](https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization) — state injection patterns
- [Personalized Tour Itinerary Recommendation Algorithm (MDPI 2024)](https://www.mdpi.com/2076-3417/14/12/5195) — POI attractiveness scoring
- [Hotel Recommendation System with Machine Learning](https://medium.com/@manishsingh99923/hotel-recommendation-system-with-machine-learning-e2424f144238) — distance filtering patterns
- [Agentic AI Travel Planning with Gemini + CrewAI (Google Cloud)](https://medium.com/google-cloud/agentic-ai-building-a-multi-agent-ai-travel-planner-using-gemini-llm-crew-ai-6d2e93f72008) — multi-agent orchestration
- [AI trip planning apps system design (Coaxsoft)](https://coaxsoft.com/blog/guide-to-ai-trip-planning-apps) — commercial system design
- [Wanderlog travel planner](https://wanderlog.com/) — competitor feature baseline
- [TripPlanner AI](https://tripplanner.ai/) — competitor feature baseline
- Codebase analysis: `backend/agents/`, `backend/orchestrator.py`, `backend/models/travel_request.py`, `backend/utils/retry_helper.py`, `frontend/js/route-builder.js`

---
*Feature research for: DetourAI v1.2 — AI-Qualität & Routenplanung*
*Researched: 2026-03-28*
