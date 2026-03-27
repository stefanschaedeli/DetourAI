# External Integrations

**Analysis Date:** 2026-03-25

## APIs & External Services

### Anthropic Claude API (AI Planning Engine)

- **Purpose:** Core AI engine powering 9 specialized travel planning agents
- **SDK:** `anthropic` Python SDK >=0.28.0 (`backend/agents/_client.py`)
- **Auth:** API key via `ANTHROPIC_API_KEY` env var
- **Client factory:** `backend/agents/_client.py` `get_client()` - creates `anthropic.Anthropic(api_key=...)`
- **Models used:**
  - Production: `claude-opus-4-5` (route planning, day planning), `claude-sonnet-4-5` (research agents)
  - Test mode (`TEST_MODE=true`): All agents use `claude-haiku-4-5`
  - Model selection configurable per-agent via settings store
- **Rate limit handling:** `backend/utils/retry_helper.py` `call_with_retry()`
  - Exponential backoff on `RateLimitError` (429) and `InternalServerError` (529)
  - Default max attempts: 5 (configurable via `api.retry_max_attempts` setting)
  - Delay formula: `2^(attempt-1) + random()` seconds
  - All calls wrapped in `asyncio.to_thread()` (SDK is synchronous)
- **Token tracking:** Token usage logged per call (input/output/total), accumulated in `token_accumulator` list
- **Agents (9 total):**
  - `backend/agents/route_architect.py` - Route planning (Opus)
  - `backend/agents/stop_options_finder.py` - Stop suggestions (Sonnet)
  - `backend/agents/region_planner.py` - Regional route planning (Opus)
  - `backend/agents/accommodation_researcher.py` - Hotel research (Sonnet)
  - `backend/agents/activities_agent.py` - Activities + Wikipedia enrichment (Sonnet)
  - `backend/agents/restaurants_agent.py` - Restaurant recommendations (Sonnet)
  - `backend/agents/day_planner.py` - Day-by-day itinerary (Opus)
  - `backend/agents/travel_guide_agent.py` - Narrative travel guide (Sonnet)
  - `backend/agents/trip_analysis_agent.py` - Replan analysis (Sonnet)

### Google Maps Platform

- **Auth:** API key via `GOOGLE_MAPS_API_KEY` env var
- **Required API activations:** Geocoding API, Directions API, Places API
- **Rate limits:** Google allows 50 QPS for Geocoding (no sleep needed)
- **Client:** `aiohttp` via shared session (`backend/utils/http_session.py`), timeout 8-10s

**Geocoding API** (`backend/utils/maps_helper.py`):
- `geocode_google(place, country_code)` - Forward geocode: place name to (lat, lon, place_id)
  - Endpoint: `https://maps.googleapis.com/maps/api/geocode/json`
  - In-memory cache: 2000 entries, FIFO eviction
  - Language: `de` (German)
- `reverse_geocode_google(lat, lon)` - Coordinates to place name
  - Same endpoint with `latlng` parameter

**Directions API** (`backend/utils/maps_helper.py`):
- `google_directions(origin, destination, waypoints)` - Driving directions
  - Endpoint: `https://maps.googleapis.com/maps/api/directions/json`
  - Returns: (hours, km, encoded_polyline)
  - Mode: `driving`, language: `de`
  - Timeout: 10s
- `google_directions_simple(origin, destination)` - Returns only (hours, km)
- `reference_cities_along_route_google(origin, destination, num_points)` - Finds cities along route using Directions + Reverse Geocoding
- `build_maps_url(locations, place_ids)` - Generates Google Maps direction URLs for user links

**Places API** (`backend/utils/google_places.py`):
- `nearby_search(lat, lon, place_type, radius_m, keyword)` - Nearby Search
  - Endpoint: `https://maps.googleapis.com/maps/api/place/nearbysearch/json`
  - Convenience wrappers: `search_restaurants()`, `search_hotels()`, `search_attractions()`
- `place_details(place_id)` - Place Details
  - Endpoint: `https://maps.googleapis.com/maps/api/place/details/json`
  - Fields: name, address, phone, website, rating, reviews, opening_hours, photos
- `find_place_from_text(input_text)` - Find Place From Text ($17/1000 - cheaper than Text Search)
  - Endpoint: `https://maps.googleapis.com/maps/api/place/findplacefromtext/json`
- `text_search(query, location_bias)` - Text Search ($32/1000)
  - Endpoint: `https://maps.googleapis.com/maps/api/place/textsearch/json`
- `place_photo_url(photo_reference, max_width)` - Constructs photo URL (no API call)
  - URL: `https://maps.googleapis.com/maps/api/place/photo`

### Brave Search API (Optional)

- **Purpose:** Local business search for restaurants, hotels, attractions
- **Auth:** API key via `BRAVE_API_KEY` env var (optional - gracefully degrades to empty results)
- **Client:** `aiohttp` via shared session, timeout 8s
- **File:** `backend/utils/brave_search.py`
- **Endpoints:**
  - `search_local(query, count)` - Local Search: `https://api.search.brave.com/res/v1/local/search`
    - Returns: name, address, rating, rating_count, phone, price_range
  - `search_web(query, count)` - Web Search fallback: `https://api.search.brave.com/res/v1/web/search`
    - Returns: name, url, description
  - `search_places(query, count)` - Tries local first, falls back to web search
- **Header:** `X-Subscription-Token: {api_key}`

### Wikipedia / Wikidata (Free, No Auth)

- **Purpose:** City summaries, thumbnails, and factual data (population, elevation, area)
- **Auth:** None required
- **User-Agent:** `DetourAI/1.0`
- **File:** `backend/utils/wikipedia.py`
- **Endpoints:**
  - `get_city_summary(city, language)` - Wikipedia REST API
    - URL: `https://{language}.wikipedia.org/api/rest_v1/page/summary/{city}`
    - Returns: title, extract, thumbnail_url, lat, lon
    - Default language: `de`
  - `get_city_facts(city, country)` - Wikidata API
    - URL: `https://www.wikidata.org/w/api.php`
    - Actions: `wbsearchentities` then `wbgetentities`
    - Properties: P1082 (population), P2044 (elevation), P2046 (area)
- **Timeout:** 6-8s

### Open-Meteo (Free Weather API, No Auth)

- **Purpose:** Weather forecasts and historical climate averages
- **Auth:** None required
- **File:** `backend/utils/weather.py`
- **Endpoints:**
  - `get_forecast(lat, lon, start_date, end_date)` - Daily forecast (max 16 days)
    - URL: `https://api.open-meteo.com/v1/forecast`
    - Returns: date, temp_max, temp_min, precipitation_mm, weather_code, description (German)
    - WMO weather codes mapped to German descriptions
  - `get_climate_average(lat, lon, month)` - Historical 30-year averages (ERA5)
    - URL: `https://archive-api.open-meteo.com/v1/archive`
    - Date range: 1991-2020 for the specified month
    - Returns: avg_temp, avg_rain_days, sunshine_hours
    - Used when trip date is beyond 16-day forecast window
- **Timeout:** 8-10s

### ECB Exchange Rates (Free, No Auth)

- **Purpose:** Currency conversion to CHF (all prices displayed in CHF)
- **Auth:** None required
- **File:** `backend/utils/currency.py`
- **Endpoint:** `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`
- **Caching:** 24h TTL per currency in `_rate_cache` dict
- **Fallback:** Hardcoded approximate rates for 14 currencies if ECB unavailable
- **Functions:**
  - `get_chf_rate(currency)` - 1 {currency} = X CHF
  - `convert_to_chf(amount, from_currency)` - Convert any amount to CHF
  - `detect_currency(country)` - Country name to currency code mapping

### HotelAPI.co / Makcorps (Deactivated)

- **Purpose:** Real hotel price fetching
- **Status:** DEACTIVATED - Mapping API not available in free plan
- **File:** `backend/utils/hotel_price_fetcher.py`
- **Current behavior:** `fetch_real_price()` always returns `(None, None)`
- **Fallback:** Claude-estimated prices + Booking.com links with hotel names
- **Reactivation:** Requires Makcorps plan with Mapping API access

### Google Places Photos (Image Fetching)

- **Purpose:** Destination images for trip stops
- **File:** `backend/utils/image_fetcher.py`
- **Implementation:** Uses `place_details()` + `place_photo_url()` from Google Places
- **Note:** Previous Unsplash integration removed - `fetch_unsplash_images()` is a stub returning None

## Data Storage

**Databases:**
- SQLite (`data/travels.db`) - Travels, users, refresh tokens
  - Client: raw `sqlite3` module, `Row` factory
  - Tables: `travels`, `users`, `refresh_tokens`
  - Migrations: `backend/utils/migrations.py`
- SQLite (`data/settings.db`) - Application settings
  - Key-value store with JSON-serialized values

**File Storage:**
- Local filesystem (`outputs/`) - Generated PDF and PPTX files

**Caching:**
- Redis 7 Alpine - Job state and Celery broker
  - Connection: `REDIS_URL` env var (default: `redis://localhost:6379`)
  - Client: `redis.from_url()` with `decode_responses=True`

## Authentication & Identity

**Auth Provider:** Custom JWT-based authentication
- **Implementation:** `backend/utils/auth.py`, `backend/utils/auth_db.py`
- **Password hashing:** Argon2id via passlib
- **JWT:** HS256 algorithm, 15-minute access token TTL
- **Refresh tokens:** SHA-256 hashed, stored in SQLite, 7-day TTL, single-use rotation
- **Admin bootstrap:** Auto-creates admin user at startup if none exists (from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars)
- **SSE auth:** Supports `?token=` query parameter for EventSource (which cannot set headers)
- **FastAPI dependencies:** `get_current_user()`, `get_current_user_sse()`, `require_admin()`

## Monitoring & Observability

**Error Tracking:** Custom file-based logging system
- **Implementation:** `backend/utils/debug_logger.py`
- **Log structure:**
  - `backend/logs/agents/<agent_name>.log` - Per-agent logs
  - `backend/logs/orchestrator/orchestrator.log` - Orchestration flow
  - `backend/logs/api/api.log` - General API logs
  - `backend/logs/frontend/frontend.log` - Browser errors reported via API
- **Rotation:** Daily, 30-day retention (configurable via `system.log_retention_days`)
- **Levels:** ERROR, WARNING, INFO, SUCCESS, AGENT, API, DEBUG, PROMPT

**Frontend Error Reporting:**
- `window.onerror` and `window.onunhandledrejection` auto-report to `/api/log` endpoint
- `apiLogError()` in `frontend/js/api.js` sends errors to backend

## CI/CD & Deployment

**Hosting:** Self-hosted via Docker Compose
- No CI pipeline detected (no `.github/workflows/`, no `Jenkinsfile`, no `.gitlab-ci.yml`)

**Deployment:**
- `docker compose up --build` - Full stack deployment
- Images: `detour-ai/backend:latest`, `detour-ai/frontend:latest`
- Volumes: `travel_data` (named), `./outputs` and `./logs` (bind mounts)

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` - Claude AI API access (required)
- `GOOGLE_MAPS_API_KEY` - Google Maps Geocoding, Directions, Places (required)
- `JWT_SECRET` - JWT signing key, minimum 32 characters (required)
- `ADMIN_PASSWORD` - Initial admin user password (required for first run)
- `REDIS_URL` - Redis connection string (default: `redis://localhost:6379`)

**Optional env vars:**
- `BRAVE_API_KEY` - Brave Search API (optional, gracefully degrades)
- `TEST_MODE` - `true` uses claude-haiku-4-5 for all agents (default: `true`)
- `ADMIN_USERNAME` - Admin username (default: `admin`)
- `COOKIE_SECURE` - Set `true` for HTTPS production (default: `true` in Docker, `false` in `.env.example`)
- `OUTPUTS_DIR` - Generated file output path (default: `./outputs`)
- `DATA_DIR` - SQLite database directory (default: `./data` or `/app/data` in Docker)
- `LOGS_DIR` - Log file directory (default: `backend/logs/` or `/app/logs` in Docker)

**Secrets location:**
- `backend/.env` file (gitignored, never committed)
- Docker Compose reads from host env or `.env` file in project root

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## HTTP Session Management

All external API integrations share a single `aiohttp.ClientSession` managed by `backend/utils/http_session.py`:
- Connection pool: 100 total, 10 per host
- Lazy initialization, process-lifetime duration
- Cleanup via `close_session()` on shutdown
- All timeouts set per-request (6-10s depending on service)

---

*Integration audit: 2026-03-25*
