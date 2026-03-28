---
phase: 11-browser-verification
plan: "03"
subsystem: frontend
tags: [gap-closure, sse, edit-lock, geocoding, guide-edit]
dependency_graph:
  requires: []
  provides: [GAP-04-fixed, GAP-05-fixed]
  affects: [frontend/js/guide-edit.js]
tech_stack:
  added: []
  patterns: [SSE onerror handler, address_components geocoding]
key_files:
  created: []
  modified:
    - frontend/js/guide-edit.js
decisions:
  - "onerror handler added to all 5 openSSE call sites — ensures edit lock always releases on connection failure"
  - "address_components preferred over formatted_address for clean city/country name extraction"
metrics:
  duration: "4min"
  completed: "2026-03-28T19:53:36Z"
  tasks_completed: 2
  files_modified: 1
---

# Phase 11 Plan 03: SSE Edit Lock and Geocode Fix Summary

**One-liner:** SSE onerror handlers on all 5 edit operations release the frontend edit lock on connection failure; reverse geocode extracts clean "City, Country" from address_components.

## Objective

Fix two logic issues found during browser UAT: edit lock getting stuck after SSE connection drops (GAP-05, high severity), and garbled characters in the click-to-add reverse geocode popup (GAP-04, medium severity).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add SSE onerror handlers to all edit operations | 634bc2b | frontend/js/guide-edit.js |
| 2 | Fix click-to-add reverse geocode garbled characters | 9c70c43 | frontend/js/guide-edit.js |

## What Was Built

### Task 1 — SSE onerror Handlers (GAP-05)

Added `onerror` callback to every `openSSE()` call in `guide-edit.js`. Each handler:
1. Closes the SSE connection and nulls the reference
2. Calls `_unlockEditing()` to re-enable all edit buttons
3. Shows a German error alert

The 5 call sites covered:
- `_executeRemoveStop` — "Verbindung verloren beim Entfernen des Stopps."
- `_executeAddStop` — "Verbindung verloren beim Hinzufügen des Stopps."
- `_doAddStopFromMap` — "Verbindung verloren beim Hinzufügen des Stopps."
- `_onStopDrop` — "Verbindung verloren beim Sortieren."
- `_listenForReplaceComplete` — "Verbindung verloren beim Ersetzen des Stopps." (uses `_replaceStopSSE`)

### Task 2 — Geocode Clean Name (GAP-04)

Replaced direct `formatted_address` use in `_onMapClickToAdd` with address component parsing:
1. Iterates `results[0].address_components` to extract `locality`, `administrative_area_level_1`, and `country`
2. Builds "City, Country" or "Region, Country" string
3. Falls back to first two comma-separated parts of `formatted_address` if no locality/region found

## Decisions Made

- onerror handler added to all 5 openSSE call sites — ensures edit lock always releases on connection failure
- address_components preferred over formatted_address for clean city/country name extraction

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- frontend/js/guide-edit.js: modified and committed
- Commit 634bc2b: `git log --oneline | grep 634bc2b` — found
- Commit 9c70c43: `git log --oneline | grep 9c70c43` — found
- `grep -c "onerror:" frontend/js/guide-edit.js` = 5
- `grep -n "address_components"` confirms parsing at line 310
