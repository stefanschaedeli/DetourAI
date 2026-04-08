# frontend/CLAUDE.md

This worker owns `frontend/` — all JS, HTML, CSS, and i18n files.
Do NOT modify backend/, infra/, or docker-compose.yml.

## JS Worker Files

JS is organized into five specialized workers — each subdirectory has its own CLAUDE.md:

| Folder | Focus |
|--------|-------|
| `js/core/` | Foundation — state, auth, router, API client, i18n |
| `js/maps/` | Google Maps — init, images, routes, guide map |
| `js/communication/` | Backend bridge — SSE protocol, progress overlay, debug log |
| `js/guide/` | Travel guide viewer — tabs, editing, lazy loading |
| `js/features/` | Planning pipeline + standalone pages (form, settings, travels, etc.) |

## Non-JS Assets

| File | Responsibility |
|------|---------------|
| `index.html` | SPA entry point — `<script>` load order matters; grouped by worker |
| `styles.css` | All styles — see `DESIGN_GUIDELINE.md` for the design system |
| `i18n/de.json` | German translations |
| `i18n/en.json` | English translations |
| `i18n/hi.json` | Hindi translations |
| `js/types.d.ts` | Generated from OpenAPI — do not edit manually |

## i18n

- `t('key')` — translates using the active locale (de/en/hi)
- `setLocale(code)` — switches locale and re-renders UI
- `getLocale()` — returns current locale code
- `getFormattingLocale()` — returns BCP-47 locale for `Intl` formatters (e.g. `'de-CH'`)
- All user-facing strings must use `t()` — no hardcoded text in JS
- Translation files: `frontend/i18n/` (de.json, en.json, hi.json)

## Security

- `esc(str)` — REQUIRED for all user-content HTML interpolation (XSS prevention)
- `safeUrl(url)` — blocks non-http(s) URLs before using in `href`/`src`
- All `console.error()` calls must also call `apiLogError('error', msg, source, stack)`

## Design System

See `DESIGN_GUIDELINE.md` for the Apple-inspired design system (colors, spacing, components).
