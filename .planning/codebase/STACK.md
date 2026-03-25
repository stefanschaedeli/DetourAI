# Technology Stack

**Analysis Date:** 2026-03-25

## Languages

**Primary:**
- Python 3.11 - Backend (FastAPI, agents, orchestrator, Celery workers)

**Secondary:**
- JavaScript ES2020 - Frontend (vanilla, no build step, no framework)
- HTML/CSS - Frontend UI (`frontend/index.html`, `frontend/styles.css`)

## Runtime

**Environment:**
- Python 3.11 (pinned in `infra/Dockerfile.backend` via `python:3.11-slim`)
- Node.js is NOT used - frontend is plain JS served as static files

**Package Manager:**
- pip (Python) - `backend/requirements.txt`
- Lockfile: Not present (no `requirements.lock` or `Pipfile.lock`)
- No npm/yarn - frontend has zero build dependencies

## Frameworks

**Core:**
- FastAPI >=0.111.0 - HTTP API framework (`backend/main.py`)
- Pydantic >=2.7.0 - Data validation for all API boundaries (`backend/models/`)
- Celery >=5.4.0 - Async task queue for long-running planning jobs (`backend/tasks/`)
- sse-starlette >=1.8.2 - Server-Sent Events for real-time progress streaming

**Testing:**
- pytest >=8.0.0 - Test runner (`backend/tests/`)
- pytest-mock >=3.12.0 - Mocking support
- pytest-asyncio >=0.23.0 - Async test support
- httpx >=0.27.0 - FastAPI TestClient HTTP transport

**Build/Dev:**
- uvicorn[standard] >=0.29.0 - ASGI server
- Docker + Docker Compose 3.9 - Containerization (`docker-compose.yml`)
- Nginx (alpine) - Static file serving + reverse proxy (`infra/nginx.conf`)

## Key Dependencies

**Critical:**
- anthropic >=0.28.0 - Claude AI SDK for all 9 planning agents (`backend/agents/_client.py`)
- aiohttp >=3.9.5 - Async HTTP client for all external API calls (`backend/utils/http_session.py`)
- redis >=5.0.4 - Job state storage, Celery broker (`backend/main.py`)

**Infrastructure:**
- PyJWT >=2.8.0 - JWT token creation/validation (`backend/utils/auth.py`)
- passlib[argon2] >=1.7.4 - Argon2id password hashing (`backend/utils/auth.py`)
- python-dotenv >=1.0.1 - Environment variable loading from `.env`
- fpdf2 >=2.7.9 - PDF generation for trip output (`backend/agents/output_generator.py`)
- python-pptx >=0.6.23 - PowerPoint generation for trip output (`backend/agents/output_generator.py`)

## Data & Storage

**Databases:**
- SQLite - Application data (travels, users, settings)
  - `data/travels.db` - Travel plans and user accounts (`backend/utils/travel_db.py`, `backend/utils/auth_db.py`)
  - `data/settings.db` - Application settings key-value store (`backend/utils/settings_store.py`)
  - Docker volume: `travel_data` mounted at `/app/data`

**Caching:**
- Redis 7 (Alpine) - Job state store + Celery message broker
  - Key pattern: `job:{job_id}`, TTL 24h (configurable via `system.redis_job_ttl_s`)
  - Config: `maxmemory 256mb`, `allkeys-lru` eviction policy
  - Fallback: In-memory `_InMemoryStore` class for local dev without Redis (`backend/main.py` lines 47-63)

**In-Memory Caches:**
- Geocode cache: OrderedDict, max 2000 entries, FIFO eviction (`backend/utils/maps_helper.py`)
- Currency rate cache: 24h TTL per currency (`backend/utils/currency.py`)
- Settings cache: 60s TTL (`backend/utils/settings_store.py`)

**File Storage:**
- Local filesystem for generated outputs (PDF/PPTX)
  - Path: `outputs/` (Docker: `/app/outputs`)

## Configuration

**Environment:**
- `.env` file loaded via python-dotenv at startup (`backend/main.py`)
- `.env.example` provides template - never commit `.env`
- Key vars: `ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`, `JWT_SECRET`, `REDIS_URL`, `TEST_MODE`
- See INTEGRATIONS.md for full env var reference

**Build:**
- `docker-compose.yml` - 4 services: redis, backend, celery, frontend
- `infra/Dockerfile.backend` - Python 3.11-slim, non-root user (uid 568)
- `infra/Dockerfile.frontend` - nginx-unprivileged:alpine, static file copy
- `infra/nginx.conf` - Reverse proxy `/api/` to `backend:8000`, SSE support (600s timeout)

**Application Settings:**
- SQLite-based settings store with defaults, validation ranges, and model allowlists
- Configurable per-agent: model selection, max_tokens
- Configurable: budget percentages, API timeouts, retry counts
- All defaults defined in `backend/utils/settings_store.py` `DEFAULTS` dict

## Infrastructure

**Containerization:**
- Docker Compose 3.9 with 4 services
- Services: `redis`, `backend`, `celery` (shared image), `frontend`
- Health checks on redis (ping), backend (HTTP /health)
- Celery worker limits: `--max-tasks-per-child=50 --max-memory-per-child=512000`

**Networking:**
- Frontend exposed on port 80 (mapped to nginx 8080)
- Backend internal on port 8000 (not directly exposed)
- Redis internal on port 6379 (also mapped to host for local dev)
- Nginx proxies `/api/` to backend with SSE buffering disabled

**Security Headers (Nginx):**
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `server_tokens off`

## HTTP Client

**Shared Session:**
- Single `aiohttp.ClientSession` with connection pooling (`backend/utils/http_session.py`)
- Connector: 100 total connections, 10 per host
- Lazy-initialized, shared across FastAPI and Celery workers
- All external API calls route through `get_session()`

## Platform Requirements

**Development:**
- Python 3.11+
- Redis (optional - falls back to in-memory store)
- Google Maps API key (Geocoding, Directions, Places APIs enabled)
- Anthropic API key
- Run: `cd backend && python3 -m uvicorn main:app --reload --port 8000`

**Production:**
- Docker + Docker Compose
- All env vars set (see `.env.example`)
- `COOKIE_SECURE=true` for HTTPS
- `TEST_MODE=false` for production Claude models

---

*Stack analysis: 2026-03-25*
