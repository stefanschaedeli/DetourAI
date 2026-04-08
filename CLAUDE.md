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

### Docker (full stack)
```bash
docker compose up --build          # start everything
docker compose up -d               # background
docker compose down                # stop
docker compose logs -f backend     # follow backend logs
```

### Type Generation (OpenAPI → TypeScript)
```bash
cd scripts && ./generate-types.sh  # emits frontend/js/types.d.ts
```

### Tests
```bash
cd backend && python3 -m pytest tests/ -v
cd backend && python3 -m pytest tests/test_models.py        # Pydantic validation only
cd backend && python3 -m pytest tests/test_endpoints.py     # API routes
cd backend && python3 -m pytest tests/test_agents_mock.py   # agents with mocked Anthropic
cd backend && python3 -m pytest tests/test_travel_db.py     # travel persistence DB
```

### Dependencies
```bash
cd backend && pip3 install -r requirements.txt
```

---

## Critical Rules

- **Never commit `.env`** — use `.env.example` as template
- **Agents always return valid JSON** — no markdown wrappers, no explanations
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

- `frontend/CLAUDE.md` — JS, HTML, CSS, i18n, SSE event names, state conventions
- `backend/CLAUDE.md` — FastAPI, models, utils, auth, testing, local debugging
- `backend/agents/CLAUDE.md` — agent models, orchestration pipeline, Celery tasks, prompts
- `infra/CLAUDE.md` — Docker Compose, Nginx, environment variables, deployment

---

## Architecture & Conventions

See `.planning/codebase/ARCHITECTURE.md` for system architecture.
See `.planning/codebase/CONVENTIONS.md` for naming and code patterns.
See `.planning/codebase/STACK.md` for technology stack details.
See `.planning/codebase/INTEGRATIONS.md` for external API integrations.

---

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
