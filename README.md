# Travelman — KI-gestützter Reiseplaner

> An AI-powered road trip planner that builds a personalised day-by-day travel guide through an interactive, multi-agent conversation with Claude.

---

## Overview

Travelman lets you plan a complete road trip in minutes. You describe where you want to go and what matters to you; seven specialised Claude agents then collaboratively research the route, stops, accommodations, activities, restaurants, and driving schedule — and hand you back a structured, budget-aware travel guide.

```
You fill a 6-step form  (or hit "Reise jetzt planen" from any step)
        ↓
AI proposes stop options — you pick the ones you want
  (if the route segment is too short: DetourOptionsAgent suggests scenic detours)
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
- **Detour fallback** — when a route segment is too short for classic in-between stops (proximity filter removes all candidates), DetourOptionsAgent automatically proposes scenic side-trip options with a blue info banner in the UI
- **Only real towns** — StopOptionsFinder is instructed to always return concrete towns/cities, never regions, mountain ranges or country names
- **Drive-limit enforcement** — every option gets an OSRM-verified drive time; options that exceed your limit are flagged with an orange warning badge
- **Route-adjust modal** — when *all* options exceed the limit a banner appears; one click opens a modal to either add extra days or insert a new via-point, re-running the agent automatically
- **Rundreise (round-trip) mode** — when you have much more time than the direct route needs, the app offers a Rundreise modal; in this mode StopOptionsFinder proposes deliberate detours (left, right, adventure) instead of stepping toward the target
- **Leaflet map in route builder** — live map with start pin, segment-target pin, and numbered option pins; dashed branch lines visualise each alternative; marker click scrolls to the option card
- **"Neu berechnen" bar** — free-text field to steer the next suggestion (e.g. "lieber Meeresküste") and re-run the agent with a custom instruction
- **Rich stop metadata** — options include population, altitude, language, climate note, must-see highlights, and family-friendliness
- **Parallel accommodation research** — budget / comfort / premium options per stop loaded simultaneously; accommodation type derived from user preference (not hardcoded "hotel")
- **Seven specialised AI agents** — route architect, stop finder, detour finder, accommodation researcher, activities, restaurants, day planner
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
│  │  ├── RouteArchitectAgent      (claude-opus-4-5)  │   │
│  │  ├── StopOptionsFinderAgent   (claude-sonnet-4-5)│   │
│  │  ├── DetourOptionsAgent       (claude-haiku-4-5) │   │
│  │  ├── AccommodationResearcher  (claude-sonnet-4-5)│   │
│  │  ├── ActivitiesAgent          (claude-sonnet-4-5)│   │
│  │  ├── RestaurantsAgent         (claude-sonnet-4-5)│   │
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
| AI | Anthropic SDK — 7 Claude agents |
| Routing | OSRM (open-source road routing) |
| Geocoding | OpenStreetMap Nominatim |
| Export | fpdf2 (PDF), python-pptx (PPTX) |
| Infra | Docker Compose, Nginx |

---

## AI Agents

Travelman uses seven specialised Claude agents. Each agent has a single, clearly scoped task, communicates exclusively via structured JSON, and is orchestrated by `TravelPlannerOrchestrator`.

---

### RouteArchitectAgent — `claude-opus-4-5`

**What it does:** Analyses the full trip (start, destination, via-points, duration, travel styles, budget) and produces a high-level multi-segment route plan — which cities to pass through, how many days per segment, and the logical order of all waypoints.

**When it runs:** Once at the very start of a planning job, before any stop selection.

**Input:** Full `TravelRequest` (start, destination, via-points, dates, styles, adults, children, budget).

**Output:** A JSON route plan with ordered segments, estimated days per segment, and contextual notes the downstream agents use as a shared reference.

**Why Opus:** Route architecture requires understanding the whole trip at once — tradeoffs between segments, seasonal factors, geographic logic — so it uses the most capable model.

---

### StopOptionsFinderAgent — `claude-sonnet-4-5`

**What it does:** For each route segment, proposes exactly 3 concrete intermediate stop options. In standard mode the three types are `direct` (shortest path toward the target), `scenic` (landscape-first detour), and `cultural` (historically or culturally interesting alternative). In Rundreise mode the types become `umweg_links`, `umweg_rechts`, and `abenteuer`.

**When it runs:** Interactively — once per stop selection round. Also re-runs when the user clicks "Neu berechnen" with a custom instruction.

**Input:** Current position, segment target, travel styles, remaining days, OSRM geometry data (total km, ideal km per etappe, minimum distances from origin and target), and optional extra instructions.

**Streaming:** Streams partial JSON so each option card appears in the browser as soon as it is complete, not after all three are done.

**OSRM enrichment:** After the agent responds, every option is geocoded (Nominatim) and OSRM-routed; the real drive hours and km replace the agent's estimates. Options that are too close to the trip origin or the segment target are silently filtered; if fewer than 3 remain, the agent is retried once with a stronger distance hint.

**Output:** 3 option objects with region, country, lat/lon, drive_hours, drive_km, nights, highlights, teaser, population, altitude, language, climate note, must-see list.

---

### DetourOptionsAgent — `claude-haiku-4-5`

**What it does:** A fallback agent that activates automatically when StopOptionsFinderAgent produces 0 valid options after its retry (this happens on very short route segments where the proximity filter eliminates all candidates). Instead of showing an empty container, it proposes 3 deliberate *side-trip* destinations that lie off the direct line — `umweg_1` (left/west), `umweg_2` (right/east), and `umweg_3` (surprising third direction).

**When it runs:** Only when both passes of StopOptionsFinder return 0 valid stops. Typical trigger: a segment shorter than ~100 km where the min-distance-from-origin and min-distance-from-target constraints leave no room for a classic in-between stop (example: Basel → Bern, ~95 km).

**Key difference from StopOptionsFinder:** No proximity filter is applied — detour options are allowed to be geographically close to the start, because they are by definition off-axis. The rule instead is that each detour must be reachable from the departure point in ≤ max_drive_hours, *and* the segment target must also be reachable from the detour in ≤ max_drive_hours.

**Frontend:** The UI shows all three detour cards with the same layout as normal stop cards, plus a blue info banner at the top explaining that these are deliberate side-trips, not classic waypoints.

**Output:** Same JSON structure as StopOptionsFinder options, with `is_detour: true` flag and `option_type` values `umweg_1` / `umweg_2` / `umweg_3`.

---

### AccommodationResearcherAgent — `claude-sonnet-4-5`

**What it does:** For each selected stop, finds 3 concrete accommodation options at three budget tiers: budget-friendly, comfortable mid-range, and premium. The accommodation type (hotel, camping, hostel, apartment, Airbnb) matches the user's preference.

**When it runs:** After the full route is confirmed, in parallel for all stops via Celery. The frontend starts loading accommodation cards as soon as each stop's result arrives — it does not wait for all stops to finish.

**Input:** Stop location, accommodation type preference, must-have amenities, hotel search radius, remaining budget allocated to accommodation, number of nights, number of adults and children.

**Budget tracking:** A `BudgetState` object tracks how much has been committed across all previously confirmed stops; the agent is told the remaining accommodation budget so it calibrates price ranges realistically.

**Output:** 3 accommodation objects per stop with name, address, price per night, total price, amenities, description, and a booking URL hint.

---

### ActivitiesAgent — `claude-sonnet-4-5`

**What it does:** For each stop, researches and recommends top activities and attractions tailored to the group's travel styles, the number of activity days at that stop, and the activities budget. Must-do activities specified by the user in the form are always included.

**When it runs:** As part of the main parallel planning job, alongside RestaurantsAgent and DayPlannerAgent.

**Wikipedia enrichment:** After the agent responds, a `WikipediaEnricher` fetches the Wikipedia summary for each stop city and appends cultural context that the day planner agent can use.

**Input:** Stop name and country, travel styles, number of adults and children, activity days, activities budget, user must-do list, max activities per stop.

**Output:** A ranked list of activities with name, description, duration in hours, estimated price in CHF, whether it is kid-friendly, and the activity category.

---

### RestaurantsAgent — `claude-sonnet-4-5`

**What it does:** For each stop, recommends restaurants and dining experiences that match the group's travel styles and food budget. Considers the local cuisine of the region and the group composition (kids, adults, dietary preferences).

**When it runs:** In parallel with ActivitiesAgent during the main planning job.

**Input:** Stop name and country, travel styles, food budget, number of adults and children, max restaurants per stop.

**Output:** A list of restaurant recommendations with name, cuisine type, price range (CHF per person), description, and a recommended dish.

---

### DayPlannerAgent — `claude-opus-4-5`

**What it does:** Takes all the research — stops, accommodations, activities, restaurants, OSRM drive times — and assembles a coherent, realistic day-by-day travel plan. It schedules driving legs on the right days, distributes activities across the stay, ensures rest days where appropriate, and writes descriptive daily summaries.

**When it runs:** Last in the pipeline, after all other agents have finished for all stops.

**Input:** Full assembled trip data: ordered stops with confirmed accommodations, activities and restaurants per stop, OSRM-verified driving times between stops, total days and date range.

**Output:** A structured `DayPlan` list — one entry per day — with date, driving leg (if applicable), km and hours from OSRM, scheduled activities, restaurant suggestion for the evening, and a narrative description. Also produces a final cost estimate broken down by category.

**Why Opus:** Day planning requires reasoning across the entire trip simultaneously — balancing drive days with rest days, sequencing activities logically, producing a coherent narrative — so it uses the most capable model.

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

If the segment is too short for any classic in-between stop, **DetourOptionsAgent** kicks in automatically and proposes 3 scenic side-trips with a blue info banner explaining what happened.

Pick an option, and it immediately suggests the next three. Keep picking until the full route is built, then confirm.

Each round displays:
- A **Leaflet map** with a green Start pin, a red Ziel pin, and blue numbered pins for each option; dashed coloured lines connect start → option → target for each branch
- A **"Neu berechnen"** bar to re-run the agent with a free-text instruction (e.g. "lieber Küste" or "Weingegend bevorzugt")
- Option cards stacked vertically, each with OSRM-verified drive time and distance, Google Maps link, and contextual metadata (altitude, language, must-sees, family score)
- An **orange warning badge** on cards whose OSRM drive time exceeds your limit
- A **"Route anpassen…"** banner if *all* cards exceed the limit — opens a modal to add days or insert a via-point
- A **blue "Umweg-Optionen" banner** if all cards are detour suggestions from DetourOptionsAgent

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
| DetourOptionsAgent | claude-haiku-4-5 | claude-haiku-4-5 |
| AccommodationResearcherAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlannerAgent | claude-opus-4-5 | claude-haiku-4-5 |

> DetourOptionsAgent always uses Haiku — it is a lightweight fallback on short segments and does not need higher reasoning capacity.

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
│   │   ├── _client.py               # shared Anthropic client + model selector
│   │   ├── route_architect.py       # RouteArchitectAgent (opus)
│   │   ├── stop_options_finder.py   # StopOptionsFinderAgent (sonnet, streaming)
│   │   ├── detour_options_agent.py  # DetourOptionsAgent (haiku, fallback)
│   │   ├── accommodation_researcher.py
│   │   ├── activities_agent.py      # + WikipediaEnricher
│   │   ├── restaurants_agent.py
│   │   ├── day_planner.py           # DayPlannerAgent (opus)
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
│       ├── route-builder.js         # route builder + detour banner + route-adjust modal
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

### v4.0.8 (2026-03-08)

**DetourOptionsAgent — Fallback for short segments**

When StopOptionsFinder returns 0 valid options after retry (typically on route segments shorter than ~100 km where proximity filters eliminate all candidates), a new `DetourOptionsAgent` activates automatically:
- Proposes 3 deliberate side-trip destinations off the direct route: `umweg_1` (left/west), `umweg_2` (right/east), `umweg_3` (surprise direction)
- No proximity filter applied — detour stops may be geographically close to the departure point
- Each option is still OSRM-enriched for real drive times
- Frontend shows the same option cards as normal, plus a blue **"Umweg-Optionen"** info banner explaining the situation to the user
- Selecting a detour option continues the route-building flow normally

---

### v4.0.7 (2026-03-07)

**Rundreise round-trip detection improvements**
- Minimum 200 km threshold prevents round-trip modal from appearing on short legs

---

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
- **Accommodation type fix** — `preferred_type` derived from `accommodation_styles[0]`; used in the prompt template instead of hardcoded "hotel"

**Sticky quick-submit bar**
- Persistent footer bar "✈ Reise jetzt planen" visible on all form steps once required fields are filled

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
