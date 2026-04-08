# infra/CLAUDE.md

This worker owns `infra/`, `docker-compose.yml`, `scripts/`, `.env.example`,
and `backend/requirements.txt`.
Do NOT modify `backend/`, `frontend/`, or application code.

## Docker Compose Services

4 services defined in `docker-compose.yml`:

| Service | Image | Exposed | Role |
|---------|-------|---------|------|
| `redis` | redis:7-alpine | 6379 (host) | Job state store + Celery broker |
| `backend` | Dockerfile.backend | 8000 (internal) | FastAPI app |
| `celery` | Dockerfile.backend (shared) | — | Celery worker |
| `frontend` | Dockerfile.frontend | 80 | Nginx static + reverse proxy |

Health checks:
- `redis`: `redis-cli ping`
- `backend`: `GET http://localhost:8000/health`

Celery worker limits: `--max-tasks-per-child=50 --max-memory-per-child=512000`

## Nginx Configuration (`infra/nginx.conf`)

- Reverse proxy: `/api/` → `backend:8000`
- SSE support: `proxy_buffering off`, `proxy_read_timeout 600s`, chunked transfer
- Static files: served from `/usr/share/nginx/html`
- Security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `server_tokens off`

## Dockerfiles

- `Dockerfile.backend`: `python:3.11-slim`, non-root user (uid 568), installs `requirements.txt`
- `Dockerfile.frontend`: `nginx-unprivileged:alpine`, copies `frontend/` to `/usr/share/nginx/html`

## Environment Variables (full reference)

```bash
# Required — AI
ANTHROPIC_API_KEY=sk-ant-...          # Claude API key

# Required — Maps
GOOGLE_MAPS_API_KEY=...               # Geocoding, Directions, Places APIs

# Required — Auth
JWT_SECRET=...                        # JWT signing key (generate: openssl rand -hex 32)
ADMIN_USERNAME=admin                  # bootstrapped admin user
ADMIN_PASSWORD=...                    # bootstrapped admin password

# Runtime
TEST_MODE=true                        # true=haiku (cheap), false=opus/sonnet (production)
REDIS_URL=redis://localhost:6379      # job state store + Celery broker
LOGS_DIR=/app/logs                    # log file dir (default: backend/logs/)

# Production
COOKIE_SECURE=true                    # set true when serving over HTTPS
```

Copy `.env.example` to `backend/.env` — never commit `.env`.

## Scripts

- `scripts/generate-types.sh` — generates `frontend/js/types.d.ts` from OpenAPI schema
- `scripts/dev-token.py` — generates a dev JWT token for local API testing (reads `backend/.env`)

## Deployment

Deployed via Docker Compose on TrueNAS. Steps:

```bash
docker compose up --build          # rebuild + start
docker compose up -d               # background
docker compose down                # stop
docker compose logs -f backend     # follow backend logs
docker compose logs -f celery      # follow Celery worker logs
```
