# Travelman — KI-gestützter Reiseplaner

> An AI-powered road trip planner that builds a personalised day-by-day travel guide through an interactive, multi-agent conversation with Claude.

---

## Overview

Travelman lets you plan a complete road trip in minutes. You describe where you want to go and what matters to you; six specialised Claude agents then collaboratively research the route, stops, accommodations, activities, restaurants, and driving schedule — and hand you back a structured, budget-aware travel guide.

```
You fill a 6-step form  (or hit "Reise jetzt planen" from any step)
        ↓
AI proposes stop options — you pick the ones you want
        ↓
AI finds 3 accommodation options per stop — you choose
        ↓
6 agents run in parallel to research every detail
        ↓
Day-by-day travel guide  ·  PDF export  ·  PPTX export
```

---

## Features

- **Interactive route building** — Claude suggests stops segment by segment; you tap the ones you want
- **Geometry-aware stop placement** — before each agent call, OSRM measures the full remaining distance and tells the agent the ideal per-etappe distance; stops are placed evenly along the route, never bunched at start or end
- **Only real towns** — StopOptionsFinder is instructed to always return concrete towns/cities, never regions, mountain ranges or country names
- **Drive-limit enforcement** — every option gets an OSRM-verified drive time; options that exceed your limit are flagged with an orange warning badge
- **Route-adjust modal** — when *all* options exceed the limit a banner appears; one click opens a modal to either add extra days or insert a new via-point, re-running the agent automatically
- **Leaflet map in route builder** — live map with start pin, segment-target pin, and numbered option pins; dashed branch lines visualise each alternative; marker click scrolls to the option card
- **"Neu berechnen" bar** — free-text field to steer the next suggestion (e.g. "lieber Meeresküste") and re-run the agent with a custom instruction
- **Rich stop metadata** — options include population, altitude, language, climate note, must-see highlights, and family-friendliness
- **Parallel accommodation research** — budget / comfort / premium options per stop loaded simultaneously; accommodation type derived from user preference (not hardcoded "hotel")
- **Six specialised AI agents** — route architect, stop finder, accommodation researcher, activities, restaurants, day planner
- **Real driving times** — OSRM replaces AI estimates with actual road distances and kilometres
- **Agent-supplied coordinates** — StopOptionsFinder provides WGS84 lat/lon for every option; Nominatim result takes priority, agent coords serve as guaranteed fallback so all pins always appear
- **Real-time progress** — Server-Sent Events stream every agent action to the browser
- **Configurable budget split** — set the exact % allocation for accommodation, food, and activities via sliders with live CHF preview; validated to sum to 100 %
- **Min/max nights per stop** — control how long the agent stays at each location
- **Settings menu** — gear icon in the header exposes max activities and max restaurants per stop without cluttering the form
- **Sticky "Reise jetzt planen" bar** — a persistent footer button appears as soon as the required fields (start, destination, dates) are filled; lets you skip straight to planning from any form step
- **Interactive overview map in travel guide** — full route polyline (start → all stops → destination) with clickable pins; clicking a pin switches to the Stops & Details tab and scrolls to that stop's card
- **Export** — download the final plan as PDF or PPTX
- **Resume** — browser-local state so you can pick up where you left off
- **Swiss-first** — all output in German, all prices in CHF

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser  (Vanilla JS, no build step)                   │
│  6-step form → route builder → acc grid → guide tabs    │
└──────────────────┬──────────────────────────────────────┘
                   │  HTTP + SSE  (via Nginx proxy)
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI  (12 endpoints)                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  TravelPlannerOrchestrator                       │   │
│  │  ├── StopOptionsFinderAgent   (claude-sonnet-4-5)│   │
│  │  ├── AccommodationResearcher  (claude-sonnet-4-5)│   │
│  │  ├── ActivitiesAgent          (claude-sonnet-4-5)│   │
│  │  ├── RestaurantsAgent         (claude-sonnet-4-5)│   │
│  │  ├── RouteArchitectAgent      (claude-opus-4-5)  │   │
│  │  └── DayPlannerAgent          (claude-opus-4-5)  │   │
│  └──────────────────────────────────────────────────┘   │
└──────────┬──────────────────────┬───────────────────────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │   Redis     │        │   Celery    │
    │ job state   │        │  workers    │
    │ (24h TTL)   │        │             │
    └─────────────┘        └─────────────┘
```

### Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Frontend | Vanilla JS (ES2020), HTML5, CSS3 |
| Real-time | Server-Sent Events (sse-starlette) |
| Job queue | Redis + Celery |
| AI | Anthropic SDK — 6 Claude agents |
| Routing | OSRM (open-source road routing) |
| Geocoding | OpenStreetMap Nominatim |
| Export | fpdf2 (PDF), python-pptx (PPTX) |
| Infra | Docker Compose, Nginx |

---

## Quick start — Docker (recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) >= 24
- An [Anthropic API key](https://console.anthropic.com/)

### 1 — Clone the repo

```bash
git clone https://github.com/stefanschaedeli/travelman3.git
cd travelman3
```

### 2 — Create your environment file

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set your API key:

```env
ANTHROPIC_API_KEY=sk-ant-...   # required
TEST_MODE=true                  # true = cheap haiku model; false = opus/sonnet
REDIS_URL=redis://redis:6379
```

> **TEST_MODE=true** uses `claude-haiku-4-5` for all agents — ideal for development and quick tests. Set to `false` for production-quality output (uses Opus and Sonnet).

### 3 — Start all services

```bash
docker compose up --build
```

Four containers start:

| Container | Role | Port |
|-----------|------|------|
| `redis` | job state store | 6379 (internal) |
| `backend` | FastAPI app | 8000 (internal) |
| `celery` | background workers | — |
| `frontend` | Nginx + static files | **80** |

### 4 — Open the app

Navigate to **[http://localhost](http://localhost)**

```bash
docker compose down             # stop everything
docker compose logs -f backend  # follow backend logs
```

---

## Using the app

### Step 1 — Route

Fill in **Start** and **Destination** plus travel dates. Optionally add via-points (waypoints you want to pass through, with optional fixed arrival dates). Set the **max drive hours per day** slider.

As soon as these required fields are filled, a sticky **"✈ Reise jetzt planen"** bar appears at the bottom of the screen — click it at any time to skip the remaining steps and plan with defaults.

### Step 2 — Travellers

Set the number of adults, add children with their ages, and choose one or more **travel styles**:

| | | | |
|-|-|-|-|
| Abenteuer | Entspannung | Kultur | Romantik |
| Kulinarik | Roadtrip | Natur | Stadt |
| Wellness | Sport | Gruppe | Familie |
| Slow Travel | Party | | |

Add a free-text description of what would make this trip special.

### Step 3 — Activities

- Tag must-do activities (e.g. "Eiffelturm besuchen") — agents ensure these are included
- Max distance from accommodation (10 – 100 km)
- Max activities and restaurants per stop are in the **⚙ Settings** menu (header)

### Step 4 — Accommodation

- Accommodation types: Hotel · Apartment · Camping · Hostel · Airbnb
- Must-have amenities: Pool · WiFi · Parking · Kitchen · Breakfast
- Hotel search radius (1 – 50 km)
- Min / max nights per stop

### Step 5 — Budget

- Total budget in CHF
- **Budget split sliders** — set the exact % for accommodation, food, and activities; a live CHF preview updates as you drag; the form blocks submission if the percentages don't sum to 100 %

### Step 6 — Summary & submit

Review everything, then click **Reise planen**.

---

### Route builder

Claude proposes **3 stop options** for the current segment. The agent is given the exact total distance and the ideal per-etappe distance so options are evenly spaced — never too close to the start or the destination.

Pick an option, and it immediately suggests the next three. Keep picking until the full route is built, then confirm.

Each round displays:
- A **Leaflet map** with a green Start pin, a red Ziel pin, and blue numbered pins for each option; dashed coloured lines connect start → option → target for each branch
- A **"Neu berechnen"** bar to re-run the agent with a free-text instruction (e.g. "lieber Küste" or "Weingegend bevorzugt")
- Option cards stacked vertically, each with OSRM-verified drive time and distance, Google Maps link, and contextual metadata (altitude, language, must-sees, family score)
- An **orange warning badge** on cards whose OSRM drive time exceeds your limit
- A **"Route anpassen…"** banner if *all* cards exceed the limit — opens a modal to add days or insert a via-point

```
┌──────────────────────────────────────────────────────────────────┐
│  Route aufbauen                                                  │
│                                                                  │
│  [Sonderwunsch eingeben…]              [Neu berechnen]           │
│                                                                  │
│  Stop #3 → Paris  (Segment 1/1)    3 Tage verbleibend            │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  🗺  [Karte: S  ──┬── 1.Grenoble ──┬── Z:Paris ]        │    │
│  │                  ├── 2.Valence  ──┤                     │    │
│  │                  └── 3.Avignon  ──┘                     │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  direct   🇫🇷 Grenoble, FR                               │    │
│  │  2.5h Fahrt · 210 km    2 Nächte                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

### Accommodation selection

For each stop, three options are loaded in parallel. The accommodation type matches your preference (hotel, camping, etc.). The remaining budget updates live after every selection.

---

### Travel guide

The finished plan is presented in four tabs:

| Tab | Content |
|-----|---------|
| **Übersicht** | Route visualisation, key stats, Google Maps link, interactive Leaflet route map, download buttons |
| **Stops & Details** | Per-stop card: accommodation, top activities (duration / price / kid-friendly), top restaurants (cuisine / price range) |
| **Tagesplan** | Day-by-day breakdown with driving legs, highlights, and Maps route links |
| **Budget** | Itemised: accommodation · fuel · activities · food · ferries · total vs. budget |

---

## Local development (without Docker)

### Requirements

- Python 3.11+
- Redis running locally (`redis-server`)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # add your API key
python3 -m uvicorn main:app --reload --port 8000
```

### Celery worker (separate terminal)

```bash
cd backend
celery -A tasks worker --loglevel=info
```

### Frontend

Open `frontend/index.html` directly in your browser, or serve it with any static file server. For local dev without Nginx, change `API_BASE` in `frontend/js/api.js` to `http://localhost:8000/api`.

### Tests

```bash
cd backend
python3 -m pytest tests/ -v                        # all tests
python3 -m pytest tests/test_models.py             # Pydantic validation
python3 -m pytest tests/test_endpoints.py          # API routes
python3 -m pytest tests/test_agents_mock.py        # agents (no API key needed)
```

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `TEST_MODE` | | `true` | `true` = haiku (cheap dev mode); `false` = opus/sonnet |
| `REDIS_URL` | | `redis://localhost:6379` | Redis connection string |

---

## Agent model assignments

| Agent | Production | TEST_MODE=true |
|-------|-----------|----------------|
| RouteArchitectAgent | claude-opus-4-5 | claude-haiku-4-5 |
| StopOptionsFinderAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| AccommodationResearcherAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/plan-trip` | Submit form, receive first stop options (with OSRM + map anchors) |
| `POST` | `/api/select-stop/{job_id}` | Choose a stop, receive next options (with OSRM + map anchors) |
| `POST` | `/api/recompute-options/{job_id}` | Re-run StopOptionsFinder with optional `extra_instructions` |
| `POST` | `/api/patch-job/{job_id}` | Adjust job when all options exceed drive limit (add days or via-point) |
| `POST` | `/api/confirm-route/{job_id}` | Confirm route, begin accommodation loading |
| `POST` | `/api/start-accommodations/{job_id}` | Trigger parallel accommodation fetch |
| `POST` | `/api/select-accommodation/{job_id}` | Select accommodation for one stop |
| `POST` | `/api/confirm-accommodations/{job_id}` | Confirm all accommodation selections |
| `POST` | `/api/start-planning/{job_id}` | Launch full plan generation |
| `GET` | `/api/progress/{job_id}` | SSE stream of events and debug logs |
| `GET` | `/api/result/{job_id}` | Fetch completed travel plan (JSON) |
| `POST` | `/api/generate-output/{job_id}/{type}` | Generate PDF or PPTX (`type` = `pdf`/`pptx`) |
| `GET` | `/health` | Health check + active job count |

---

## Project structure

```
travelman3/
├── backend/
│   ├── main.py                      # FastAPI app — 12 endpoints
│   ├── orchestrator.py              # TravelPlannerOrchestrator
│   ├── agents/
│   │   ├── route_architect.py
│   │   ├── stop_options_finder.py
│   │   ├── accommodation_researcher.py
│   │   ├── activities_agent.py
│   │   ├── restaurants_agent.py
│   │   ├── day_planner.py
│   │   └── output_generator.py      # PDF + PPTX
│   ├── models/                      # Pydantic models
│   ├── tasks/                       # Celery tasks
│   ├── utils/                       # retry, geocoding, SSE logger, JSON parser
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── js/
│       ├── state.js                 # global S object + localStorage
│       ├── api.js                   # all fetch() calls live here
│       ├── form.js                  # 6-step form + quick-submit bar
│       ├── route-builder.js         # route builder + route-adjust modal
│       ├── accommodation.js
│       ├── progress.js              # SSE event handlers
│       └── guide.js                 # 4 output tabs
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── scripts/
│   └── generate-types.sh            # OpenAPI → TypeScript types
├── docker-compose.yml
└── outputs/                         # generated PDF / PPTX files
```

---

## Budget model

| Category | Allocation |
|----------|-----------|
| Accommodation | configurable % (default 60 %) |
| Food | configurable % (default 20 %) |
| Activities | configurable % (default 20 %) |
| Fuel | CHF 12 per driving hour |

---

## Changelog

### v2.0 (2026-03-03)

**Form overhaul — 6-step form**
- Form extended from 5 to 6 steps: Route · Travellers · Activities · Accommodation · **Budget** · Summary
- Max drive hours slider moved to Step 1 (Route) where it belongs
- New Step 5: budget split sliders for accommodation / food / activities with live CHF preview and 100 % validation
- Settings gear icon in header for max activities / restaurants per stop
- Step 4 (Accommodation): min / max nights per stop selectable
- Step 3 (Activities): label clarified to "Max. Distanz zu Übernachtungsort"
- New backend fields: `budget_accommodation_pct`, `budget_food_pct`, `budget_activities_pct`

**Route quality improvements**
- **Geometry-aware etappe planning** — `_calc_route_geometry()` queries OSRM for the full remaining distance before each agent call; StopOptionsFinder receives `segment_total_km`, `stops_remaining`, and `ideal_km_from_prev` so stops are evenly distributed
- **Only concrete towns** — SYSTEM_PROMPT now enforces that `region` is always a specific town/city, never a region or geographic area
- **Drive-limit flag** — `_enrich_options_with_osrm()` sets `drives_over_limit` on each option; flagged cards get an orange border and warning badge in the UI
- **Route-adjust modal** — when all 3 options exceed the drive limit, a banner with "Route anpassen…" button appears; the modal offers two options: add extra days or insert a via-point; `POST /api/patch-job/{job_id}` handles both, updates the job and recomputes immediately
- **Accommodation type fix** — `preferred_type` derived from `accommodation_styles[0]`; used in the prompt template and Unsplash queries instead of hardcoded "hotel"

**Sticky quick-submit bar**
- Persistent footer bar "✈ Reise jetzt planen" visible on all form steps once required fields are filled
- Allows skipping to planning without stepping through all 6 form steps

---

### v1.2.3 (2026-03-02)
- **Route lines on maps** — dashed branch lines (start → option → target) per alternative in the route-builder map; solid polyline through all stops in the guide overview map
- **Agent-supplied coordinates as fallback** — StopOptionsFinder returns WGS84 `lat`/`lon`; used when Nominatim geocoding fails

### v1.2.2 (2026-03-02)
- **Interactive map in travel guide overview** — Leaflet map with clickable stop pins; clicking navigates to the stop's detail card

### v1.2.1 (2026-03-02)
- **Start and segment-target pins on route-builder map** — green "S" and red "Z" pins geocoded server-side

### v1.2 (2026-03-02)
- **Leaflet map in route builder**, **"Neu berechnen" bar**, **OSRM-verified drive times**, **rich stop metadata**, **Google Maps link** per card, vertical card layout

### v1.1 (2026-03-01)
- Unsplash image galleries with lightbox support

### v1.0 (2026-02-28)
- Initial release — full 5-step form, 6 AI agents, SSE progress, PDF/PPTX export

---

## License

MIT
