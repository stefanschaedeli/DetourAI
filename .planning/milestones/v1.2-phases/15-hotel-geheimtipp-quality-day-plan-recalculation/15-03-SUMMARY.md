---
phase: 15-hotel-geheimtipp-quality-day-plan-recalculation
plan: "03"
subsystem: frontend
tags: [nights-editor, inline-ui, sse, guide-edit]
dependency_graph:
  requires: [15-02]
  provides: [inline-nights-editor, sse-nights-listener]
  affects: [frontend/js/guide-edit.js, frontend/js/guide-stops.js, frontend/js/api.js, frontend/styles.css]
tech_stack:
  added: []
  patterns: [inline-dom-editor, sse-listener, edit-lock-guard]
key_files:
  created: []
  modified:
    - frontend/js/guide-edit.js
    - frontend/js/guide-stops.js
    - frontend/js/api.js
    - frontend/styles.css
decisions:
  - "Used _fetchQuiet (not _fetch) for apiUpdateNights — SSE overlay provides progress feedback, no loading overlay needed"
  - "DOM-built inline editor (createElement) instead of template strings — XSS-safe for all user data paths"
  - "_nightsSSE scoped inside _listenForNightsComplete (not module-level) — nights edits don't conflict with replace stop SSE"
metrics:
  duration: "~8min"
  completed: "2026-03-29"
  tasks: 2
  files: 4
---

# Phase 15 Plan 03: Inline Nights Editor with Backend Recalculation Summary

**One-liner:** Replaced prompt() dialog with DOM-built inline number input that triggers SSE-backed day plan recalculation via POST /api/travels/{id}/update-nights.

## What Was Built

The nights editing flow for stop cards has been completely replaced. Previously, clicking the nights display triggered a browser `prompt()` dialog that only updated local state without recalculating day plans. Now:

1. Clicking the nights display inserts an inline number input (1-14) with confirm/cancel buttons directly into the DOM, replacing the span element.
2. Confirming a changed value calls `apiUpdateNights()` which POSTs to the backend endpoint from Plan 02.
3. An SSE connection (`_listenForNightsComplete`) listens for `update_nights_complete` which carries the full recalculated plan.
4. On completion, the plan state is updated in `S.result` and localStorage, and the guide re-renders with corrected arrival days.
5. The `_editInProgress` guard prevents concurrent edits during recalculation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add API wrapper + replace _editStopNights with inline editor + SSE listener | 6b23e73 | api.js, guide-edit.js, guide-stops.js, styles.css |
| 2 | Verify nights edit flow end-to-end | auto-approved | — |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all functionality is fully wired to the backend.

## Self-Check: PASSED

- `frontend/js/api.js`: modified — contains `apiUpdateNights`
- `frontend/js/guide-edit.js`: modified — contains `_editStopNights` (inline editor) and `_listenForNightsComplete`
- `frontend/js/guide-stops.js`: modified — contains `data-nights-stop`
- `frontend/styles.css`: modified — contains `.nights-inline-editor` CSS
- commit `6b23e73` exists
