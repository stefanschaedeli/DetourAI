# Travelman — KI-gestützter Reiseplaner

> An AI-powered road trip planner that builds a personalised day-by-day travel guide through an interactive, multi-agent conversation with Claude.

[![Current Version](https://img.shields.io/badge/version-v6.1.0-blue)](#releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](#license)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20·%20Vanilla%20JS%20·%20Redis%20·%20Docker-orange)](#tech-stack)
[![Agents](https://img.shields.io/badge/AI%20agents-10%20Claude%20agents-purple)](#ai-agents)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [AI Agents](#ai-agents)
- [API Reference](#api-reference)
- [Using the App](#using-the-app)
- [Local Development](#local-development)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Releases](#releases)
- [License](#license)

---

## Overview

Travelman lets you plan a complete road trip in minutes. You describe where you want to go and what matters to you; ten specialised Claude agents then collaboratively research the route, stops, accommodations, activities, restaurants, and driving schedule — and hand you back a structured, budget-aware travel guide.

```
You fill a 5-step form  →  define trip legs (Transit / Explore)
        ↓
AI proposes stop options per leg — you pick the ones you want
  (short segments: DetourOptionsAgent suggests scenic detours)
  (explore legs: ExploreZoneAgent discovers hidden gems in a zone)
        ↓
AI finds 3 accommodation options per stop — you choose
        ↓
10 agents run to research every detail
        ↓
Day-by-day travel guide  ·  PDF export  ·  PPTX export
```

---

## Features

### Trip Planning
- **Leg-based trip architecture** — build trips from Transit legs (A → B routing) and Explore legs (discover a geographic zone)
- **Interactive route building** — Claude suggests stops segment by segment; you pick the ones you want
- **Explore mode** — define a zone on the map and let ExploreZoneAgent discover anchor points, scenic spots, and hidden gems via a guided questionnaire
- **Geometry-aware stop placement** — OSRM measures the full remaining distance; stops are placed evenly along the route
- **Detour fallback** — when a segment is too short for classic stops, DetourOptionsAgent proposes scenic side-trips
- **"Direkt weiterfahren" option** — skip a stop and add freed nights to the next destination
- **Rundkurs display** — explore legs show a circular route through discovered stops

### Route Quality
- **Only real towns** — StopOptionsFinder always returns concrete towns/cities, never regions
- **Drive-limit enforcement** — OSRM-verified drive times; options exceeding the limit get a warning badge
- **Route-adjust modal** — when all options exceed the limit, one click adds days or inserts a via-point
- **Configurable proximity filter** — set minimum distance from start/target to prevent stop bunching
- **Real driving times** — OSRM replaces AI estimates with actual road distances

### Accommodation & Budget
- **Parallel accommodation research** — budget / comfort / premium options per stop loaded simultaneously
- **Configurable budget split** — set % allocation for accommodation, food, and activities with live CHF preview
- **Budget tracking** — remaining budget updates live after every accommodation selection

### AI & Agents
- **10 specialised AI agents** — route architect, stop finder, detour finder, explore zone, accommodation researcher, activities, restaurants, day planner, travel guide, trip analysis
- **Real-time progress** — Server-Sent Events stream every agent action to the browser
- **Live progress overlay** — spinner log with green checkmarks during all wait phases

### Output & Persistence
- **Travel guide with 4 tabs** — overview map, stops & details, day-by-day plan, budget breakdown
- **Export** — download as PDF or PPTX
- **Trip analysis** — AI-powered post-planning analysis with requirement tags and keyword highlighting
- **Saved trips** — SQLite persistence with rename, star rating (0–5), replan, and delete
- **Resume** — browser-local state so you can pick up where you left off

### UX & Design
- **Travel-Forward design** — sky-blue + adventure-orange branded UI
- **Lucide SVG icons** — no emoji, consistent icon set throughout
- **Full accessibility** — focus rings, aria labels, screen-reader compatibility, keyboard navigation
- **Mobile-responsive** — dynamic viewport height, visible step labels on small screens
- **Collapsible stops** — sidebar navigation and calendar tab in the travel guide
- **Google Maps integration** — Places API photos, interactive maps, photo strips with lightbox

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) >= 24
- An [Anthropic API key](https://console.anthropic.com/)

### 1 — Clone & configure

```bash
git clone https://github.com/stefanschaedeli/travelman3.git
cd travelman3
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...   # required
TEST_MODE=true                  # true = cheap haiku; false = opus/sonnet
REDIS_URL=redis://redis:6379
```

### 2 — Start

```bash
docker compose up --build
```

| Container | Role | Port |
|-----------|------|------|
| `redis` | Job state store | 6379 (internal) |
| `backend` | FastAPI app | 8000 (internal) |
| `celery` | Background workers | — |
| `frontend` | Nginx + static files | **80** |

### 3 — Open

Navigate to **http://localhost**

```bash
docker compose down             # stop everything
docker compose logs -f backend  # follow backend logs
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser  (Vanilla JS, no build step)                   │
│  5-step form → legs builder → route builder →           │
│  acc grid → guide tabs                                  │
└──────────────────┬──────────────────────────────────────┘
                   │  HTTP + SSE  (via Nginx proxy)
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI  (25+ endpoints)                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │  TravelPlannerOrchestrator                       │   │
│  │  ├── RouteArchitectAgent      (claude-opus-4-5)  │   │
│  │  ├── StopOptionsFinderAgent   (claude-sonnet-4-5)│   │
│  │  ├── DetourOptionsAgent       (claude-haiku-4-5) │   │
│  │  ├── ExploreZoneAgent         (claude-sonnet-4-5)│   │
│  │  ├── AccommodationResearcher  (claude-sonnet-4-5)│   │
│  │  ├── ActivitiesAgent          (claude-sonnet-4-5)│   │
│  │  ├── RestaurantsAgent         (claude-sonnet-4-5)│   │
│  │  ├── DayPlannerAgent          (claude-opus-4-5)  │   │
│  │  ├── TravelGuideAgent         (claude-sonnet-4-5)│   │
│  │  └── TripAnalysisAgent        (claude-sonnet-4-5)│   │
│  └──────────────────────────────────────────────────┘   │
└──────────┬──────────────────────┬───────────────────────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │   Redis     │        │   Celery    │
    │ job state   │        │  workers    │
    │ (24h TTL)   │        │             │
    └─────────────┘        └─────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Frontend | Vanilla JS (ES2020), HTML5, CSS3 |
| Real-time | Server-Sent Events (sse-starlette) |
| Job queue | Redis + Celery |
| AI | Anthropic SDK — 10 Claude agents |
| Maps | Google Maps JS SDK + Places API |
| Routing | OSRM (open-source road routing) |
| Geocoding | OpenStreetMap Nominatim |
| Icons | Lucide SVG |
| Export | fpdf2 (PDF), python-pptx (PPTX) |
| Infra | Docker Compose, Nginx |

### Data Stores

| Store | Technology | Lifetime | Content |
|-------|-----------|----------|---------|
| **Job state** | Redis | 24h TTL | Live planning sessions, SSE queues, agent results |
| **Travel history** | SQLite (`data/travels.db`) | Permanent | Saved trips with metadata and full plan JSON |

---

## AI Agents

Travelman uses ten specialised Claude agents. Each has a single, clearly scoped task, communicates exclusively via structured JSON, and is orchestrated by `TravelPlannerOrchestrator`.

### Agent Model Assignments

| Agent | Production | TEST_MODE=true |
|-------|-----------|----------------|
| RouteArchitectAgent | claude-opus-4-5 | claude-haiku-4-5 |
| StopOptionsFinderAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DetourOptionsAgent | claude-haiku-4-5 | claude-haiku-4-5 |
| ExploreZoneAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| AccommodationResearcherAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |
| TravelGuideAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| TripAnalysisAgent | claude-sonnet-4-5 | claude-haiku-4-5 |

### Agent Details

**RouteArchitectAgent** (`claude-opus-4-5`) — Analyses the full trip and produces a high-level multi-segment route plan: which cities to pass through, how many days per segment, and the logical order of all waypoints. Uses Opus for its ability to reason across the entire trip simultaneously.

**StopOptionsFinderAgent** (`claude-sonnet-4-5`) — For each route segment, proposes 3 stop options: `direct` (shortest path), `scenic` (landscape-first), and `cultural` (historically interesting). In explore mode, types become `anker` (anchor point), `landschaft` (scenic), and `geheimtipp` (hidden gem). Streams partial JSON so cards appear incrementally. All options are OSRM-enriched with real drive times.

**DetourOptionsAgent** (`claude-haiku-4-5`) — Fallback agent for segments too short for classic stops. Proposes 3 deliberate side-trip destinations off the direct route. No proximity filter applied — detours may be close to departure. Always uses Haiku as it is a lightweight fallback.

**ExploreZoneAgent** (`claude-sonnet-4-5`) — Two-pass workflow for explore legs. First pass: generates clarifying questions about the user's interests for the zone. Second pass: uses the answers to discover stops categorised as anchor points, scenic spots, and hidden gems within the defined zone bbox.

**AccommodationResearcherAgent** (`claude-sonnet-4-5`) — Finds 3 accommodation options per stop at budget / comfort / premium tiers. Type matches user preference (hotel, camping, hostel, apartment, Airbnb). Tracks remaining budget across all stops.

**ActivitiesAgent** (`claude-sonnet-4-5`) — Researches activities and attractions per stop, tailored to travel styles and group composition. Wikipedia enrichment adds cultural context for the day planner.

**RestaurantsAgent** (`claude-sonnet-4-5`) — Recommends restaurants per stop matching travel styles and food budget, with cuisine type, price range, and a recommended dish.

**DayPlannerAgent** (`claude-opus-4-5`) — Assembles the day-by-day travel plan from all agent outputs: schedules driving legs, distributes activities, ensures rest days, and writes narrative summaries. Uses Opus for cross-trip reasoning.

**TravelGuideAgent** (`claude-sonnet-4-5`) — Generates a narrative travel guide with storytelling descriptions for each stop and day.

**TripAnalysisAgent** (`claude-sonnet-4-5`) — Post-planning analysis that evaluates how well the generated plan meets the original requirements, with requirement tags and keyword highlighting.

---

## API Reference

### Planning Flow

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/plan-trip` | Submit form, receive first stop options |
| `POST` | `/api/select-stop/{job_id}` | Choose a stop, receive next options |
| `POST` | `/api/recompute-options/{job_id}` | Re-run StopOptionsFinder with custom instructions |
| `POST` | `/api/patch-job/{job_id}` | Adjust job (add days or via-point) |
| `POST` | `/api/confirm-route/{job_id}` | Confirm route, begin accommodation loading |
| `POST` | `/api/start-accommodations/{job_id}` | Trigger parallel accommodation fetch |
| `POST` | `/api/select-accommodation/{job_id}` | Select accommodation for one stop |
| `POST` | `/api/confirm-accommodations/{job_id}` | Confirm all accommodation selections |
| `POST` | `/api/start-planning/{job_id}` | Launch full plan generation |
| `POST` | `/api/answer-explore-questions` | Submit answers to explore zone questionnaire |
| `GET` | `/api/progress/{job_id}` | SSE stream of events and debug logs |
| `GET` | `/api/result/{job_id}` | Fetch completed travel plan (JSON) |
| `POST` | `/api/generate-output/{job_id}/{type}` | Generate PDF or PPTX |
| `GET` | `/health` | Health check + active job count |

### Travel History (SQLite)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/travels` | List all saved trips (metadata only) |
| `POST` | `/api/travels` | Save a completed plan |
| `GET` | `/api/travels/{id}` | Load full plan JSON |
| `PATCH` | `/api/travels/{id}` | Update name and/or rating |
| `DELETE` | `/api/travels/{id}` | Delete a saved trip |
| `POST` | `/api/travels/{id}/replan` | Re-run agents against saved route |

---

## Using the App

### Step 1 — Route

Fill in **Start** and **Destination** plus travel dates. Optionally add via-points. Set the **max drive hours per day** slider. As soon as the required fields are filled, a sticky **"Reise jetzt planen"** bar appears.

### Step 2 — Travellers & Styles

Set adults, add children with ages, and choose travel styles (Abenteuer, Entspannung, Kultur, Romantik, Kulinarik, Roadtrip, Natur, Stadt, Wellness, Sport, Gruppe, Familie, Slow Travel, Party). Add a free-text trip description.

### Step 3 — Trip Legs

Define your trip legs as **Transit** (drive from A to B with stops) or **Explore** (discover a geographic zone). Each leg shows a map with the zone or route segment.

### Step 4 — Accommodation & Activities

- Accommodation types: Hotel · Apartment · Camping · Hostel · Airbnb
- Must-have amenities: Pool · WiFi · Parking · Kitchen · Breakfast
- Must-do activities as tags, max distance from accommodation
- Min / max nights per stop

### Step 5 — Budget & Submit

- Total budget in CHF with % split sliders (accommodation / food / activities)
- Review summary and submit

### Route Builder

Claude proposes **3 stop options** per segment, evenly spaced via OSRM geometry. Pick options to build the route iteratively. Features:

- Google Maps with numbered pins and branch lines
- **"Neu berechnen"** bar for custom re-runs (e.g. "lieber Küste")
- Orange warning badges for drive-limit violations
- Blue "Umweg-Optionen" banner for detour suggestions
- Route-adjust modal when all options exceed the limit

### Travel Guide

Four tabs in the finished plan:

| Tab | Content |
|-----|---------|
| **Übersicht** | Route map, key stats, Google Maps link, downloads |
| **Stops & Details** | Per-stop card: accommodation, activities, restaurants |
| **Tagesplan** | Day-by-day breakdown with driving legs and highlights |
| **Budget** | Itemised: accommodation · fuel · activities · food · total vs. budget |

---

## Local Development

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

### Celery Worker (separate terminal)

```bash
cd backend
celery -A tasks worker --loglevel=info
```

### Frontend

Open `frontend/index.html` directly, or serve with any static file server. For local dev without Nginx, change `API_BASE` in `frontend/js/api.js` to `http://localhost:8000/api`.

### Tests

```bash
cd backend
python3 -m pytest tests/ -v                        # all tests
python3 -m pytest tests/test_models.py             # Pydantic validation
python3 -m pytest tests/test_endpoints.py          # API routes
python3 -m pytest tests/test_agents_mock.py        # agents (no API key needed)
python3 -m pytest tests/test_travel_db.py          # travel persistence
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `TEST_MODE` | No | `true` | `true` = haiku (cheap dev); `false` = opus/sonnet |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection string |
| `GOOGLE_MAPS_API_KEY` | No | — | Google Maps JS SDK + Places API |

### Budget Model

| Category | Allocation |
|----------|-----------|
| Accommodation | configurable % (default 60%) |
| Food | configurable % (default 20%) |
| Activities | configurable % (default 20%) |
| Fuel | CHF 12 per driving hour |

---

## Project Structure

```
travelman3/
├── backend/
│   ├── main.py                        # FastAPI app — 25+ endpoints
│   ├── orchestrator.py                # TravelPlannerOrchestrator (leg-sequential)
│   ├── agents/
│   │   ├── _client.py                 # shared Anthropic client + model selector
│   │   ├── route_architect.py         # RouteArchitectAgent (opus)
│   │   ├── stop_options_finder.py     # StopOptionsFinderAgent (sonnet, streaming)
│   │   ├── detour_options_agent.py    # DetourOptionsAgent (haiku, fallback)
│   │   ├── explore_zone_agent.py      # ExploreZoneAgent (sonnet, two-pass)
│   │   ├── accommodation_researcher.py
│   │   ├── activities_agent.py        # + WikipediaEnricher
│   │   ├── restaurants_agent.py
│   │   ├── day_planner.py             # DayPlannerAgent (opus)
│   │   ├── travel_guide_agent.py      # TravelGuideAgent (sonnet)
│   │   ├── trip_analysis_agent.py     # TripAnalysisAgent (sonnet)
│   │   └── output_generator.py        # PDF + PPTX
│   ├── models/
│   │   ├── travel_request.py          # TravelRequest (leg-based)
│   │   ├── travel_response.py         # TravelPlan, TravelStop, DayPlan
│   │   ├── stop_option.py             # StopOption, StopOptionsResponse
│   │   ├── accommodation_option.py    # AccommodationOption, BudgetState
│   │   ├── trip_leg.py                # TripLeg, Transit/Explore modes
│   │   └── via_point.py               # ViaPoint, ZoneBBox, ExploreStop
│   ├── tasks/
│   │   ├── run_planning_job.py        # Celery: full orchestration + explore pause
│   │   └── prefetch_accommodations.py # Celery: parallel acc fetch
│   ├── utils/
│   │   ├── debug_logger.py            # DebugLogger + SSE subscriber manager
│   │   ├── maps_helper.py             # geocode, OSRM routing, Maps URLs
│   │   ├── retry_helper.py            # call_with_retry() + exponential backoff
│   │   ├── json_parser.py             # parse_agent_json()
│   │   ├── travel_db.py               # SQLite persistence
│   │   ├── hotel_price_fetcher.py     # hotel price fetching
│   │   └── image_fetcher.py           # destination image fetching
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_models.py             # Pydantic validation tests
│   │   ├── test_endpoints.py          # API route tests
│   │   ├── test_agents_mock.py        # agent tests with mocked Anthropic
│   │   └── test_travel_db.py          # travel persistence tests
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── js/
│       ├── state.js                   # global S object + localStorage
│       ├── api.js                     # all fetch() + SSE calls
│       ├── form.js                    # 5-step form + legs builder
│       ├── route-builder.js           # route builder + explore UI
│       ├── accommodation.js           # parallel acc loading + grid
│       ├── progress.js                # SSE progress handlers
│       ├── guide.js                   # 4-tab travel guide
│       ├── travels.js                 # saved trips drawer
│       ├── maps.js                    # map rendering helpers
│       ├── loading.js                 # loading state UI
│       ├── sse-overlay.js             # SSE progress overlay
│       └── types.d.ts                 # generated from OpenAPI
├── docs/
│   └── database.md                    # DB schema + API reference
├── infra/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── scripts/
│   └── generate-types.sh             # OpenAPI → TypeScript types
├── data/
│   └── travels.db                     # SQLite (auto-created)
├── docker-compose.yml
└── outputs/                           # generated PDF / PPTX files
```

---

## Releases

### v6.1.0 — Trip Legs & Explore Mode (2026-03-11)

Major architectural upgrade: trips are now composed of **legs** instead of flat segment sequences.

- **Leg-based trip architecture** — TravelRequest refactored from flat via-points to typed `TripLeg` objects (Transit or Explore mode)
- **Explore mode** — new leg type that lets users define a geographic zone and discover stops via a guided questionnaire
- **ExploreZoneAgent** — new two-pass agent: generates questions → processes answers → returns categorised stops (anker/landschaft/geheimtipp)
- **StopOptionsFinder explore branch** — new option types for explore legs: anchor points, scenic spots, hidden gems
- **Legs Builder UI** — Step 3 redesigned with Transit/Explore leg cards and map zone selection
- **Explore UI in Route Builder** — zone guidance overlay, circular route display, explore questionnaire flow
- **Orchestrator refactored** — leg-sequential planning with explore-phase pause/resume logic
- **POST /api/answer-explore-questions** — new endpoint for explore questionnaire answers
- **All tests updated** for legs-based architecture

### v6.0.0 — Google Maps & UX Overhaul (2026-03-10)

Complete frontend redesign and map provider migration.

- **Google Maps JS SDK migration** — replaced Leaflet & Unsplash with Google Maps + Places API
- **Google Maps Places API** — real photos via Nearby Search, photo strips with lightbox
- **Travel-Forward rebrand** — sky-blue + adventure-orange design system
- **Lucide SVG icons** — all emojis and text icons replaced with consistent SVGs
- **Full accessibility pass** — focus rings, aria labels, sr-only labels, keyboard navigation, screen-reader compatibility
- **Collapsible stops + sidebar navigation** — improved travel guide UX with calendar tab
- **Full-width layout** — gallery UX with lightbox navigation
- **Step indicators as click navigation** — jump to completed steps
- **Auto-balancing budget sliders** — automatically maintain 100% sum
- **Mobile improvements** — `100dvh` viewport, visible step labels on small screens
- **Inline field validation** — replaced `alert()` with inline error messages
- **Wait-time hint + cancel button** — user feedback during long planning phases
- **Advanced settings** — proximity sliders hidden under expandable section
- **Performance** — parallelised StopOptionsFinder enrichment, reduced timeouts, eliminated geocoding duplication
- **529 Overloaded error handling** — exponential backoff retry for API overload

### v5.1.x — Travel Guide & Trip Analysis (2026-03-09)

- **Travel guide agent** — narrative storytelling guide with hourly day plans per stop
- **Trip analysis agent** — post-planning requirement evaluation with tags and keyword highlighting
- **Replan saved trips** — re-run agents against saved route and accommodations
- **Accommodation system overhaul** — free-text wishes, all options included in final plan
- **Rename + star rating** — inline rename and 0–5 star widget for saved trips
- **SSE via Redis relay** — Celery worker events reliably forwarded to FastAPI
- **Database documentation** — full schema reference in `docs/database.md`

### v5.0.0 — Progress Overlay & Skip Stops (2026-03-08)

- **Live progress overlay** — semi-transparent overlay with spinner log during all three wait phases; each step flips to a green checkmark on completion
- **"Direkt weiterfahren"** — skip a stop and redistribute freed nights to the next destination
- **Proximity filter in GUI** — two sliders to control minimum distance from start/target
- **Geo-bounded detours** — DetourOptionsAgent uses explicit bounding box (±1.5°) to keep suggestions in range
- **Retry optimisation** — skip retry pass when 0 valid stops, go directly to DetourOptionsAgent
- **Correct map markers** — "S" marker always shows the last confirmed stop

### v4.0.x — Persistence & Detour Agent (2026-03-07)

- **SQLite travel history** — "Meine Reisen" with save, load, and delete
- **DetourOptionsAgent** — automatic fallback when StopOptionsFinder returns 0 valid options on short segments
- **Rundreise mode** — round-trip detection with deliberate detour options (left, right, adventure)
- **Interactive map markers** — click-to-select, hover tooltips, number matching
- **Minimum stop distance validation** — proximity filter for stop placement
- **Rundreise threshold** — minimum 200 km to prevent false positives

### v4.0.0 — Accommodation Agent Redesign (2026-03-07)

- **Style-based accommodation search** — 3 options based on travel style instead of hardcoded types
- **UTM VM Docker host delegation** — Docker deployment from virtual machines
- **Booking.com deeplinks** — direct booking links and "Geheimtipp" option

### v3.1 — Performance & Security (2026-03-05)

- **4x speed improvement** — parallelised route option display
- **Security hardening** — XSS prevention, job enumeration protection, port restrictions
- **Docker deploy pipeline** — fixed OUTPUTS_DIR path resolution

### v2.0 — Form Overhaul (2026-03-03)

- **6-step form** → Route · Travellers · Activities · Accommodation · Budget · Summary
- **Budget split sliders** — configurable % with live CHF preview and 100% validation
- **Geometry-aware etappe planning** — OSRM-measured distances for even stop distribution
- **Drive-limit enforcement** — OSRM-verified times with orange warning badges
- **Route-adjust modal** — add days or insert via-points when all options exceed limits
- **Sticky quick-submit bar** — "Reise jetzt planen" visible from any form step

### v1.2.x — Maps & Routing (2026-03-02)

- **Leaflet map in route builder** — start/target pins, numbered option pins, dashed branch lines
- **Interactive guide map** — clickable stop pins navigating to detail cards
- **Agent-supplied coordinates** — WGS84 lat/lon fallback when geocoding fails
- **"Neu berechnen" bar** — free-text instruction to re-run the agent
- **OSRM-verified drive times** — real road distances replace AI estimates

### v1.1 — Image Galleries (2026-03-01)

- Unsplash image galleries with lightbox support

### v1.0 — Initial Release (2026-02-28)

- Full 5-step form with travel style selection
- 6 AI agents with structured JSON communication
- Server-Sent Events for real-time progress streaming
- PDF and PPTX export
- Swiss-first: all output in German, all prices in CHF

---

## License

MIT
