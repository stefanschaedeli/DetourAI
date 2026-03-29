# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — AI Trip Planner MVP

**Shipped:** 2026-03-26
**Phases:** 7 | **Plans:** 20 | **Commits:** 166
**Timeline:** 3 days (2026-03-24 → 2026-03-26)

### What Was Built
- AI quality stabilization: model bug fix, three-stage stop validation, travel style enforcement
- Geographic intelligence: 8 Mediterranean island groups with ferry detection, port awareness, ferry cost/time
- Route editing: remove/add/reorder/replace stops with Celery tasks, edit locking, metric recalculation
- Map-centric responsive layout: split-panel map-hero, stop cards, day timeline, stats bar, click-to-add
- Public sharing: token-based shareable links with read-only view, share toggle, URL preservation
- Wiring fixes: cross-phase integration (tags, SSE events, hints, share token persistence)
- Ferry-aware route edits: ferry directions in all edit code paths

### What Worked
- Phase ordering was correct: AI quality → geography → editing → layout → sharing. Each phase built cleanly on the last
- Gap closure phases (6, 7) effectively caught integration issues that individual phase verifications missed
- Milestone audit process identified real bugs (replace_stop_job Celery registration, map marker refresh)
- Parallel plan execution within phases saved significant time (e.g., Phase 5 plans 01+02 in parallel)
- Verification reports with 4-level checks (exists/substantive/wired/data-flowing) caught wiring gaps early

### What Was Inefficient
- ROADMAP.md plan completion checkboxes drifted out of sync — plans marked incomplete in roadmap but complete on disk
- Some SUMMARY.md one-liners were noisy/unhelpful (e.g., just a filename, or rule-bug format) — needs better extraction
- Phase 4 had 6 plans which was too granular — several could have been combined
- Integration issues found at milestone audit could have been caught earlier with cross-phase wiring checks during execution

### Patterns Established
- 4-tuple return from `google_directions_with_ferry` (hours, km, polyline, is_ferry) as standard API
- Tags merge with `dict.fromkeys` for ordered dedup, max 4 per stop
- SSE event registration pattern: api.js events array → handler map in progress.js/route-builder.js → showToast()
- Edit lock pattern: acquire after validation, release in finally block
- Share token pattern: token_urlsafe(16), separate public endpoint, query param for SSE auth

### Key Lessons
1. **Wire integration checks into phase execution, not just milestone audits** — the replace_stop_job Celery registration gap and map marker refresh issue both existed from Phase 3 but weren't caught until milestone audit
2. **Keep ROADMAP.md checkboxes in sync with disk state** — use `roadmap analyze` to detect drift
3. **Phase 1 corridor/quality checks should apply to edit paths too** — design choice to skip them for edits may cause quality regression on user-added stops
4. **Ferry-aware directions must be the default everywhere** — the Phase 3→Phase 7 gap showed that `google_directions_simple` was the wrong default for any new code

### Cost Observations
- Model mix: quality profile (Opus for orchestration/planning, Sonnet for research/integration checker)
- Average plan execution: ~3.7 minutes across 18 tracked plans
- Most plans required 2 tasks and 3-6 files — consistent scope
- Phase 4 Plan 05 was fastest (2 min, 1 task) — click-to-add was well-scoped

---

## Milestone: v1.1 — Polish & Travel View Redesign

**Shipped:** 2026-03-28
**Phases:** 4 | **Plans:** 11 | **Commits:** 34
**Timeline:** 2 days (2026-03-27 → 2026-03-28)

### What Was Built
- Tech debt fixes: Celery task registration, map marker/polyline refresh after all 5 edit paths, stats bar on all tabs, two-tier drive limit enforcement with ferry exclusion
- Guide module split: 3010-line guide.js decomposed into 7 focused modules (82 functions, zero regressions)
- Progressive disclosure UI: three-level drill-down (overview → day → stop) with crossfade transitions, breadcrumb navigation, map marker dimming and focus management
- Browser verification: 18 UI items tested, 7 gaps fixed (layout ratio, zoom cap, stats font, SSE error handling, geocode popup, drag-drop zones, inline nights edit)

### What Worked
- Module split (Phase 9) as prerequisite for progressive disclosure (Phase 10) was the right sequencing — clean module boundaries made drill-down navigation straightforward
- Browser verification as final phase (Phase 11) caught real issues that automated checks missed (layout ratios, zoom behavior, SSE onerror handling)
- Milestone audit with 3-source cross-reference (VERIFICATION.md + SUMMARY frontmatter + REQUIREMENTS.md) gave high confidence in completion
- Gap closure plans (11-02, 11-03, 11-04) were scoped precisely from UAT findings — no wasted work

### What Was Inefficient
- SUMMARY.md one-liner extraction still produced noisy results — some summaries had rule-bug prefixes or incomplete text
- Phase 11 roadmap showed "3/4" plans complete while disk had 4/4 — same roadmap sync issue from v1.0
- Nyquist validation was never completed for 3 of 4 phases — validation framework exists but wasn't prioritized

### Patterns Established
- `_drillTransition` helper for consistent crossfade between drill levels
- Breadcrumb placed outside `#guide-content` to persist across `renderGuide()` calls
- Marker dimming via `OverlayView._div.style.opacity` — simpler than icon swaps
- Drop zones as separate divs between cards (not on-card drop targets)
- `addListenerOnce('idle')` to cap map zoom after `fitBounds`

### Key Lessons
1. **Module split before UI redesign is essential** — trying to add progressive disclosure to a 3010-line monolith would have been extremely error-prone
2. **Browser verification catches things automated checks miss** — layout ratios, zoom behavior, and SSE error handling all required human eyes
3. **Gap closure plans should be scoped from UAT results, not guessed** — Phase 11's targeted fixes were efficient because they came from observed browser behavior

### Cost Observations
- Model mix: quality profile (Opus for orchestration/planning, Sonnet for research agents)
- Average plan execution: ~5 minutes across 11 plans (slightly higher than v1.0 due to UI complexity)
- Phase 10 was the most complex with 3 plans touching 4+ files each
- Phase 11 gap closure plans were efficiently scoped (2-3 files each)

---

## Milestone: v1.2 — AI-Qualität & Routenplanung

**Shipped:** 2026-03-29
**Phases:** 4 (of 5 planned) | **Plans:** 9 | **Commits:** 66
**Timeline:** 2 days (2026-03-28 → 2026-03-29)

### What Was Built
- Context infrastructure: global wishes field forwarded to all 9 agents via conditional prompt injection
- Architect pre-plan: new ArchitectPrePlanAgent creates strategic region/nights distribution before stop selection
- Stop deduplication: KRITISCH exclusion rule in prompt + post-processing safety net + history capping
- Nights-remaining display in route builder during interactive stop selection
- Geheimtipp quality: explicit coordinates in prompt + haversine post-filter + name dedup
- Inline nights editor: DOM-based number input replacing prompt(), Celery task for arrival_day rechaining + day plan refresh with SSE progress

### What Worked
- Two independent streams per phase (e.g., Phase 15: ACC + BDG) allowed parallel Wave 1 execution with no conflicts
- Reusing existing helpers (recalc_arrival_days, run_day_planner_refresh, haversine_km) kept implementation time low
- Context discussion before planning (CONTEXT.md) prevented architectural debates during execution
- Auto-advance mode (plan → execute → verify) allowed completing Phase 15 in a single session

### What Was Inefficient
- Phase 16 (UI polish) was planned but never started — scope was too ambitious for a milestone focused on AI quality
- SUMMARY.md one-liner extraction still unreliable — many plans produced empty "One-liner:" fields
- REQUIREMENTS.md traceability table wasn't updated when phases completed (ACC-01/02 and RTE-03/04 stayed "Pending")
- No milestone audit was run — proceeding with known gaps instead of formal verification

### Patterns Established
- Conditional prompt injection: `if travel_description: prompt += f"\n\nReisebeschreibung: {travel_description}"`
- Pre-plan advisory pattern: lightweight agent → job state → optional consumption by downstream agent
- Sentinel flag pattern for async filtering: `_geheimtipp_too_far` flag set during gather, filtered after
- Inline edit UI pattern: DOM createElement (XSS-safe) → _fetchQuiet → openSSE → re-render on complete

### Key Lessons
1. **Prompt-level fixes are more effective than post-processing** — Geheimtipp distance improved dramatically with explicit coordinates in the prompt; haversine filter is secondary safety net
2. **Scope UI polish separately from AI improvements** — AI quality and UI polish have different testing needs; mixing them dilutes both
3. **REQUIREMENTS.md traceability needs automated sync** — manual checkbox updates drift; `roadmap analyze` catches plan state but not requirement status
4. **Auto-advance is powerful for sequential phases** — discuss → plan → execute → verify in one session eliminates context switching

### Cost Observations
- Model mix: quality profile (Opus for planner, Sonnet for researcher/executor/verifier)
- Phase 15 execution: ~13 min across 3 plans (2 parallel + 1 sequential)
- Worktree isolation enabled true parallel execution with zero merge conflicts on code files
- Most complex task: update_nights_job.py (Celery task touching 4 files with endpoint + tests)

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Commits | Phases | Plans | Key Change |
|-----------|---------|--------|-------|------------|
| v1.0 | 166 | 7 | 20 | Initial milestone — established GSD workflow with verification + audit loop |
| v1.1 | 34 | 4 | 11 | Refined gap closure — UAT-driven fixes, milestone audit with 3-source cross-reference |
| v1.2 | 66 | 4 | 9 | AI quality focus — pre-planning, dedup, prompt engineering, auto-advance workflow |

### Cumulative Quality

| Milestone | Tests | LOC (Python) | LOC (JS/HTML/CSS) | Requirements |
|-----------|-------|--------------|--------------------| -------------|
| v1.0 | 286 | 14,332 | 16,092 | 25/25 |
| v1.1 | 291 | ~14,400 | ~17,000 | 12/12 |
| v1.2 | 319 | ~15,200 | ~17,500 | 12/16 |

### Top Lessons (Verified Across Milestones)

1. Phase ordering matters — fix data quality before building UI on top of it (v1.0), split modules before UI redesign (v1.1)
2. Integration wiring should be verified continuously, not just at milestone boundaries (v1.0 Celery bug, v1.1 router drill state)
3. Browser/human verification as a final phase catches real issues that automated checks miss (v1.0 audit, v1.1 UAT)
4. Prompt-level fixes outperform post-processing for AI quality — give agents better context rather than filtering bad output (v1.2 Geheimtipp distance)
5. Scope UI polish separately from AI/backend improvements — different testing needs, different verification cycles (v1.2 Phase 16 deferred)
