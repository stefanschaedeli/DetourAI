---
phase: 11-browser-verification
plan: "02"
subsystem: frontend
tags: [css, layout, maps, uat-fix, gap-closure]
dependency_graph:
  requires: []
  provides: [split-panel-45-55, stats-font-xl, fitDayStops-maxzoom]
  affects: [frontend/styles.css, frontend/js/maps.js]
tech_stack:
  added: []
  patterns: [google.maps.event.addListenerOnce]
key_files:
  created: []
  modified:
    - frontend/styles.css
    - frontend/js/maps.js
decisions:
  - "Split-panel ratio changed to 45/55 (map/content) for better content readability"
  - "Stats bar font-size reduced from text-3xl (2rem) to text-xl (1.25rem) for cleaner UI"
  - "fitDayStops uses addListenerOnce idle handler to cap zoom at 13 — avoids persistent listener overhead"
metrics:
  duration_minutes: 4
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_modified: 2
---

# Phase 11 Plan 02: Visual Layout and Map Zoom Fixes Summary

CSS split-panel ratio corrected to 45/55 (map/content), stats bar font reduced to text-xl, and fitDayStops zoom capped at 13 via addListenerOnce idle handler.

## What Was Built

Three targeted fixes for UAT failures GAP-01, GAP-02, and GAP-03:

- **GAP-01 (split-panel ratio):** Desktop split changed from 58/42 to 45/55 (map/content). The map was taking too much horizontal space, leaving content in a narrow 42% column. At 55% the content panel is comfortable on widescreen and 1080p displays.
- **GAP-02 (day drill-down zoom):** `fitDayStops` in maps.js now adds an `addListenerOnce` idle listener after `fitBounds`. If zoom exceeds 13 when the map settles, it is pulled back to 13. This prevents stops within a single city from zooming in to street level where markers and POIs disappear.
- **GAP-03 (stats bar font):** `.stat-pill .stat-num` font-size reduced from `var(--text-3xl)` (2rem/32px) to `var(--text-xl)` (1.25rem/20px). The oversized numbers were dominating the stats bar visually.

Tablet (50/50) and mobile (stacked) breakpoints were not touched.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Fix split-panel ratio and stats bar font | ccb3b17 | frontend/styles.css |
| 2 | Constrain fitDayStops zoom to prevent over-zoom | a3003ba | frontend/js/maps.js |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- `frontend/styles.css` exists with `width: 45%` at line 1611 and `margin-left: 45%` at line 1631
- `frontend/styles.css` has `font-size: var(--text-xl)` at line 1828 for `.stat-pill .stat-num`
- `frontend/js/maps.js` has `addListenerOnce` zoom cap in `fitDayStops`
- Commits ccb3b17 and a3003ba present in git log
