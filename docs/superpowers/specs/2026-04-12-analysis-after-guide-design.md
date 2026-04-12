# Spec: Show Travel Guide Before Trip Analysis

**Date:** 2026-04-12
**Status:** Approved

## Problem

Today the orchestrator runs `TripAnalysisAgent` before sending `job_complete`. The user sees nothing until both the day planner and analysis finish. Analysis can take 10–20 seconds extra.

## Goal

Show the travel guide as soon as the day planner is done. Run trip analysis in the background and inject its result into the already-visible guide when it completes.

---

## Solution Overview

Split the final pipeline into two phases:

1. **`job_complete`** fires immediately after Day Planner — carries full plan with `trip_analysis: null`
2. **`analysis_complete`** fires after TripAnalysisAgent — carries `{ trip_analysis: { ... } }`

The frontend shows the guide on `job_complete`, then patches the analysis block into the DOM on `analysis_complete`.

---

## Backend (`orchestrator.py`)

**Current order:**
```
Day Planner → TripAnalysis → job_complete (with plan + analysis)
```

**New order:**
```
Day Planner → job_complete (plan, trip_analysis: null)
            → TripAnalysis (background, same async task)
            → analysis_complete (trip_analysis result)
            → update Redis job with merged plan
```

Changes:
- Move `job_complete` emit to immediately after Day Planner, before analysis
- Run `TripAnalysisAgent` after the emit
- Send new `analysis_complete` SSE event: `await self.progress("analysis_complete", None, {"trip_analysis": analysis_result}, 100)`
- After analysis, merge `trip_analysis` into the plan dict and persist back to Redis so saved travels have complete data

The `self.progress()` method already sends arbitrary payloads — no signature changes needed.

---

## SSE Contract (`contracts/sse-events.md`)

Add new event:

| Event | Payload | Meaning |
|-------|---------|---------|
| `analysis_complete` | `{ trip_analysis: TripAnalysis \| null }` | Trip analysis finished; patch into visible guide |

---

## Frontend

### `progress.js`

- `onJobComplete`: no changes — shows guide with `trip_analysis: null` (analysis block simply absent)
- New `onAnalysisComplete(data)`:
  - Update `S.result.trip_analysis` with `data.trip_analysis`
  - Re-save to localStorage (`lsSet(LS_RESULT, ...)`)
  - Patch DOM: find `.overview-details` collapsible section and prepend the rendered analysis HTML, OR replace existing `.trip-analysis` element if present
  - Also update saved travel in DB via `apiPatchTravel` if `S.result._saved_travel_id` exists (optional — can be skipped if no patch endpoint exists)
- Register in `connectSSE` event map: `analysis_complete: onAnalysisComplete`
- Update `_completeAnalysisTimelineRow()` call: move it to `onAnalysisComplete` (currently called in `onJobComplete`)

### `guide-overview.js`

No logic changes needed. `renderTripAnalysis()` is already a standalone function and can be called from the patch handler.

### `travels.js`

The reconnect-to-existing-job SSE handler (`openSSE(jobId, { job_complete: ... })`) does not need `analysis_complete` — if a user reconnects to an in-progress job, they'll get whichever events are still pending in the Redis SSE list, including `analysis_complete` if analysis hasn't finished yet. No changes needed.

---

## Progress Overlay

Currently `onJobComplete` calls `_completeAnalysisTimelineRow()`. With the new flow:
- `onJobComplete` should NOT mark analysis complete (it isn't yet)
- `onAnalysisComplete` marks the analysis timeline row done
- If `analysis_complete` never arrives (error), the row stays in "pending" state — acceptable since the guide is already visible

---

## Error Handling

- If TripAnalysis fails after `job_complete` was already sent, send `analysis_complete` with `{ trip_analysis: null }` — same as today (analysis is non-critical)
- The frontend `onAnalysisComplete` with `null` payload simply does nothing (guards on `if (!data.trip_analysis) return`)

---

## Out of Scope

- No new API endpoint needed
- No changes to `travels.js` SSE handler
- No changes to Pydantic models
- No changes to i18n keys (existing `progress.analysis_complete` key reused)
