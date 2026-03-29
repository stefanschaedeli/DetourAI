# Milestone v1.2 — Project Summary

**Generated:** 2026-03-29
**Purpose:** Team onboarding and project review

---

## 1. Project Overview

**DetourAI** is an AI-powered road trip planner for friends and family. Users configure a trip (start, destination, duration, budget, travel style), then 9 specialized Claude agents collaboratively build the route, research accommodations/activities/restaurants, and produce a day-by-day travel guide. Features interactive route building with stop selection, map-centric responsive layout, route editing, public shareable trip links, and geographic intelligence for island/ferry destinations. Real-time progress via SSE.

**Core Value:** Route planning and stop discovery must produce consistently high-quality, geographically correct results for any destination type — mainland, coastal, and island regions alike.

**Target Users:** Friends and family circle (personal project, not a public product).

**Stack:** Python/FastAPI backend · Vanilla JS frontend (no framework) · Redis job state · Celery workers · Nginx static serving · Docker Compose deployment · Anthropic Claude AI (Opus/Sonnet)

**v1.2 Goal:** Die AI-gesteuerte Routenplanung und Stop-Auswahl grundlegend verbessern — intelligentere Tagesverteilung, bessere Kontextweiterleitung, und UI-Korrekturen für eine nutzbare Reiseplanung.

**Status:** 4 of 5 phases complete. Phase 16 (Frontend UI Fixes + Polish) remains.

---

## 2. Architecture & Technical Decisions

### Multi-Agent AI Orchestration
- **9 specialized Claude agents** handle route planning, stop options, region planning, accommodation research, activities, restaurants, day planning, travel guide writing, and trip analysis
- **Model assignment:** Opus for strategic agents (RouteArchitect, RegionPlanner, DayPlanner), Sonnet for research agents (StopOptionsFinder, AccommodationResearcher, etc.)
- **TEST_MODE=true** switches all agents to Haiku for cheap development

### Key v1.2 Architectural Decisions

- **Wishes forwarding via prompt injection (Phase 12):** All 9 agents receive `travel_description`, `preferred_activities`, and `mandatory_activities` through conditional prompt blocks. Routing agents include location in mandatory_activities formatting; content agents use name-only.
  - **Why:** Users need their preferences to influence every agent's output
  - **Phase:** 12

- **ArchitectPrePlanAgent using Sonnet with 5s timeout (Phase 13):** Lightweight pre-plan runs once before the first StopOptionsFinder call. Creates ordered regions list with recommended nights per region based on destination potential.
  - **Why:** Stay under 2-3s latency budget; Opus would be too slow for a pre-planning step
  - **Phase:** 13

- **Silent fallback on pre-plan failure (Phase 13):** If ArchitectPrePlanAgent times out or errors, StopOptionsFinder proceeds without architect context. No retry (max_attempts=1).
  - **Why:** Pre-plan is enhancement, not requirement; user should never be blocked by it
  - **Phase:** 13

- **KRITISCH exclusion rule for stop deduplication (Phase 14):** Prompt-level instruction listing all already-selected stops. Post-processing dedup as safety net (case-insensitive name match).
  - **Why:** Prompt is primary guard; post-processing catches edge cases where Claude ignores constraints
  - **Phase:** 14

- **History capping at 8 stops (Phase 14):** When >8 stops selected, show only last 5 in prompt context, but exclusion rule always uses full list.
  - **Why:** Keeps prompt concise while maintaining dedup correctness
  - **Phase:** 14

- **Prompt-level coordinates as primary Geheimtipp fix (Phase 15):** Include explicit stop lat/lon in accommodation researcher prompt ("Stopzentrum: 47.38°N, 8.54°E"). Haversine post-filter is secondary safety net.
  - **Why:** Root cause was prompt quality — Claude lacked concrete geographic reference
  - **Phase:** 15

- **Inline nights editor replacing prompt() (Phase 15):** DOM-built number input with confirm/cancel buttons. Triggers backend Celery task for arrival_day rechaining + day plan refresh via SSE.
  - **Why:** prompt() is poor UX; proper editing needs server-side state management
  - **Phase:** 15

- **Name-based dedup over coordinate-based (Phase 15):** Case-insensitive exact name match for hotel dedup. No lat/lon added to AccommodationOption model.
  - **Why:** False positives from coordinate matching outweigh benefits; within-stop exact name match is sufficient
  - **Phase:** 15

---

## 3. Phases Delivered

| Phase | Name | Status | One-Liner |
|-------|------|--------|-----------|
| 12 | Context Infrastructure + Wishes Forwarding | ✓ Complete | Global wishes field in trip form; all 9 agents receive travel_description, preferred_activities, mandatory_activities |
| 13 | Architect Pre-Plan for Interactive Flow | ✓ Complete | Lightweight Sonnet pre-plan creates region/nights recommendations before first stop selection |
| 14 | Stop History Awareness + Night Distribution | ✓ Complete | StopOptionsFinder knows all previous stops; dedup safety net; nights-remaining display in route builder |
| 15 | Hotel Geheimtipp Quality + Day Plan Recalculation | ✓ Complete | Haversine distance filter for Geheimtipps; inline nights editor with Celery-based day plan recalculation |
| 16 | Frontend UI Fixes + Polish | ○ Not started | Map fitBounds on route load, correct stop images, tooltips, stop selection map with history |

### Phase Detail

**Phase 12 — Context Infrastructure + Wishes Forwarding**
- 2 plans, 2 waves
- Added preferredTags state with tag-chip UI in Step 2
- Conditional prompt injection in all 8 agent files (9th agent gets context via orchestrator)
- 295 tests passing after completion

**Phase 13 — Architect Pre-Plan for Interactive Flow**
- 2 plans, 2 waves
- New `ArchitectPrePlanAgent` class with German SYSTEM_PROMPT
- Wired into `_start_leg_route_building()` with 5s timeout and silent fallback
- ARCHITECT-EMPFEHLUNG block injected into StopOptionsFinder prompts
- 304 tests passing after completion

**Phase 14 — Stop History Awareness + Night Distribution**
- 2 plans, 1 wave (parallel)
- KRITISCH exclusion rule in StopOptionsFinder prompt
- Post-processing dedup in `_enrich_one`
- Per-stop nights recommendation using position math against architect plan
- Frontend "X Nächte verbleibend" display in route builder
- 307 tests passing after completion

**Phase 15 — Hotel Geheimtipp Quality + Day Plan Recalculation**
- 3 plans, 2 waves
- Prompt coordinate hint + haversine post-filter for Geheimtipps
- New `update_nights_job.py` Celery task with `recalc_arrival_days()` + `run_day_planner_refresh()`
- POST `/api/travels/{id}/update-nights` endpoint with edit lock
- Inline nights editor replacing `prompt()` with SSE progress
- 319 tests passing after completion

---

## 4. Requirements Coverage

### Context Forwarding (3/3)
- ✅ **CTX-01**: User kann globale Aktivitätswünsche als Freitext im Trip-Formular eingeben — Phase 12
- ✅ **CTX-02**: `travel_description` und `preferred_activities` werden an alle 9 Agents weitergeleitet — Phase 12
- ✅ **CTX-03**: `mandatory_activities` werden an StopOptionsFinder und ActivitiesAgent weitergeleitet — Phase 12

### Route Intelligence (4/5)
- ✅ **RTE-01**: Vor der Stopauswahl erstellt ein Architect Pre-Plan die Regionen und Nächte-Verteilung — Phase 13
- ✅ **RTE-02**: StopOptionsFinder erhält Architect-Kontext (Regionen, empfohlene Nächte, Route-Logik) — Phase 13
- ✅ **RTE-03**: StopOptionsFinder kennt alle bisherigen Stops und schlägt keine Duplikate vor — Phase 14
- ✅ **RTE-04**: Post-Processing Dedup verhindert doppelte Städte als Safety Net — Phase 14
- ✅ **RTE-05**: Nächte-Verteilung basiert auf Ort-Potenzial statt immer Minimum — Phase 13

### Budget & Tagesplanung (3/3)
- ✅ **BDG-01**: `arrival_day` wird bei jeder Nächte-Änderung korrekt neu berechnet — Phase 15
- ✅ **BDG-02**: User kann Nächte pro Stop anpassen (dedizierter Edit-Button) — Phase 15
- ✅ **BDG-03**: Tagesplan wird nach Nächte- oder Stop-Änderungen neu berechnet (Celery Task) — Phase 15

### Unterkunftsqualität (2/2)
- ✅ **ACC-01**: Hotel-Geheimtipps werden serverseitig per Haversine auf Entfernung validiert — Phase 15
- ✅ **ACC-02**: Geheimtipp-Duplikate innerhalb eines Stops werden entfernt — Phase 15

### UI/UX (0/4 — Phase 16 pending)
- ○ **UIX-01**: Karte beim Öffnen einer Reise auf Route fokussiert (fitBounds)
- ○ **UIX-02**: Korrekte Bilder in der Stopp-Übersicht
- ○ **UIX-03**: Tooltips für alle Stop-Edit-Buttons
- ○ **UIX-04**: Bei Stopauswahl: alle bisherigen Stops sichtbar, Zoom auf letzte + neue Optionen

**Summary:** 12/16 requirements complete (75%). Remaining 4 are all in Phase 16 (UI/UX polish).

---

## 5. Key Decisions Log

| ID | Decision | Phase | Rationale |
|----|----------|-------|-----------|
| D-01 (P12) | Three distinct wishes fields (travel_description, preferred_activities, mandatory_activities) | 12 | Different semantic purposes; structured tag input for activities vs free text for description |
| D-07 (P12) | All agents get all 3 wishes fields | 12 | Maximum context for every agent; conditional injection only adds text when fields are non-empty |
| D-01 (P13) | Pre-plan is ordered regions list with nights/drive constraints | 13 | Lightweight structure StopOptionsFinder can consume directly |
| D-07 (P13) | New ArchitectPrePlanAgent using Sonnet | 13 | Sonnet fast enough for 2-3s budget; Opus too slow |
| D-12 (P13) | 5-second timeout with silent fallback | 13 | Enhancement, not requirement — never block user |
| D-01 (P14) | KRITISCH exclusion rule in prompt | 14 | Prompt-level dedup is primary guard |
| D-09 (P14) | History capping: last 5 shown when >8, full list for exclusion | 14 | Prompt conciseness vs dedup correctness |
| D-01 (P15) | Explicit lat/lon coordinates in accommodation prompt | 15 | Root cause was missing geographic anchor |
| D-02 (P15) | Haversine post-filter: silent drop, no retry | 15 | Honest: show 3 options instead of 4, don't retry |
| D-05 (P15) | Name-based dedup (no lat/lon on model) | 15 | False positives from coordinate matching outweigh benefits |

---

## 6. Tech Debt & Deferred Items

### Known Tech Debt
- **REQUIREMENTS.md traceability:** ACC-01 and ACC-02 still marked "Pending" in traceability table despite being implemented in Phase 15 (documentation-only issue)
- **RTE-03/RTE-04 traceability:** Also marked "Pending" in REQUIREMENTS.md despite Phase 14 completion (same documentation drift)
- **Router `_travelTab` drill state reset:** Low severity edge case from v1.1 — not yet addressed

### Deferred Ideas
- **CONV-01**: Echtzeit-Verhandlung über Nächte-Verteilung im Chat-Format (v2+)
- **CONV-02**: Globale besuchte-Orte-Datenbank über Trips hinweg (v2+)
- **PARA-01**: Parallele Tagesplan-Regenerierung für alle Stops nach jeder Änderung (v2+)
- **Stopfinder Performance-Optimierung**: Listed in PROJECT.md target features but not assigned to any phase

### Out of Scope (confirmed)
| Feature | Reason |
|---------|--------|
| Fuzzy Hotel-Deduplizierung über Stops | False positives outweigh benefits |
| Chatbot-UX für Nächte-Verhandlung | Conflicts with form flow; adds latency |
| Scipy/numpy for night distribution | stdlib math sufficient; 50MB+ Docker overhead |
| LangChain/Agent-Frameworks | Clean custom agent patterns already in production |
| Tooltip-JS-Library (tippy.js) | CSS `[data-tooltip]::after` sufficient; zero frontend dependencies |

### Lessons from v1.0 and v1.1 (still applicable)
1. Integration wiring should be verified continuously, not just at milestone boundaries
2. Browser/human verification catches real issues that automated checks miss
3. Module split before UI redesign is essential

---

## 7. Getting Started

### Run the Project

```bash
# Backend (dev mode)
cd backend && python3 -m uvicorn main:app --reload --port 8000

# Full stack (Docker)
docker compose up --build

# Tests
cd backend && python3 -m pytest tests/ -v   # 319 tests
```

### Key Directories

```
backend/
├── main.py                    # FastAPI app (127KB, central hub)
├── orchestrator.py            # Agent pipeline coordinator
├── agents/                    # 9 Claude AI agents + shared client
│   ├── route_architect.py     # Route planning (Opus)
│   ├── architect_pre_plan.py  # Pre-plan for regions/nights (Sonnet) — NEW v1.2
│   ├── stop_options_finder.py # Stop suggestions with dedup (Sonnet)
│   ├── accommodation_researcher.py  # Hotels + Geheimtipp filter (Sonnet) — MODIFIED v1.2
│   └── ...                    # activities, restaurants, day planner, guide, analysis
├── tasks/                     # Celery background tasks
│   ├── update_nights_job.py   # Nights edit + day plan recalc — NEW v1.2
│   └── ...                    # planning, prefetch, replace, add, remove, reorder
├── models/                    # Pydantic models for all API boundaries
└── utils/                     # Shared utilities (maps, auth, logging, etc.)

frontend/js/
├── state.js                   # Global S object + TRAVEL_STYLES + FLAGS
├── api.js                     # All fetch calls + openSSE()
├── form.js                    # 5-step form + wishes tag input — MODIFIED v1.2
├── route-builder.js           # Interactive stop selection + nights display — MODIFIED v1.2
├── guide-edit.js              # Stop editing + inline nights editor — MODIFIED v1.2
└── ...                        # accommodation, progress, guide modules, maps, auth, router
```

### Where to Look First
- **Trip planning entry point:** `backend/main.py` → `api_start_planning()` → Celery task
- **Interactive route building:** `backend/main.py` → `_find_and_stream_options()` (SSE streaming)
- **Agent pattern:** Any file in `backend/agents/` — all follow same structure (SYSTEM_PROMPT + run() + JSON parsing)
- **Frontend state:** `frontend/js/state.js` → global `S` object
- **v1.2 changes:** Search for "architect_pre_plan", "wished", "KRITISCH", "Stopzentrum", "apiUpdateNights"

### Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...     # Required
GOOGLE_MAPS_API_KEY=...          # Required (Geocoding, Directions, Places)
TEST_MODE=true                   # true=haiku (dev), false=opus/sonnet (prod)
REDIS_URL=redis://localhost:6379 # Job state + Celery broker
```

---

## Stats

- **Timeline:** 2026-03-28 → 2026-03-29 (2 days, in progress — Phase 16 remaining)
- **Phases:** 4/5 complete
- **Plans executed:** 8 (across 4 phases)
- **Commits:** ~65 (since v11.0.0 tag)
- **Files changed:** 68 (+8,611 / -96 lines)
- **Tests:** 319 passing (up from 291 at v1.1 end)
- **New tests in v1.2:** 28 (covering wishes, pre-plan, dedup, Geheimtipp filter, nights edit)
- **Contributors:** Stefan (sole developer)
- **Verification scores:** 9/9, 9/9, 8/8, 10/10 (all phases passed)

---

*Summary generated from: ROADMAP.md, PROJECT.md, REQUIREMENTS.md, STATE.md, RETROSPECTIVE.md, and 17 phase artifacts (CONTEXT, RESEARCH, SUMMARY, VERIFICATION files for Phases 12-15)*
