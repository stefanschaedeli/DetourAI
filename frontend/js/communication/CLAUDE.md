# frontend/js/communication/CLAUDE.md

Backend bridge — SSE wire protocol, event dispatch, and progress UI.
Do NOT modify backend/, infra/, core/, maps/, guide/, or features/.

## Files

| File | Responsibility |
|------|---------------|
| `sse-client.js` | `SSEClient` IIFE — EventSource lifecycle, auth token injection, CustomEvent dispatch |
| `sse-overlay.js` | `progressOverlay` IIFE — phase spinner/check lines during planning |
| `progress.js` | SSE stop timeline, debug log panel, overlay status lines |

## SSE Subscriber Pattern

New code subscribes directly to window events — do NOT call `openSSE()` in new files:

```js
// New pattern (preferred)
window.addEventListener('sse:stop_done', e => {
  const data = e.detail;  // parsed SSE payload
});

// Legacy pattern (openSSE shim in core/api.js — existing files only)
openSSE(jobId, { stop_done: (data) => { … } });
```

`SSEClient` dispatches all events as `window` CustomEvents with the prefix `sse:`.
Auth token injected via `?token=` query param (EventSource doesn't support headers).

## SSE Events

| Event | Meaning |
|-------|---------|
| `route_option_ready` | One stop option available for selection |
| `route_options_done` | All options for current stop delivered |
| `stop_done` | Stop confirmed and added to route |
| `accommodation_loading` | Accommodation research started for a stop |
| `accommodation_loaded` | One accommodation option ready |
| `accommodations_all_loaded` | All accommodations delivered |
| `region_plan_ready` | RegionPlanner produced a plan |
| `leg_complete` | One trip leg fully planned |
| `job_complete` | Planning finished — full TravelPlan available |
| `job_error` | Fatal error — SSE stream closes |
| `ping` | Keepalive |

## progress.js

Renders the stop timeline and debug log panel during the planning phase.
Subscribes to `sse:*` events to update the UI in real time.
Also manages overlay status lines via `progressOverlay` from `sse-overlay.js`.
