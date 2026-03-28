# Phase 11: Browser Verification - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Verify all pending UI items from v1.0 and v1.1 against the current progressive disclosure view, then fix anything found broken. This is a verification + fix phase, not a feature phase. No new capabilities — only confirming existing ones work correctly and patching any that don't.

</domain>

<decisions>
## Implementation Decisions

### Verification Scope
- **D-01:** Verify ALL pending human items across v1.0 and v1.1 — 13 items from v1.0 (9 from Phase 4 + 4 from Phase 3) plus 5 from Phase 10. Total: up to 18 items.
- **D-02:** Phase 10's 5 items were approved at a checkpoint during execution but not formally UAT'd. Re-verify them as part of this phase to confirm they work in the full integrated app.
- **D-03:** Phase 3's 4 route-editing items (remove, add, drag-drop, edit controls disabled) are included — they were never browser-tested and the UI has changed significantly since v1.0.

### Verification Workflow
- **D-04:** This is a human-driven phase. The planner should create a single plan that lists all verification items as a structured checklist. The executor presents each item to the user for manual browser testing.
- **D-05:** Fixes are batched: document all failures first, then fix them in a second plan (or inline if trivial). Don't context-switch between verifying and fixing.
- **D-06:** Verification runs against the Docker deployment (`docker compose up --build`) to match production conditions. If Docker is unavailable, local dev server (`uvicorn`) is acceptable.

### Fix Strategy
- **D-07:** Trivial fixes (CSS tweaks, missing class, wrong selector) can be fixed inline during verification. Non-trivial fixes (broken SSE flow, missing endpoint, logic errors) get documented and planned separately.
- **D-08:** If Phase 10's progressive disclosure changes broke any Phase 3/4 items, those fixes take priority since they represent regressions.

### Claude's Discretion
- How to group verification items for efficient testing (by feature area vs by phase origin)
- Whether to use a UAT file format or a simpler checklist
- Order of verification items
- How to present results to the user

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pending Verification Items
- `.planning/milestones/v1.0-phases/04-map-centric-responsive-layout/04-VERIFICATION.md` — 9 human_verification items (split-panel layout, mobile responsive, stop cards, day timeline, stats bar, marker-card sync, scroll sync, click-to-add, sidebar)
- `.planning/milestones/v1.0-phases/03-route-editing/03-VERIFICATION.md` — 4 human_verification items (remove stop, add stop, drag-drop reorder, edit controls disabled)
- `.planning/phases/10-progressive-disclosure-ui/10-VERIFICATION.md` — 5 human_verification items (drill-down flow, map dimming, browser back/forward, responsive grid, collapsible)
- `.planning/phases/10-progressive-disclosure-ui/10-HUMAN-UAT.md` — Phase 10 UAT tracking file

### Current Frontend State
- `frontend/js/guide-core.js` — Central dispatch with drill-down navigation (Phase 10)
- `frontend/js/guide-overview.js` — Day cards grid + collapsible details (Phase 10)
- `frontend/js/guide-stops.js` — Stop detail with crossfade navigation (Phase 10)
- `frontend/js/guide-days.js` — Day detail with crossfade navigation (Phase 10)
- `frontend/js/guide-map.js` — Drill-level-aware map focus (Phase 10)
- `frontend/js/guide-edit.js` — Route editing handlers
- `frontend/js/maps.js` — GoogleMaps namespace with marker dimming
- `frontend/js/router.js` — Client-side routing with drill-down URLs
- `frontend/styles.css` — All CSS including Phase 10 additions

### Requirements
- `.planning/REQUIREMENTS.md` — VRFY-01 definition

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 10 VERIFICATION.md has structured human_verification items with test/expected/why_human format — reuse this structure
- 10-HUMAN-UAT.md has a tracking template with pass/fail/pending status per item

### Established Patterns
- Verification files use YAML frontmatter with status field
- UAT files track total/passed/issues/pending counts
- Fixes are committed with `fix(phase):` prefix

### Integration Points
- All verification happens in the browser against the live app
- Docker deployment: `docker compose up --build`
- Local dev: `cd backend && python3 -m uvicorn main:app --reload --port 8000`
- Test travel: Liestal → Französische Alpen → Paris, 10 days, 2 adults, CHF 5'000

</code_context>

<specifics>
## Specific Ideas

- User chose to skip detailed discussion — phase is straightforward verification work
- All 18 items should be verified, not just the 9 from ROADMAP description
- Phase 10 checkpoint approval counts as preliminary but should be re-verified in full integration context

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-browser-verification*
*Context gathered: 2026-03-27*
