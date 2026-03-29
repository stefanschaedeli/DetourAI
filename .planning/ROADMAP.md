# Roadmap: DetourAI

## Milestones

- ✅ **v1.0 AI Trip Planner MVP** — Phases 1-7 (shipped 2026-03-26) — [Archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Polish & Travel View Redesign** — Phases 8-11 (shipped 2026-03-28) — [Archive](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 AI-Qualität & Routenplanung** — Phases 12-15 (shipped 2026-03-29, Phase 16 deferred) — [Archive](milestones/v1.2-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 AI Trip Planner MVP (Phases 1-7) — SHIPPED 2026-03-26</summary>

- [x] Phase 1: AI Quality Stabilization (3/3 plans) — AI model fix, corridor validation, style enforcement, quality gating
- [x] Phase 2: Geographic Routing (2/2 plans) — Island-aware routing, ferry detection, port awareness
- [x] Phase 3: Route Editing (3/3 plans) — Remove/add/reorder/replace stops with Celery tasks
- [x] Phase 4: Map-Centric Responsive Layout (6/6 plans) — Split-panel map-hero, stop cards, day timeline, mobile responsive
- [x] Phase 5: Sharing & Cleanup (3/3 plans) — Public shareable links, PDF/PPTX export removal
- [x] Phase 6: Wiring Fixes (2/2 plans) — Share token persistence, tags, SSE events, hints
- [x] Phase 7: Ferry-Aware Route Edits (1/1 plans) — Ferry-aware directions in all edit paths

**25/25 requirements satisfied** | **286 tests passing** | **166 commits**

</details>

<details>
<summary>✅ v1.1 Polish & Travel View Redesign (Phases 8-11) — SHIPPED 2026-03-28</summary>

- [x] Phase 8: Tech Debt Stabilization (2/2 plans) — Celery fix, map redraw, stats bar, drive limits
- [x] Phase 9: Guide Module Split (2/2 plans) — guide.js split into 7 focused modules
- [x] Phase 10: Progressive Disclosure UI (3/3 plans) — Three-level drill-down with breadcrumb and map focus
- [x] Phase 11: Browser Verification (4/4 plans) — 18 UI items verified, 7 gaps fixed

**12/12 requirements satisfied** | **291 tests passing** | **34 commits**

</details>

<details>
<summary>✅ v1.2 AI-Qualität & Routenplanung (Phases 12-15) — SHIPPED 2026-03-29</summary>

- [x] Phase 12: Context Infrastructure + Wishes Forwarding (2/2 plans) — Global wishes field forwarded to all 9 agents
- [x] Phase 13: Architect Pre-Plan for Interactive Flow (2/2 plans) — Strategic region/nights pre-planning
- [x] Phase 14: Stop History Awareness + Night Distribution (2/2 plans) — Dedup + nights-remaining display
- [x] Phase 15: Hotel Geheimtipp Quality + Day Plan Recalculation (3/3 plans) — Haversine filter + inline nights editor

**12/16 requirements satisfied** | **319 tests passing** | **66 commits**
**Phase 16 deferred** — UIX-01..04 (map fitBounds, stop images, tooltips, selection map history)

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-7 | v1.0 | 20/20 | Complete | 2026-03-26 |
| 8-11 | v1.1 | 11/11 | Complete | 2026-03-28 |
| 12. Context Infrastructure + Wishes Forwarding | v1.2 | 2/2 | Complete | 2026-03-29 |
| 13. Architect Pre-Plan for Interactive Flow | v1.2 | 2/2 | Complete | 2026-03-29 |
| 14. Stop History Awareness + Night Distribution | v1.2 | 2/2 | Complete | 2026-03-29 |
| 15. Hotel Geheimtipp Quality + Day Plan Recalculation | v1.2 | 3/3 | Complete | 2026-03-29 |
| 16. Frontend UI Fixes + Polish | v1.2 | — | Deferred | - |
