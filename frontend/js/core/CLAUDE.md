# frontend/js/core/CLAUDE.md

Foundation modules — loaded first, zero inter-module dependencies.
Do NOT modify backend/, infra/, maps/, guide/, communication/, or features/.

## Files

| File | Responsibility |
|------|---------------|
| `i18n.js` | `t()`, `setLocale()`, `getLocale()`, `getFormattingLocale()` — loaded before everything |
| `loading.js` | Loading overlay IIFE — `showLoadingOverlay()`, `hideLoadingOverlay()` |
| `state.js` | Global `S` object, `TRAVEL_STYLES`, `FLAGS`, `esc()`, `safeUrl()`, localStorage layer |
| `auth.js` | In-memory JWT — `authGetToken/Set/Clear()`, `authSilentRefresh()` |
| `router.js` | `Router` IIFE — pattern-matched routes, `Router.navigate()`, `Router.dispatch()` |
| `api.js` | `_fetch()`, `_fetchQuiet()`, `_fetchWithAuth()`, all `apiXxx()` wrappers, `openSSE()` shim |

## API Client Rules

- NEVER use `fetch()` outside of `api.js`
- `_fetch(url, opts)` — shows loading overlay, for user-triggered actions
- `_fetchQuiet(url, opts)` — no overlay, for background requests
- `_fetchWithAuth(url, opts)` — injects Bearer token, retries once on 401 via `authSilentRefresh()`
- All `apiXxx()` wrappers call `_fetchWithAuth()` internally
- API base prefix is `/api` (Nginx proxy) — never use `localhost:8000`

## State Management

- All mutable state lives on the `S` object in `state.js`
- localStorage keys prefixed `tp_v1_*`
- No reactivity — UI updates are imperative DOM manipulation
- URL routing via `router.js` — routes: `/`, `/form/step/{n}`, `/route-builder/{jobId}`,
  `/accommodation/{jobId}`, `/progress/{jobId}`, `/travel/{id}`, `/travels`, `/settings`

## Security

- `esc(str)` — REQUIRED for all user-content HTML interpolation (XSS prevention)
- `safeUrl(url)` — blocks non-http(s) URLs before using in `href`/`src`
- `window.onerror` and `window.onunhandledrejection` auto-report via `apiLogError()`

## JavaScript Conventions

- Vanilla ES2020, no build step, no framework, no npm
- No import/export — all files loaded via `<script>` tags; load order in `index.html` is significant
- Constants UPPER_CASE: `API`, `TRAVEL_STYLES`, `FLAGS`
- camelCase functions: `goToStep()`, `buildPayload()`
- `api` prefix for API wrappers: `apiLogin()`, `apiGetMe()`, `apiLogError()`
- Private vars prefixed `_`: `_fetchWithAuth()`, `_activeStopId`
- kebab-case CSS classes: `form-step`, `guide-tab`
