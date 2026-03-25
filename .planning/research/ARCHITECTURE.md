# Architecture Research

**Domain:** AI road trip planner -- stabilization + UX redesign
**Researched:** 2026-03-25
**Confidence:** HIGH (based on direct codebase analysis + domain knowledge)

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         NGINX (reverse proxy)                        │
│         Static files (frontend/)  +  /api/ → backend:8000            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────┐    SSE     ┌──────────────────────────┐     │
│  │   Vanilla JS SPA    │◄══════════►│     FastAPI Backend      │     │
│  │                     │   REST     │     (main.py, 2600+ LoC) │     │
│  │  state.js (S obj)   │◄══════════►│                          │     │
│  │  route-builder.js   │            │  Route geometry calc     │     │
│  │  maps.js (GMaps)    │            │  Agent orchestration     │     │
│  │  guide.js           │            │  Job lifecycle mgmt      │     │
│  └─────────────────────┘            └────────┬──────┬──────────┘     │
│                                              │      │                │
│                                    ┌─────────┘      └──────────┐     │
│                                    ▼                           ▼     │
│                          ┌──────────────┐           ┌──────────────┐ │
│                          │    Redis     │           │   Celery     │ │
│                          │  job:{id}    │◄─────────►│   Workers    │ │
│                          │  sse:{id}    │  events   │              │ │
│                          │  TTL 24h     │           │  planning    │ │
│                          └──────────────┘           │  acc-fetch   │ │
│                                                     │  stop-replace│ │
│                                                     └──────┬───────┘ │
│                                                            │         │
│  ┌──────────────────────────────────────────────────┐      │         │
│  │              AI Agents (9 agents)                 │◄─────┘         │
│  │  RouteArchitect  StopOptionsFinder  RegionPlanner │                │
│  │  AccommodationR. Activities  Restaurants          │                │
│  │  DayPlanner  TravelGuide  TripAnalysis            │                │
│  └──────────────────────┬────────────────────────────┘                │
│                         │                                            │
│  ┌──────────────────────┴────────────────────────────┐               │
│  │           External APIs                            │               │
│  │  Anthropic Claude  |  Google Maps (Geo/Dir/Places) │               │
│  │  Brave Search      |  Wikipedia  |  Unsplash       │               │
│  └────────────────────────────────────────────────────┘               │
│                                                                      │
│  ┌────────────────────────────────────────────────────┐               │
│  │           SQLite Persistence                       │               │
│  │  data/travels.db (plans + users + settings)        │               │
│  └────────────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Key Constraint |
|-----------|----------------|----------------|
| **main.py** | HTTP endpoints, SSE streaming, route geometry, job lifecycle | Monolith at 2600+ LoC -- all new endpoints land here |
| **Orchestrator** | Sequences agents for full planning pipeline | Runs inside Celery task, pushes SSE events via Redis |
| **AI Agents** | Domain-specific Claude API calls (route, stops, accommodation, etc.) | All follow same pattern: prompt -> call_with_retry -> parse_agent_json |
| **Redis** | Ephemeral job state (24h TTL) + SSE event bus between Celery and FastAPI | Cross-process bridge -- Celery workers push, SSE endpoint drains |
| **SQLite** | Persistent travel plans, users, settings | Single file, no concurrent write issues at friends-and-family scale |
| **Frontend SPA** | Vanilla JS with client-side routing, Google Maps rendering | No framework, no build step -- all DOM manipulation is manual |

## How New Features Integrate

### 1. Geographic Awareness (Ferry/Island Routing)

**Current gap:** The StopOptionsFinder prompt constrains stops to a corridor bounding box between origin and destination. For island destinations (e.g., Greek islands), this corridor is over water. Google Directions returns driving-only results, missing ferries entirely.

**Architecture change: Prompt enrichment layer, not new agents.**

```
Current flow:
  _calc_route_geometry() → Google Directions (driving only)
      → corridor_box, reference_cities → StopOptionsFinder prompt

New flow:
  _calc_route_geometry() → Google Directions
      → _detect_water_crossing() [NEW]
          → if islands/coastal: inject ferry context into geometry dict
      → corridor_box adjusted for maritime routes
      → StopOptionsFinder prompt includes ferry/island awareness
```

**Component: `_detect_water_crossing()` in main.py**
- Checks if destination coordinates are on an island (reverse geocode → check for island-type results, or maintain a small lookup of known island groups)
- When detected: skip corridor bounding box constraint (meaningless over water), add explicit ferry port context to prompt, set `transport_mode: "ferry+driving"` in geometry dict
- Google Directions API supports `mode=transit` but not ferries specifically. Better approach: hardcode known ferry port pairs for common island groups (Greek islands, Corsica, Sardinia, Balearics) and inject them as waypoint hints

**Prompt changes in StopOptionsFinder:**
- Add transport_mode awareness: when geometry dict contains `ferry_ports`, the system prompt gets a new rule block about coastal/island routing
- Remove the strict bounding box rule for island segments (rule 7 in current prompt)
- Add: "Wenn Fährüberfahrten nötig sind, schlage Hafenstädte als Zwischenstopps vor"

**Prompt changes in RouteArchitect:**
- The `ferry_crossings: []` field already exists in the output schema but is never populated
- Add explicit instruction: "Identifiziere Fährüberfahrten wenn das Ziel eine Insel ist oder Küstenrouten Wasserüberquerungen erfordern"

**No new agents needed.** This is purely prompt engineering + geometry enrichment.

**Build order implication:** This must come before UI work because correct route data feeds everything downstream.

### 2. User Route Control (Edit/Reorder/Replace Stops)

**Current state:** Users can select stops during route building and replace stops post-planning. No reorder, no manual add, no mid-planning preference changes.

**Architecture change: New endpoints on main.py + frontend route-builder enhancements.**

```
New endpoints (all operate on Redis job state):

POST /api/reorder-stops/{job_id}
  Body: { "stop_ids": [3, 1, 2, 4] }
  → Reorder selected_stops in job state
  → Recalculate Google Directions for affected segments
  → Return updated route with new drive times/distances

POST /api/remove-stop/{job_id}/{stop_id}
  → Remove from selected_stops
  → Recalculate remaining route geometry
  → Return updated route

POST /api/add-custom-stop/{job_id}
  Body: { "region": "Nice", "country": "FR", "nights": 2 }
  → Geocode via Google
  → Insert into selected_stops at correct position
  → Recalculate route geometry
  → Return updated route

POST /api/regenerate-options/{job_id}
  Body: { "extra_instructions": "Mehr Strand, weniger Berge" }
  → Re-run StopOptionsFinder with updated preferences
  → Stream new options via SSE (same as current flow)
```

**SSE flow is NOT broken.** These are all synchronous request-response endpoints that modify job state. The SSE stream only runs during the initial option-finding phase. Route editing happens after options are displayed, so it uses normal REST calls. The only SSE-aware operation is `regenerate-options`, which reuses the existing `route_option_ready` event pattern.

**Frontend changes:**
- `route-builder.js`: Add drag-to-reorder for confirmed stops (HTML5 drag-and-drop already exists for regions)
- Add "Remove stop" button per stop card
- Add "Add custom stop" input field
- Add "More options like this" / preference adjustment UI

**Data flow for reorder:**
```
User drags stop → POST /api/reorder-stops/{job_id}
  → Backend reorders job.selected_stops
  → Recalculates Google Directions for changed pairs
  → Returns { stops: [...], route_updated: true }
  → Frontend re-renders route on map + stop list
```

**Build order implication:** Depends on geographic awareness being done first (correct coordinates and routes are prerequisite for meaningful reordering).

### 3. Map-Centric Responsive Layout

**Current state:** Google Maps is a secondary element in the UI. The route-builder has a small map alongside option cards. Guide view has a separate map. No responsive design.

**Architecture change: CSS/HTML restructure only. No backend changes.**

**Layout pattern: Split-pane with map as persistent hero.**

```
┌─────────────────────────────────────────────────────┐
│  Desktop (>768px)                                    │
│  ┌────────────────────────┬────────────────────────┐ │
│  │                        │                        │ │
│  │      Map (60%)         │   Content Panel (40%)  │ │
│  │                        │                        │ │
│  │   Google Maps fills    │   Stop cards           │ │
│  │   entire left side     │   Day timeline         │ │
│  │                        │   Guide content        │ │
│  │   Markers, polylines   │                        │ │
│  │   update as user       │   Scrollable           │ │
│  │   interacts with       │                        │ │
│  │   content panel        │                        │ │
│  │                        │                        │ │
│  └────────────────────────┴────────────────────────┘ │
│                                                      │
│  Mobile (<768px)                                     │
│  ┌──────────────────────────────────────────────────┐│
│  │   Map (top 40vh, collapsible)                    ││
│  ├──────────────────────────────────────────────────┤│
│  │   Content (bottom, scrollable)                   ││
│  │   Stop cards stack vertically                    ││
│  │   Pull-up sheet pattern for details              ││
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

**Implementation approach:**
- CSS Grid with `grid-template-columns: 1fr 1fr` (desktop) collapsing to single column (mobile)
- Map container uses `position: sticky` on desktop so it stays visible while content scrolls
- One persistent map instance (replace current two-map approach: `_routeMap` + `_guideMap` in maps.js) with a single `GoogleMaps.getMap()` that all views share
- Content panel transitions between views (route-builder, accommodation, guide) without destroying the map
- On mobile: map is a collapsible top section with a "Show map" / "Hide map" toggle

**Key frontend files affected:**
- `index.html`: Restructure section layout to two-panel grid
- `styles.css`: Major rewrite for responsive grid, remove Apple-inspired card layout, add travel-app visual style
- `maps.js`: Merge `_routeMap` and `_guideMap` into single persistent instance
- `route-builder.js`, `accommodation.js`, `guide.js`: All render into the content panel, all update the shared map
- `router.js`: Route transitions must preserve map state

**No backend changes.** The map layout is purely a frontend concern.

**Build order implication:** This is the largest frontend change. Do it as a dedicated phase after backend work is stable. Attempting responsive layout changes while also modifying route-builder logic causes merge conflicts and testing nightmares.

### 4. Public Shareable Links

**Current state:** All endpoints require JWT auth. No share functionality exists. Travel plans are stored in SQLite with user_id ownership.

**Architecture change: New share_token column + public endpoint bypass.**

```
Database schema addition (travels table):
  share_token  TEXT UNIQUE      -- random URL-safe token (e.g., secrets.token_urlsafe(16))
  is_shared    INTEGER DEFAULT 0  -- explicit share toggle

New endpoints:
  POST   /api/travels/{id}/share     [auth required]
    → Generate share_token if not exists, set is_shared=1
    → Return { share_url: "/shared/{share_token}" }

  DELETE /api/travels/{id}/share     [auth required]
    → Set is_shared=0 (keep token for re-enable)
    → Return { success: true }

  GET    /api/shared/{share_token}   [NO AUTH -- public]
    → Look up travel by share_token WHERE is_shared=1
    → Return full plan JSON (read-only, no user info)
    → 404 if token invalid or sharing disabled
```

**Auth bypass pattern:**
```python
# In main.py -- no Depends(get_current_user) on this endpoint
@app.get("/api/shared/{share_token}")
async def get_shared_travel(share_token: str):
    travel = travel_db.get_by_share_token(share_token)
    if not travel or not travel["is_shared"]:
        raise HTTPException(404, "Reise nicht gefunden")
    # Strip sensitive fields (user_id, token counts)
    plan = json.loads(travel["plan_json"])
    return {"travel": _sanitize_for_public(plan), "title": travel["title"]}
```

**Frontend for shared view:**
- New route: `/shared/{token}` in router.js
- Renders the guide view (guide.js) in read-only mode
- No sidebar, no edit controls, no auth check
- Map + day-by-day timeline + stop details
- "Geplant mit Travelman" attribution footer

**Nginx config:**
- `/shared/*` must serve `index.html` (SPA routing) -- same as existing `try_files` pattern

**Security considerations:**
- `share_token` is 22 chars of URL-safe base64 (128 bits of entropy) -- unguessable
- No personal data exposed (strip user_id, email from response)
- Rate limiting on `/api/shared/*` to prevent scraping (optional, low priority at friends-and-family scale)

**Build order implication:** Can be done independently of other features. Small scope, clean boundaries. Good candidate for an early quick-win phase.

## Data Flow Summary

### Current Planning Flow (unchanged)
```
Form → POST /api/plan-trip → Redis job
  → StopOptionsFinder (SSE streaming) → User selects stops
  → Confirm route → Celery: accommodation research (SSE)
  → User selects accommodations → Celery: full planning (SSE)
  → Result saved to SQLite → Guide view
```

### New: Route Editing Flow (added)
```
During route building (after stops displayed):
  User drags/removes/adds stop → REST call → Redis job state updated
  → Google Directions recalculated → Response with updated route
  → Frontend re-renders map + stop list

Post-planning:
  User wants to change stop → POST /api/travels/{id}/replace-stop (existing)
```

### New: Share Flow (added)
```
Owner: Guide view → "Teilen" button → POST /api/travels/{id}/share
  → share_token generated → URL copied to clipboard

Recipient: Opens /shared/{token} → GET /api/shared/{token}
  → Read-only guide view rendered (no auth needed)
```

## Suggested Build Order (Dependencies)

```
Phase 1: Geographic Awareness (ferry/island routing)
  ├── No dependencies on other features
  ├── Feeds correct data to all downstream features
  └── Changes: route_architect.py prompts, stop_options_finder.py prompts,
      main.py geometry functions

Phase 2: Route Editing Controls
  ├── Depends on: Phase 1 (correct geography)
  ├── New endpoints + route-builder.js enhancements
  └── Changes: main.py (4 new endpoints), route-builder.js, maps.js

Phase 3: Public Shareable Links
  ├── Independent -- can run parallel with Phase 2
  ├── Small scope, clean boundaries
  └── Changes: travel_db.py (schema), main.py (2 endpoints),
      router.js, new shared-view.js

Phase 4: Map-Centric Responsive Layout
  ├── Depends on: Phase 2 (route editing UI must be designed first)
  ├── Largest change -- full CSS/HTML restructure
  └── Changes: index.html, styles.css, maps.js, route-builder.js,
      accommodation.js, guide.js, router.js
```

**Rationale for ordering:**
- Phase 1 first because wrong geography makes everything else unreliable
- Phase 2 before Phase 4 because you need to know what controls exist before designing the layout
- Phase 3 is independent and small -- schedule wherever convenient
- Phase 4 last because it touches every frontend file and must not conflict with Phase 2 changes

## Anti-Patterns to Avoid

### Anti-Pattern 1: New Agents for Prompt Problems

**What people do:** Create a new "FerryRoutingAgent" or "IslandAwarenessAgent" for geographic improvements.
**Why it's wrong:** Adds another Claude API call ($$$), more orchestration complexity, more failure points. The problem is prompt quality, not missing agents.
**Do this instead:** Enrich the existing StopOptionsFinder and RouteArchitect prompts with geographic context from Google APIs and a small ferry-port lookup table.

### Anti-Pattern 2: WebSocket Migration for "Real-Time" Features

**What people do:** Replace SSE with WebSockets for route editing "real-time updates."
**Why it's wrong:** Route editing is request-response, not streaming. SSE is one-directional (server to client) which is exactly right for progress streaming. WebSockets add connection management complexity.
**Do this instead:** Use REST for route edits (synchronous). Keep SSE only for long-running operations (option finding, planning).

### Anti-Pattern 3: Separate Public Frontend

**What people do:** Build a separate HTML page or micro-frontend for the shared view.
**Why it's wrong:** Duplicates rendering logic (guide.js, maps.js). Two codebases to maintain.
**Do this instead:** Reuse the existing SPA. Add `/shared/{token}` route that renders guide.js in read-only mode. The `auth.js` module simply skips auth checks when on a `/shared/` route.

### Anti-Pattern 4: Responsive Retrofit

**What people do:** Add `@media` queries on top of existing desktop layout.
**Why it's wrong:** The current layout uses fixed widths, absolute positioning, and two separate map instances. Retrofitting responsive on top of this creates a fragile mess.
**Do this instead:** Redesign the layout from scratch with CSS Grid as the foundation. Mobile-first, then enhance for desktop. Merge the two map instances into one.

## Integration Points

### External Services

| Service | Integration Pattern | Notes for New Features |
|---------|---------------------|------------------------|
| Google Directions API | `google_directions()` in maps_helper.py | Does NOT return ferry routes. Must supplement with ferry-port lookup for island destinations |
| Google Geocoding API | `geocode_google()` in maps_helper.py | Works fine for islands -- returns correct lat/lon for island cities |
| Anthropic Claude API | `call_with_retry()` in retry_helper.py | No changes needed -- prompt modifications only |
| Google Maps JS SDK | `maps.js` singleton | Must merge two map instances into one for responsive layout |

### Internal Boundaries

| Boundary | Communication | Impact of Changes |
|----------|---------------|-------------------|
| Frontend <-> Backend | REST + SSE via `/api/` | New endpoints for route editing + sharing. SSE unchanged |
| Backend <-> Celery | Redis lists (`sse:{job_id}`) | No changes -- route editing is synchronous, not Celery tasks |
| Backend <-> SQLite | `travel_db.py` functions | Add share_token column + `get_by_share_token()` query |
| Agents <-> main.py | Direct function calls | Prompt changes only -- no interface changes |

## Sources

- Direct codebase analysis of `/Users/stefan/Code/Travelman3/` (all findings verified against actual code)
- Google Directions API documentation: supports `mode=driving` only for car routes; ferry detection requires supplementary data
- Existing drag-and-drop implementation in `route-builder.js` (regions) as pattern for stop reordering

---
*Architecture research for: Travelman3 stabilization + UX redesign*
*Researched: 2026-03-25*
