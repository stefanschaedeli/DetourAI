# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Full-stack AI-powered road trip planner. Users configure a trip in a 5-step form; specialized
Claude agents interactively build the route, research accommodations/activities/restaurants,
and produce a day-by-day travel guide. All communication uses Server-Sent Events (SSE) for
real-time progress streaming.

**Stack:** Python/FastAPI backend · Vanilla JS frontend · Redis job state · Celery workers ·
Nginx serving static files · Docker Compose deployment

---

## Build & Dev Commands

### Backend (FastAPI)
```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

### Frontend (static)
Open `frontend/index.html` directly, or let Nginx serve it via Docker.

### Type Generation (OpenAPI → TypeScript)
```bash
cd scripts && ./generate-types.sh  # emits frontend/js/types.d.ts
```

### Dependencies
```bash
cd backend && pip3 install -r requirements.txt
```

---

## Critical Rules

- **Never commit `.env`** — use `.env.example` as template
- **All user-facing text in German** — error messages, log entries, UI labels
- **Prices always in CHF**
- **TEST_MODE=true** → all agents use `claude-haiku-4-5` (cheap dev mode)
- **TEST_MODE=false** → Opus for route+planner, Sonnet for research
- **Job state in Redis** — key pattern `job:{job_id}`, TTL 24h
- **SSE stream closes** on `job_complete` or `job_error` event
- **Budget split:** 45% accommodation · 15% food · ~CHF 80/stop activities · CHF 12/h fuel
- **Google Maps APIs** for Geocoding, Directions, Places — `GOOGLE_MAPS_API_KEY` env var required
- **Frontend API prefix:** `/api` (Nginx proxy to backend:8000) — never use `localhost:8000` in JS

---

## Code Documentation

**Comment language:** English for all code comments, docstrings, and CLAUDE.md content.
User-facing strings (UI labels, error messages, API responses) remain in the user's language per i18n.

### Python (backend/)
- **File header:** One-line module docstring on every `.py` file (except `__init__.py`)
  `"""Route editing helpers — remove, add, reorder stops."""`
- **Class docstring:** Required on all classes (skip inline Pydantic request models)
- **Function docstring:** Required on functions with 3+ params or non-obvious behavior; skip trivial getters
- **Inline comments:** Explain *why*, not *what*
- **Section dividers:** `# ---------------------------------------------------------------------------`

### JavaScript (frontend/js/)
- **File header:** Every `.js` file starts with a description line + dependency contracts:
  ```
  // Guide Core — entry point, tab switching, stats.
  // Reads: S (state.js), Router (router.js).
  // Provides: showTravelGuide, renderGuide, switchGuideTab.
  ```
- **Function docs:** `/** ... */` on global/exported functions (those listed in `Provides:`)
- **Section dividers:** `// ---------------------------------------------------------------------------`
- No `@param`/`@returns` tags — `types.d.ts` handles types

### When to document
- **New files:** Full standard from the start
- **Changed files:** Add missing file header + docstrings on touched functions (boy scout rule)
- **Do NOT** rewrite comments in files you did not otherwise change

---

## Git Workflow (REQUIRED)
After **every** change, commit immediately as a patch release and push:

```bash
git add <changed files>
git commit -m "type: beschreibung"
git tag vX.X.Y        # increment patch number from latest tag
git push && git push --tags
```

- Version scheme: `x.x.y` — only increment `y` for each change
- Check current version with `git tag --sort=-v:refname | head -1`
- Commit message in German, type prefix in English (fix/feat/perf/docs/refactor)

---

## Worker Files

- `frontend/CLAUDE.md` — ownership, HTML/CSS/i18n assets, security, design system
- `frontend/js/core/CLAUDE.md` — foundation: state, auth, router, API client, i18n
- `frontend/js/maps/CLAUDE.md` — Google Maps: init, images, routes, guide map
- `frontend/js/communication/CLAUDE.md` — SSE protocol, progress overlay, debug log
- `frontend/js/guide/CLAUDE.md` — travel guide viewer: tabs, editing, lazy loading
- `frontend/js/features/CLAUDE.md` — planning pipeline + standalone pages
- `backend/CLAUDE.md` — FastAPI, models, utils, auth, testing, local debugging
- `backend/agents/CLAUDE.md` — agent models, orchestration pipeline, Celery tasks, prompts
- `infra/CLAUDE.md` — Docker Compose, Nginx, environment variables, deployment

