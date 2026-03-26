---
phase: 04-map-centric-responsive-layout
plan: 03
subsystem: frontend-guide
tags: [stop-cards, stats-bar, photo-cards, tag-pills, edit-controls]
dependency_graph:
  requires: [04-01]
  provides: [stop-card-row-layout, stats-bar-render, card-map-sync]
  affects: [guide.js, styles.css]
tech_stack:
  added: []
  patterns: [compact-row-card, lazy-image-loading, intersection-observer-ready, drag-and-drop-cards]
key_files:
  created: []
  modified:
    - frontend/js/guide.js
    - frontend/styles.css
decisions:
  - "Used buildHeroPhotoLoading('sm') for card photos with parent container constraining dimensions"
  - "Card click navigates to stop detail AND triggers map sync (bidirectional)"
  - "Stats bar populated via insertAdjacentHTML with DOM methods for XSS safety"
  - "GoogleMaps.panToStop/highlightGuideMarker called conditionally — functions not yet implemented (Plan 04)"
metrics:
  duration: 5min
  completed: 2026-03-25
---

# Phase 4 Plan 03: Stop Cards + Stats Bar Summary

Compact row stop cards with 16:9 photo, number badge, tags, teaser, always-visible edit controls, and 4-pill stats bar on overview tab.

## What Was Done

### Task 1: renderStopCard, renderStatsBar, and renderStopsOverview Rewrite
- Added `renderStopCard(stop, i, totalStops)` producing compact row cards per D-05 through D-08
- Card structure: 16:9 photo left, stop number badge, name, drive time, nights, tag pills, 2-line teaser description, edit action icons
- Edit buttons always visible: remove (X), replace (refresh arrows), drag (6-dot grip) with aria-labels in German
- Added `renderStatsBar(plan)` computing total days, stops, distance, budget remaining with German formatting
- Stats bar shows on overview tab, hidden on other tabs via renderGuide updates
- Added `_onCardClick(stopId)` for bidirectional map-content sync with conditional GoogleMaps API calls
- Added `_lazyLoadCardImages(plan)` using existing 5-tier image fallback chain
- Updated event delegation to handle new `.stop-card-row` clicks (navigate + highlight)
- Updated `_onStopDrop` to clean drag state on both old and new card classes

### Task 2: Stop Card and Stats Bar CSS
- `.stop-card-row`: flex layout with surface-card background, border-subtle, 16px padding, hover shadow
- `.stop-card-photo`: 120px wide, 16:9 aspect ratio, border-radius 8px, overflow hidden
- `.stop-num-badge`: 24px accent-primary circle with white number
- `.stop-tag-pill`: 980px radius pills with surface-active background, accent-primary text
- `.stop-card-desc`: 2-line clamp with -webkit-line-clamp
- `.stop-edit-icon`: 20px icons with hover states (accent for replace/drag, warm for remove)
- `.selected` state: 3px accent-primary left border + subtle shadow
- `.drag-over` state: 2px dashed accent border
- `.stat-negative`: warm color for budget exceeded
- Mobile (< 768px): 90px photo width, smaller title, stacked meta
- Reduced-motion: transitions disabled for cards and edit icons

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | efa3bfd | Stop cards JS with photo/tags/teaser and stats bar |
| 2 | ddfa7c5 | CSS for stop card row layout and stats bar styling |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

- `GoogleMaps.panToStop()` and `GoogleMaps.highlightGuideMarker()` are called conditionally but do not exist yet -- will be implemented in Plan 04 (map interactivity).
