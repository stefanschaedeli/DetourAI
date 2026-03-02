# Travelman — KI-gestützter Reiseplaner

> An AI-powered road trip planner that builds a personalised day-by-day travel guide through an interactive, multi-agent conversation with Claude.

---

## Overview

Travelman lets you plan a complete road trip in minutes. You describe where you want to go and what matters to you; six specialised Claude agents then collaboratively research the route, stops, accommodations, activities, restaurants, and driving schedule — and hand you back a structured, budget-aware travel guide.

```
You fill a 5-step form
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
- **Parallel accommodation research** — budget / comfort / premium options per stop loaded simultaneously
- **Six specialised AI agents** — route architect, stop finder, accommodation researcher, activities, restaurants, day planner
- **Real driving times** — OSRM replaces AI estimates with actual road distances
- **Real-time progress** — Server-Sent Events stream every agent action to the browser
- **Budget tracking** — 45 % accommodation · 15 % food · CHF 80/stop activities · CHF 12/h fuel
- **Export** — download the final plan as PDF or PPTX
- **Resume** — browser-local state so you can pick up where you left off
- **Swiss-first** — all output in German, all prices in CHF

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser  (Vanilla JS, no build step)                   │
│  5-step form → route builder → acc grid → guide tabs    │
└──────────────────┬──────────────────────────────────────┘
                   │  HTTP + SSE  (via Nginx proxy)
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI  (11 endpoints)                                 │
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

Fill in **Start** and **Destination** plus travel dates. Optionally add via-points (waypoints you want to pass through, with optional fixed arrival dates and notes).

```
┌────────────────────────────────────────────────────────┐
│  Wohin geht die Reise?                   Step 1 / 5   │
├────────────────────────────────────────────────────────┤
│  Startort                 Hauptziel                    │
│  ┌──────────────────┐     ┌──────────────────┐         │
│  │  Liestal, CH     │     │  Paris, FR       │         │
│  └──────────────────┘     └──────────────────┘         │
│                                                        │
│  Startdatum               Enddatum                     │
│  ┌──────────────┐         ┌──────────────┐             │
│  │  01.07.2025  │         │  10.07.2025  │  →  10 Tage │
│  └──────────────┘         └──────────────┘             │
│                                                        │
│  + Via-Punkt hinzufügen                                │
│                                          [Weiter →]    │
└────────────────────────────────────────────────────────┘
```

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
- Max activities per stop (3 / 5 / 8)
- Max restaurants per stop (2 / 3 / 5)
- Search radius for activities (10 – 100 km)

### Step 4 — Accommodation & Budget

- Accommodation types: Hotel · Apartment · Camping · Hostel · Airbnb
- Must-have amenities: Pool · WiFi · Parking · Kitchen · Breakfast
- Hotel search radius (1 – 50 km)
- Max drive hours per day (1 – 10 h, default 4.5 h)
- Total budget in CHF (500 – 50 000)

### Step 5 — Summary & submit

Review everything, then click **Reise planen**.

---

### Route builder

Claude proposes **3 stop options** for the first segment. Pick one, and it immediately suggests the next. Keep picking until the full route is built, then confirm.

```
┌──────────────────────────────────────────────────────────────────┐
│  Route aufbauen                                                  │
│  Ausgewählte Stops:  Liestal  →  Bern  →  Lyon                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────┐   │
│  │  Grenoble      │   │  Valence       │   │  Avignon       │   │
│  │                │   │                │   │                │   │
│  │  Fahrtzeit 2.5h│   │  Fahrtzeit 2.1h│   │  Fahrtzeit 3.0h│   │
│  │                │   │                │   │                │   │
│  │  Bergkulisse,  │   │  Rhône-Tal,    │   │  Historische   │   │
│  │  UNESCO-Stadt  │   │  Lavendelfelder│   │  Altstadt      │   │
│  │  ★ 4.5         │   │  ★ 4.2         │   │  ★ 4.7         │   │
│  │   [Wählen]     │   │   [Wählen]     │   │   [Wählen]     │   │
│  └────────────────┘   └────────────────┘   └────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

### Accommodation selection

For each stop, three options are loaded in parallel. The remaining budget updates live after every selection.

```
┌──────────────────────────────────────────────────────────┐
│  Unterkunft wählen                                       │
│  Budget übrig: CHF 2'340 von CHF 5'000                   │
├──────────────────────────────────────────────────────────┤
│  📍 Grenoble                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Budget      │  │  Komfort     │  │  Premium     │   │
│  │              │  │              │  │              │   │
│  │ Hostel Central│  │ Hotel Ibis   │  │ Park Hyatt   │   │
│  │ CHF 45/Nacht │  │ CHF 89/Nacht │  │ CHF 210/Nacht│   │
│  │ WiFi · Zentrum│  │ WiFi·Parking │  │ Pool·Breakfast│  │
│  │  [Wählen]    │  │  [Wählen]    │  │  [Wählen]    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                          │
│                             [Planung starten →]          │
└──────────────────────────────────────────────────────────┘
```

---

### Planning progress

A live timeline shows each agent's work as SSE events arrive:

```
┌──────────────────────────────────────────┐
│  Reiseplan wird erstellt…                │
│                                          │
│  ✔  Route analysiert                     │
│  ✔  Grenoble — Aktivitäten geladen       │
│  ✔  Grenoble — Restaurants geladen       │
│  ⟳  Avignon — Aktivitäten werden geladen │
│  …                                       │
└──────────────────────────────────────────┘
```

---

### Travel guide

The finished plan is presented in four tabs:

```
┌────────────────────────────────────────────────────────────┐
│  Ihr Reiseplan                                             │
├──────────┬────────────┬────────────┬────────┤             │
│ Übersicht│Stops&Detail│ Tagesplan  │ Budget │             │
├──────────┴────────────┴────────────┴────────┤             │
│                                              │             │
│  Liestal → Bern → Lyon → Grenoble → Paris    │             │
│                                              │             │
│  5 Stops · 10 Tage · CHF 4'820 total         │             │
│  Ersparnis gegenüber Budget: CHF 180         │             │
│                                              │             │
│  [Google Maps öffnen]                        │             │
│                                              │             │
│  [PDF herunterladen]  [PPTX herunterladen]   │             │
└──────────────────────────────────────────────┘
```

| Tab | Content |
|-----|---------|
| **Übersicht** | Route visualisation, key stats, Google Maps link, download buttons |
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
python3 -m pytest tests/ -v                        # all 49 tests
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
| `POST` | `/api/plan-trip` | Submit form, receive first stop options |
| `POST` | `/api/select-stop/{job_id}` | Choose a stop, receive next options |
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
│   ├── main.py                      # FastAPI app — 11 endpoints
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
│   ├── tests/                       # 49 tests
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── js/
│       ├── state.js                 # global S object + localStorage
│       ├── api.js                   # all fetch() calls live here
│       ├── form.js                  # 5-step form
│       ├── route-builder.js
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
| Accommodation | 45 % of total budget |
| Food | 15 % of total budget |
| Activities | ~CHF 80 per stop |
| Fuel | CHF 12 per driving hour |

---

## License

MIT
