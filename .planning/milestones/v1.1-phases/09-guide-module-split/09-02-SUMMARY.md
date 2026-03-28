---
phase: 09-guide-module-split
plan: "02"
subsystem: frontend
tags: [refactor, guide, module-split, javascript, wiring]
dependency_graph:
  requires: [09-01]
  provides: [index.html-with-7-guide-modules]
  affects: [frontend/index.html]
tech_stack:
  added: []
  patterns: [script-tag-load-order, flat-globals]
key_files:
  created: []
  modified:
    - frontend/index.html
  deleted:
    - frontend/js/guide.js
decisions:
  - "7 guide module script tags replace the single guide.js tag in index.html"
  - "Load order: guide-core > guide-overview > guide-stops > guide-days > guide-map > guide-edit > guide-share"
  - "guide.js deleted — all 82 functions now live in the 7 focused modules"
metrics:
  duration_minutes: 5
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_created: 0
  files_modified: 1
  files_deleted: 1
---

# Phase 9 Plan 02: Guide Module Wire-up Summary

## One-liner

Replaced single guide.js script tag with 7 ordered module tags in index.html and deleted the now-superseded monolith file.

## What Was Built

Plan 02 completes the guide module split by wiring the 7 new guide modules into `frontend/index.html` and removing the original `frontend/js/guide.js`.

### Changes Made

| Action | File | Detail |
|--------|------|--------|
| Modified | frontend/index.html | Replaced `<script src="/js/guide.js">` with 7 module tags |
| Deleted | frontend/js/guide.js | 3010-line monolith — fully superseded by 7 focused modules |

### Script Tag Load Order (in index.html)

```html
<script src="/js/progress.js"></script>       <!-- line 762 — unchanged -->
<script src="/js/guide-core.js"></script>      <!-- line 763 — entry point -->
<script src="/js/guide-overview.js"></script>  <!-- line 764 -->
<script src="/js/guide-stops.js"></script>     <!-- line 765 -->
<script src="/js/guide-days.js"></script>      <!-- line 766 -->
<script src="/js/guide-map.js"></script>       <!-- line 767 -->
<script src="/js/guide-edit.js"></script>      <!-- line 768 -->
<script src="/js/guide-share.js"></script>     <!-- line 769 -->
<script src="/js/travels.js"></script>         <!-- line 770 — unchanged -->
```

## Verification Results

- **Backend tests:** 289 passed, 2 failed (pre-existing: ANTHROPIC_API_KEY not set in test env, unrelated to this plan)
- **Function count:** 82 functions across 7 modules (8+10+13+15+9+24+3)
- **Critical functions:** `showTravelGuide` in guide-core.js, `navigateToStop` in guide-stops.js, `navigateToDay` in guide-days.js, `openReplaceStopModal` in guide-edit.js — all verified
- **Duplicate variables:** Zero — each `let` variable name declared in exactly one module
- **Remaining guide.js references:** Zero — no file in frontend/ references guide.js as a script path

## Deviations from Plan

### Merge from main required before execution

The worktree for this plan was created before plan 01 completed. The 7 guide module files from plan 01 existed on `main` branch but not in this worktree. A `git merge main` was performed at the start to bring the worktree up to date with plan 01's output. This is standard parallel execution handling — not a behavioral deviation.

## Known Stubs

None. This is a pure structural wiring change. All 82 functions are fully implemented in the 7 modules (delivered by plan 01). index.html now correctly loads all modules in dependency order.

## Self-Check: PASSED

Files exist:
- frontend/index.html: FOUND (modified)
- frontend/js/guide.js: DELETED (confirmed not present)

Commits exist:
- c8cee63: feat(09-02): replace guide.js with 7 module script tags in index.html
