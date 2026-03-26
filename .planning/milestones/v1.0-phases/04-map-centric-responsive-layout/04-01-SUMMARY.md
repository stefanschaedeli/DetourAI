---
phase: 04-map-centric-responsive-layout
plan: 01
subsystem: frontend-layout, backend-models
tags: [split-panel, responsive, pydantic, css-layout, html-structure]
dependency_graph:
  requires: []
  provides: [split-panel-html, split-panel-css, travel-stop-card-fields]
  affects: [guide.js, maps.js, sidebar.js]
tech_stack:
  added: []
  patterns: [css-custom-properties, aria-roles, responsive-breakpoints, position-fixed-panel]
key_files:
  created: []
  modified:
    - backend/models/travel_response.py
    - backend/tests/test_models.py
    - frontend/index.html
    - frontend/styles.css
decisions:
  - "TravelStop tags/teaser/highlights placed after notes, before is_ferry for field grouping"
  - "guide-map-panel override for #guide-map avoids breaking existing map initialization"
  - "Tab labels shortened: 'Reisefuehrer & Stops' -> 'Stopps', 'Tagesplan' -> 'Tage'"
metrics:
  duration: 4min
  completed: 2026-03-25
---

# Phase 4 Plan 01: Model Extension + Split-Panel Layout Summary

Split-panel guide layout with TravelStop card data fields and responsive CSS at three breakpoints (desktop 58/42, tablet 50/50, mobile stacked).

## What Was Done

### Task 1: TravelStop Model Extension (TDD)
- Added `tags: List[str] = []`, `teaser: Optional[str] = None`, `highlights: List[str] = []` to TravelStop
- Fields carry StopOption data through to frontend for card display
- All defaults ensure backward compatibility with existing saved travels
- Test `test_travel_stop_tags_teaser` verifies defaults, explicit values, and backward compatibility
- All 71 model tests pass

### Task 2: Split-Panel HTML/CSS Layout
- Restructured `#travel-guide` section into `guide-split-panel` flex container
- Map panel (`guide-map-panel`): fixed position, 58% width, full viewport height
- Content panel (`guide-content-panel`): scrollable, 42% width, margin-left offset
- Sidebar overlay container inside map panel (collapsed by default, expandable)
- Click-to-add popup container inside map panel
- Stats bar placeholder (`#guide-stats-bar`) above tabs
- ARIA roles added: `tablist`, `tab`, `aria-selected`, `role="main"`
- Responsive breakpoints: tablet 50/50 (768-1099px), mobile stacked 30vh map (<768px)
- `prefers-reduced-motion` support for all Phase 4 animations
- `#guide-map` override inside split panel removes old height/border constraints

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | 36930e1 | Failing test for tags/teaser/highlights |
| 1 (GREEN) | 36bf3a8 | TravelStop model fields added |
| 2 | c4993d9 | Split-panel HTML + CSS layout |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] #guide-map height override**
- **Found during:** Task 2
- **Issue:** Existing `#guide-map` CSS had `height: clamp(360px, 50vh, 600px)` and border-radius which would conflict with full-height map panel
- **Fix:** Added `.guide-map-panel #guide-map` override to set height:100%, remove border-radius and margin
- **Files modified:** frontend/styles.css
- **Commit:** c4993d9

## Known Stubs

None - all containers are structural placeholders that will be populated by subsequent plans (02-06).

## Verification

- `python3 -m pytest tests/test_models.py -x -q` -- 71 passed
- HTML contains: guide-split-panel, guide-map-panel, guide-content-panel, guide-stats-bar, sidebar-overlay, role="tablist"
- CSS contains: position:fixed map panel at 58%, responsive breakpoints at 1099px and 767px
