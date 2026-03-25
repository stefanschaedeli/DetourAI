# Stack Research

**Domain:** AI-powered road trip planner — stabilization and UX redesign
**Researched:** 2026-03-25
**Confidence:** MEDIUM-HIGH

> This research covers NEW additions only. The existing stack (FastAPI, vanilla JS, Redis, Celery, Docker, Anthropic SDK, Google Maps JS SDK, Leaflet 1.9.4) is not re-evaluated.

---

## 1. Geographic Routing with Ferry/Island Awareness

### Problem Statement

The app currently uses the legacy Google Directions API (`mode=driving`) which handles ferries implicitly — if a driving route includes a ferry crossing, the API includes it. But the app has no explicit ferry awareness: stops land on mainland instead of target islands, and the AI agents have no geographic context about which destinations require ferries.

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Google Routes API (Compute Routes) | v2 | Replace legacy Directions API | Legacy Directions API deprecated March 2025. Routes API has identical ferry behavior (ferries included by default in DRIVE mode unless `avoidFerries: true`) plus better pricing tiers and polyline encoding. Migration is straightforward — same auth, same concepts, REST POST instead of GET. | HIGH |
| Google Geocoding API | existing | Coordinate resolution | Already used. No change needed. The island-misplacement bug is an AI agent prompt problem, not a geocoding problem — geocoding "Santorini" correctly returns island coordinates. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `polyline` (Python) | 2.0.2 | Decode Google encoded polylines | Replace the hand-rolled `decode_polyline5()` in `maps_helper.py` with a battle-tested library. Handles edge cases. `pip install polyline` | HIGH |
| `shapely` | 2.0.7 | Geographic geometry operations | Use for corridor calculations, point-in-polygon checks (is this coordinate on an island?), and bounding-box operations. Replaces manual haversine math for complex spatial queries. | MEDIUM |

### Key Insight: The Ferry Problem is Mostly an AI Agent Problem

Google Directions/Routes API already handles ferry routing correctly for DRIVE mode — if you ask for directions from Athens to Santorini, it returns a route including a ferry. The real problems are:

1. **Stop Options Finder agent** suggests mainland stops when the destination is an island chain — this is a prompt engineering fix, not an API fix
2. **Route Architect agent** doesn't understand that some legs require ferries and plans driving times as if everything is connected by road — this needs geographic context in the prompt
3. **No ferry duration data** — Google includes ferry time in total duration but doesn't break it out, so the day planner can't distinguish "4h driving" from "1h driving + 3h ferry"

### Approach: Geographic Context Enrichment

Instead of adding new routing APIs, enrich agent prompts with geographic context:

| Approach | Implementation | Why |
|----------|---------------|-----|
| Island detection | Pre-check destination coordinates against known island regions (bounding boxes for Greek islands, Balearics, Canaries, etc.) | Tells agents "this is an island destination — ferries required" |
| Ferry leg flagging | When Google Routes returns a route with ferry steps, parse the `steps` array and flag legs containing `travel_mode: FERRY` | Gives day planner accurate ferry vs. driving breakdown |
| Region-aware prompting | Add geographic context to agent system prompts: "The destination region contains islands accessible only by ferry" | Prevents mainland stop suggestions |

### What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| OpenRouteService for ferry routing | Known issues with ferry routes — community reports routes avoiding available ferries. Based on OSM data which has incomplete ferry coverage for Mediterranean. | Google Routes API — commercial-grade ferry data |
| Ferryhopper API | No public developer API (contact-only access). Would add a dependency on a third-party booking platform for schedule data the app doesn't need. | Google Routes API includes ferry segments in driving routes |
| OSRM (Open Source Routing Machine) | Self-hosted, no ferry support in driving profile, would require maintaining a separate routing server | Google Routes API |
| Separate transit-mode queries for ferries | Google Routes API TRANSIT mode doesn't support intermediate waypoints and returns public transit schedules, not driving+ferry combinations | Use DRIVE mode which already includes ferries |

---

## 2. Responsive Map-Centric Travel UI

### Problem Statement

The app needs a map-centric redesign where the route map is the hero element. Currently uses Google Maps JS SDK for route/guide maps and Leaflet 1.9.4 for zone drawing. The frontend is vanilla JS with no build step — must stay that way.

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Google Maps JS SDK | existing (v3) | Primary map rendering | Already deeply integrated (maps.js, guide.js, route-builder.js). Switching would be a massive rewrite for no gain. The SDK handles route rendering, place markers, info windows, and Places API integration. Keep it. | HIGH |
| Leaflet | 1.9.4 (CDN) | Zone/corridor drawing only | Already loaded. Keep for the specific draw/corridor functionality where it's used. Don't expand its role — Google Maps is the primary map. | HIGH |
| CSS Container Queries | native | Responsive component layouts | Use `@container` queries instead of only media queries. Allows map panels and card grids to respond to their container size, not just viewport. Supported in all modern browsers since 2023. No library needed. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `@googlemaps/polyline-codec` | 1.0.28 (CDN) | Frontend polyline decoding | Decode route polylines on the frontend for animated route drawing and interactive route segments. Available via CDN: `unpkg.com/@googlemaps/polyline-codec` | MEDIUM |

### UI Architecture Patterns

| Pattern | Implementation | Why |
|---------|---------------|-----|
| Split-pane layout | CSS Grid with `grid-template-columns: 1fr 400px` (desktop) collapsing to stacked (mobile) | Map fills available space, sidebar has fixed width. On mobile, map becomes a sticky header and content scrolls below. |
| Sticky map | `position: sticky; top: 0; height: 100vh` on desktop | Map stays visible while scrolling through stops/days. Standard pattern in Airbnb, Google Travel, Booking.com. |
| Card-based stops | Semantic HTML + CSS Grid for stop cards | Photo-heavy cards with accommodation/activity previews. Grid auto-fills based on container width. |
| Bottom sheet (mobile) | CSS `transform: translateY()` + touch events | On mobile, content slides up over the map as a draggable bottom sheet. No library needed — ~100 lines of vanilla JS. |
| Scroll-driven map sync | `IntersectionObserver` on day/stop sections | As user scrolls through the travel guide, map pans to show the relevant stop. Zero-dependency browser API. |

### Responsive Breakpoints

| Breakpoint | Layout | Map Behavior |
|------------|--------|-------------|
| >= 1024px | Side-by-side (map + content panel) | Full-height sticky map, ~60% width |
| 768-1023px | Side-by-side with narrower panel | Map ~50% width |
| < 768px | Stacked (map header + scrollable content) | Map sticky at top (~40vh), content below with bottom-sheet option |

### What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| MapLibre GL JS | Would require replacing the entire Google Maps integration (~600+ lines across maps.js, guide.js, route-builder.js). MapLibre uses vector tiles which need a tile server. Adds complexity for a friends-and-family app. | Keep Google Maps JS SDK |
| Mapbox GL JS | Proprietary license since v2. Requires Mapbox account and access token. Feature overlap with Google Maps which is already integrated. | Keep Google Maps JS SDK |
| Any CSS framework (Tailwind, Bootstrap) | Project constraint: vanilla JS, no build step. Tailwind requires a build step. Bootstrap adds 30KB+ of CSS the app doesn't need. | Hand-written CSS with CSS Grid + Container Queries |
| Swiper/Splide for carousels | CSS `scroll-snap` handles horizontal scrolling natively. Adding a carousel library for photo galleries is unnecessary weight. | CSS `scroll-snap-type: x mandatory` |
| Hammer.js for touch gestures | Only needed for bottom-sheet drag on mobile. Native `touchstart`/`touchmove`/`touchend` events are sufficient for a single drag gesture. | Native touch events |

---

## 3. Shareable Public Link System

### Problem Statement

Users want to share trip plans with friends/family via a simple link. Recipients should see a read-only view without needing an account. This replaces the deprecated PDF/PPTX export.

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| `secrets` (Python stdlib) | built-in | Generate share tokens | `secrets.token_urlsafe(16)` produces 22-character URL-safe tokens with 128 bits of entropy. No external dependency. Cryptographically secure. | HIGH |
| SQLite | existing | Store share links | Add a `shares` table to the existing `travels.db`. Columns: `token`, `travel_id`, `created_at`, `expires_at`, `created_by`. No new database needed. | HIGH |
| FastAPI | existing | Public endpoint | Add `GET /api/shared/{token}` — no JWT required. Returns full travel plan JSON. Frontend renders the same guide view in read-only mode. | HIGH |

### Architecture

```
User clicks "Teilen" (Share)
  → POST /api/travels/{id}/share
  → Backend generates token via secrets.token_urlsafe(16)
  → Stores in shares table: (token, travel_id, user_id, created_at, expires_at)
  → Returns: { "url": "https://app.example/shared/{token}" }

Recipient opens link
  → Frontend detects /shared/{token} route
  → GET /api/shared/{token} (no auth required)
  → Backend looks up token → returns travel plan JSON
  → Frontend renders read-only guide view (reuse existing guide.js rendering)
```

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| None needed | — | — | The share system is simple enough that Python stdlib + existing stack covers everything. No external dependencies required. | HIGH |

### Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Token format | `secrets.token_urlsafe(16)` = 22 chars | Short enough for URLs, 128-bit entropy prevents guessing. UUIDs work too but are 36 chars — uglier in URLs. |
| Token lifetime | 90 days default, configurable | Long enough for trip sharing, short enough to not accumulate forever. User can revoke manually. |
| Auth bypass | Dedicated `/api/shared/{token}` endpoint | Clean separation from authenticated endpoints. No JWT middleware on this route. Token IS the auth. |
| Read-only enforcement | Backend returns data only, no write endpoints accept share tokens | Share tokens can never modify data. Architecturally impossible, not just permission-checked. |
| Rate limiting | IP-based rate limit on `/api/shared/` | Prevent token enumeration attacks. 60 requests/minute per IP is reasonable. |
| Revocation | `DELETE /api/travels/{id}/share` | User can revoke share link. Deletes token from DB. Immediate effect. |
| Multiple shares | One active share per travel | Simplicity. Revoking creates a new token if user shares again. |

### What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| nanoid (Python) | External dependency for something `secrets.token_urlsafe()` does natively. nanoid adds a pip dependency for zero benefit. | `secrets.token_urlsafe(16)` |
| JWT-based share tokens | JWTs are self-contained — you can't revoke them without a blocklist. Database tokens can be instantly revoked by deletion. Share tokens don't need to carry claims. | Opaque database-backed tokens |
| Short URL service (bit.ly, etc.) | Adds external dependency and potential privacy concern (third party sees all shared trips). URLs are already short enough with 22-char tokens. | Direct app URLs |
| Separate "public" database/schema | Overengineered. A single `shares` table in the existing `travels.db` is sufficient. | Single `shares` table |

---

## Installation

### Backend (new dependencies)

```bash
# Only if adopting polyline + shapely for geographic operations
pip install polyline==2.0.2 shapely==2.0.7
```

### Frontend (no new dependencies)

No new frontend dependencies. All recommendations use:
- Existing Google Maps JS SDK (already loaded)
- Existing Leaflet 1.9.4 (already loaded via CDN)
- Native browser APIs (CSS Grid, Container Queries, IntersectionObserver, touch events)

---

## Google Routes API Migration Path

The legacy Directions API is deprecated since March 2025. Migration to Routes API is recommended but not urgent — legacy API continues to work.

### Changes Required in `maps_helper.py`

| Current (Legacy) | New (Routes API) | Change |
|-------------------|------------------|--------|
| `GET /maps/api/directions/json` | `POST https://routes.googleapis.com/directions/v2:computeRoutes` | HTTP method + URL |
| `mode=driving` | `"travelMode": "DRIVE"` | Parameter name + format |
| `waypoints=A\|B` | `"intermediates": [{"address": "A"}, {"address": "B"}]` | Waypoint format |
| Response: `routes[0].legs[].duration.value` | Response: `routes[0].legs[].duration` (string like "3600s") | Duration format |
| API key as query param | API key as `X-Goog-Api-Key` header + `X-Goog-FieldMask` header | Auth mechanism |

### Ferry Step Detection (New Capability)

The Routes API response includes step-level travel modes. Parse for ferry segments:

```python
for step in leg.get("steps", []):
    if step.get("travelMode") == "FERRY":
        ferry_duration_s += int(step["staticDuration"].rstrip("s"))
```

This enables the day planner to distinguish driving time from ferry time — currently impossible with the legacy API's aggregated duration.

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| polyline 2.0.2 | Python 3.8+ | Pure Python, no C extensions |
| shapely 2.0.7 | Python 3.8+, requires GEOS lib | Docker: `apt-get install libgeos-dev` in Dockerfile |
| Google Routes API v2 | Existing `GOOGLE_MAPS_API_KEY` | Must enable "Routes API" in Google Cloud Console (separate from legacy Directions API) |

---

## Sources

- [Google Routes API — Route Modifiers](https://developers.google.com/maps/documentation/routes/route-modifiers) — verified avoidFerries parameter, ferry behavior in DRIVE mode (HIGH confidence)
- [Google Routes API — computeRoutes](https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes) — verified travel modes, request format (HIGH confidence)
- [Google Routes API Migration Announcement](https://mapsplatform.google.com/resources/blog/announcing-routes-api-new-enhanced-version-directions-and-distance-matrix-apis/) — confirmed legacy Directions API deprecation March 2025 (HIGH confidence)
- [Google Directions API Legacy Overview](https://developers.google.com/maps/documentation/directions/overview) — confirmed continued access for existing users (HIGH confidence)
- [Leaflet 1.9.4 CDN](https://leafletjs.com/download.html) — confirmed latest stable version, v2.0 not yet released (HIGH confidence)
- [MapLibre GL JS v5.15.0](https://github.com/maplibre/maplibre-gl-js) — evaluated and rejected for this project (MEDIUM confidence)
- [OpenRouteService ferry routing issues](https://ask.openrouteservice.org/t/route-wont-take-ferry/461) — confirmed unreliable ferry support (MEDIUM confidence)
- [Python nanoid on PyPI](https://pypi.org/project/nanoid/) — evaluated and rejected in favor of stdlib secrets (HIGH confidence)
- [Python secrets module](https://docs.python.org/3/library/secrets.html) — stdlib, cryptographically secure token generation (HIGH confidence)

---
*Stack research for: Travelman3 stabilization and UX redesign*
*Researched: 2026-03-25*
