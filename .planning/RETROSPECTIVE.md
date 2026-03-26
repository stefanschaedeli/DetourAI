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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Commits | Phases | Plans | Key Change |
|-----------|---------|--------|-------|------------|
| v1.0 | 166 | 7 | 20 | Initial milestone — established GSD workflow with verification + audit loop |

### Cumulative Quality

| Milestone | Tests | LOC (Python) | LOC (JS/HTML/CSS) | Requirements |
|-----------|-------|--------------|--------------------| -------------|
| v1.0 | 286 | 14,332 | 16,092 | 25/25 |

### Top Lessons (Verified Across Milestones)

1. Phase ordering matters — fix data quality before building UI on top of it
2. Integration wiring should be verified continuously, not just at milestone boundaries
