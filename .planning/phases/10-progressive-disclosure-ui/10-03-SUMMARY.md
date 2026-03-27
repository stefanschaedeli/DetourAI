---
phase: 10-progressive-disclosure-ui
plan: 03
subsystem: frontend
tags: [vanilla-js, progressive-disclosure, drill-down, breadcrumb, crossfade, browser-history]
dependency_graph:
  requires:
    - phase: 10-progressive-disclosure-ui-plan-01
      provides: _drillTransition, _renderBreadcrumb, CSS infrastructure
    - phase: 10-progressive-disclosure-ui-plan-02
      provides: GoogleMaps.dimNonFocusedMarkers, _updateMapForTab drill-level params
  provides:
    - Complete drill-down navigation wiring (day card click, stop click, breadcrumb, browser back/forward)
    - navigateToDay uses _drillTransition + _renderBreadcrumb + _updateMapForTab
    - navigateToStop uses _drillTransition + _renderBreadcrumb + _updateMapForTab
    - _initBreadcrumbDelegation() separate listener on #guide-breadcrumb (outside #guide-content)
    - _navigateToOverview() helper for back-to-overview from any drill level
    - router.js _travel handler resets drill state on browser back to overview URL
  affects:
    - frontend/js/guide-core.js
    - frontend/js/guide-days.js
    - frontend/js/guide-stops.js
    - frontend/js/router.js
tech_stack:
  added: []
  patterns:
    - "Breadcrumb delegation must use separate listener — breadcrumb element is outside #guide-content"
    - "activateDayDetail/activateStopDetail use _drillTransition for consistent browser back/forward UX"
    - "router _travel handler resets activeTab/_activeDayNum/_activeStopId before showTravelGuide"
    - "navigateToStopsOverview goes to day if _activeDayNum set, else overview"
key_files:
  created: []
  modified:
    - frontend/js/guide-core.js
    - frontend/js/guide-days.js
    - frontend/js/guide-stops.js
    - frontend/js/router.js
decisions:
  - "_initBreadcrumbDelegation() uses separate guard and separate addEventListener on #guide-breadcrumb — not inside _initGuideDelegation (#guide-content delegation cannot receive clicks outside its subtree)"
  - "activateDayDetail and activateStopDetail (router-called) use _drillTransition — consistent UX whether navigating via click or browser popstate"
  - "navigateToStopsOverview returns to day detail if _activeDayNum is set — preserves navigation context"
metrics:
  duration: 6 min
  completed: "2026-03-27"
  tasks: 2 of 3 (Task 3 is human-verify checkpoint — pending approval)
  files: 4
---

# Phase 10 Plan 03: Drill-Down Navigation Wiring Summary

Complete three-level drill-down navigation: all in-app clicks (day cards, stop clicks, breadcrumb segments, back buttons) and browser back/forward now use crossfade transitions, update the breadcrumb, and trigger correct map focus via _updateMapForTab.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Wire day card clicks, breadcrumb delegation, navigateToDay/Stop crossfade | afc331b | guide-core.js, guide-days.js, guide-stops.js |
| 2 | Update router _travel handler for browser back/forward drill reset | 6067463 | router.js |
| 3 | Human verification checkpoint | PENDING | — |

## What Was Built

### Task 1: Navigation Wiring

**guide-core.js changes:**
- Added `_breadcrumbDelegationReady` guard and `_initBreadcrumbDelegation()` — separate click listener on `#guide-breadcrumb` (outside `#guide-content`, so it cannot be handled by `_initGuideDelegation`)
- Added `_navigateToOverview()` helper — uses `_drillTransition`, `_renderBreadcrumb('overview')`, `_updateMapForTab`, and `Router.navigate` to reset to overview from any drill level
- Removed breadcrumb click handling from `_initGuideDelegation` (was unreachable since breadcrumb is a sibling of `#guide-content`)
- `renderGuide` now calls `_initBreadcrumbDelegation()` at top and `_renderBreadcrumb` for each tab case (days with `_activeDayNum` set → 'day', stops with `_activeStopId` set → 'stop', all others → 'overview')
- `renderGuide` days case updated: when `_activeDayNum !== null`, renders `renderDayDetail` directly (not `renderDaysOverview`)

**guide-days.js changes:**
- `navigateToDay` now uses `_drillTransition`, `_renderBreadcrumb('day')`, `_updateMapForTab` with drill-level params
- `navigateToDaysOverview` delegates to `_navigateToOverview()` (back from day goes to overview, not days list)
- `activateDayDetail` updated to use `_drillTransition` + `_renderBreadcrumb` + `_updateMapForTab` (called by router popstate)

**guide-stops.js changes:**
- `navigateToStop` now uses `_drillTransition`, `_renderBreadcrumb('stop')`, `_updateMapForTab` with stop drill params
- `navigateToStopsOverview` goes to day detail if `_activeDayNum` is set, else `_navigateToOverview()`
- `activateStopDetail` updated to use `_drillTransition` + `_renderBreadcrumb` + `_updateMapForTab` (called by router popstate)

### Task 2: Router Browser History Fix

**router.js changes:**
- `_travel` handler resets `activeTab = 'overview'`, `_activeDayNum = null`, `_activeStopId = null` before calling `showTravelGuide` in both the cached-match branch and the API-load branch
- Ensures browser back from `/travel/42/days/3` → `/travel/42` correctly shows overview with all markers restored

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All navigation paths are fully wired with actual data and crossfade transitions.

## Checkpoint Status

**Task 3 (human-verify):** PENDING — awaiting human verification in browser.

## Self-Check

### Files verified:
- frontend/js/guide-core.js — contains _initBreadcrumbDelegation, _navigateToOverview, _renderBreadcrumb for all tab cases
- frontend/js/guide-days.js — navigateToDay uses _drillTransition, activateDayDetail uses _drillTransition
- frontend/js/guide-stops.js — navigateToStop uses _drillTransition, activateStopDetail uses _drillTransition
- frontend/js/router.js — _travel handler resets activeTab/_activeDayNum/_activeStopId

### Commits verified:
- afc331b: feat(10-03): wire day card clicks, breadcrumb, and crossfade to navigateToDay/Stop
- 6067463: feat(10-03): update router _travel handler to reset drill state on browser back

### Backend tests: 291 passed, 0 failed

## Self-Check: PASSED
