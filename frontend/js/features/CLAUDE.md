# frontend/js/features/CLAUDE.md

Planning workflow + standalone page modules.
Do NOT modify backend/, infra/, core/, maps/, communication/, or guide/.

## Files

| File | Responsibility |
|------|---------------|
| `form.js` | 5-step trip planning wizard, `buildPayload()` → TravelRequest, auto-save |
| `route-builder.js` | Interactive stop selection, SSE-driven route options, map rendering |
| `accommodation.js` | Parallel accommodation loading grid, per-stop selection |
| `travels.js` | Saved travels list — CRUD, star ratings, travel card rendering |
| `settings.js` | Settings page — per-agent model selection (9 AI agents) |
| `sidebar.js` | `Sidebar` IIFE — node-based trip progress visualization |
| `feedback.js` | Feedback modal — category selection, screenshot via `html2canvas` |

## Planning Pipeline (sequential)

```
form.js → route-builder.js → accommodation.js → (communication/progress.js)
```

1. `form.js` — user fills 5-step form; `buildPayload()` builds the TravelRequest JSON
2. `route-builder.js` — submits job; subscribes to `sse:route_option_ready` / `sse:stop_done`
3. `accommodation.js` — subscribes to `sse:accommodation_loaded` / `sse:accommodations_all_loaded`

`route-builder.js` and `accommodation.js` consume SSE events (from `communication/`) but
their primary role is UX — rendering selection cards, not managing the SSE connection itself.

## SSE Consumption Pattern

```js
// These files subscribe to events dispatched by communication/sse-client.js
window.addEventListener('sse:route_option_ready', e => {
  const option = e.detail;
  // render stop option card
});
```

## Settings (settings.js)

9 AI agents configurable: RouteArchitect, StopOptionsFinder, RegionPlanner,
AccommodationResearcher, ActivitiesAgent, RestaurantsAgent, DayPlanner,
TravelGuideAgent, TripAnalysisAgent.
Model options: Opus / Sonnet / Haiku per agent.
Preferences persisted to localStorage + synced to backend.

## Sidebar (sidebar.js)

`Sidebar` IIFE renders the trip progress sidebar as a node-based visualization.
Updates during planning via SSE event subscriptions.
Reads phase state from `S` to determine which nodes are active/complete.
