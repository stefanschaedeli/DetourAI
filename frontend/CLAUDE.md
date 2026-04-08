# frontend/CLAUDE.md

This worker owns `frontend/` — all JS, HTML, CSS, and i18n files.
Do NOT modify backend/, infra/, or docker-compose.yml.

## Key Files

| File | Responsibility |
|------|---------------|
| `js/state.js` | Global `S` object, TRAVEL_STYLES, FLAGS, localStorage layer |
| `js/api.js` | All fetch wrappers (`_fetch`, `_fetchQuiet`, `_fetchWithAuth`), `openSSE()` shim, all `apiXxx()` functions |
| `js/sse-client.js` | SSE wire protocol — EventSource lifecycle, auth token injection, dispatches `window` CustomEvents (`sse:X`) |
| `js/form.js` | 5-step trip form, `buildPayload()`, tag-input, via-points |
| `js/route-builder.js` | Interactive stop selection flow |
| `js/accommodation.js` | Parallel accommodation loading + selection grid |
| `js/progress.js` | SSE progress UI — stop timeline, overlay lines, debug log |
| `js/guide-core.js` | Travel guide entry point, tab routing |
| `js/guide-overview.js` | Trip overview tab |
| `js/guide-stops.js` | Stop detail cards |
| `js/guide-days.js` | Day-by-day itinerary rendering |
| `js/guide-map.js` | Guide map tab — delegates to GoogleMaps |
| `js/guide-edit.js` | Stop editing (replace, add, remove, reorder) |
| `js/guide-share.js` | Share link generation |
| `js/travels.js` | Saved travels list + management |
| `js/maps-core.js` | GoogleMaps init, markers, autocomplete, coordinate resolution |
| `js/maps-images.js` | Photo fetching (4-tier fallback), image cache — edit this to change photo quality/sources |
| `js/maps-routes.js` | Driving route rendering via Routes API, straight-line fallback |
| `js/maps-guide.js` | Persistent guide map state, stop markers, ferry lines, pan/fit/dim |
| `js/loading.js` | Loading state UI |
| `js/sse-overlay.js` | SSE progress overlay component |
| `js/auth.js` | Authentication / access control |
| `js/router.js` | Client-side routing, pattern-matched routes |
| `js/sidebar.js` | Sidebar navigation component |
| `js/settings.js` | Settings page / preferences |
| `js/i18n.js` | `t()`, `setLocale()`, `getLocale()`, `getFormattingLocale()` |
| `js/types.d.ts` | Generated from OpenAPI — do not edit manually |
| `index.html` | Entry point, `<script>` load order matters |
| `styles.css` | All styles — see DESIGN_GUIDELINE.md for design system |

## SSE Subscriber Pattern

New code subscribes directly to window events — do not call `openSSE()` in new files:

```js
// New pattern (direct window event subscription)
window.addEventListener('sse:stop_done', e => {
  const data = e.detail;  // parsed SSE payload
});

// Legacy pattern (still works via openSSE shim — existing files only)
openSSE(jobId, { stop_done: (data) => { ... } });
```

## JavaScript Conventions

- Vanilla ES2020, no build step, no framework, no npm
- No import/export — all files loaded via `<script>` tags in `index.html`
- Load order in `index.html` is significant: `state.js` → `api.js` → `form.js` → …
- Global state object is `S` (defined in `state.js`) — all mutable app state lives here
- Constants are UPPER_CASE: `API`, `TRAVEL_STYLES`, `FLAGS`
- kebab-case for filenames: `route-builder.js`, `sse-overlay.js`
- camelCase for functions: `goToStep()`, `renderGuide()`, `buildPayload()`
- `api` prefix for API wrappers: `apiLogin()`, `apiLogout()`, `apiGetMe()`, `apiLogError()`
- Private vars prefixed `_`: `_fetchWithAuth()`, `_guideMarkers`, `_activeStopId`
- kebab-case for CSS classes: `form-step`, `step-indicator`, `guide-tab`

## API Client Rules

- NEVER use `fetch()` outside of `api.js`
- `_fetch(url, opts)` — shows loading overlay, for user-triggered actions
- `_fetchQuiet(url, opts)` — no overlay, for background requests (skeleton cards give feedback)
- `_fetchWithAuth(url, opts)` — injects Bearer token, retries once on 401 (silent token refresh)
- All API wrappers call `_fetchWithAuth()` internally
- API base prefix is `/api` (Nginx proxy to backend:8000) — never use `localhost:8000`

## State Management

- All mutable state lives on the `S` object in `state.js`
- localStorage keys are prefixed `tp_v1_*`
- No reactivity system — UI updates are imperative DOM manipulation
- URL state via `router.js` — routes: `/`, `/form/step/{n}`, `/route-builder/{jobId}`,
  `/accommodation/{jobId}`, `/progress/{jobId}`, `/travel/{id}`, `/travels`, `/settings`

## Security

- `esc(str)` — REQUIRED for all user-content HTML interpolation (XSS prevention)
- `safeUrl(url)` — blocks non-http(s) URLs before using in `href`/`src`
- `window.onerror` and `window.onunhandledrejection` auto-report to backend via `apiLogError()`
- All `console.error()` calls should also call `apiLogError('error', msg, source, stack)`

## i18n

- `t('key')` — translates a key using the active locale (de/en/hi)
- `setLocale(code)` — switches locale and re-renders UI
- `getLocale()` — returns current locale code
- `getFormattingLocale()` — returns BCP-47 locale for Intl formatters (e.g. `'de-CH'`)
- All user-facing strings must use `t()` — no hardcoded German text in JS
- Translation files live in `frontend/i18n/` (de.json, en.json, hi.json)

## SSE Events (key names)

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
| `job_error` | Fatal error — close SSE |
| `ping` | Keepalive |

## Design System

See `DESIGN_GUIDELINE.md` for the Apple-inspired design system (colors, spacing, components).
