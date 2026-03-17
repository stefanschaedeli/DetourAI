# Auth & Access Control — Design Spec

**Date:** 2026-03-17
**Status:** Approved
**Stack:** FastAPI · SQLite · Vanilla JS · Docker Compose

---

## Goal

Add login-based access control to Travelman3. All endpoints require authentication. Users see only their own saved trips. An admin user (bootstrapped from environment variables) can manage users via a dedicated GUI panel in the SPA.

---

## Data Model

### New tables (added to existing `travels.db`)

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,          -- Argon2id via passlib
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL           -- ISO timestamp UTC
    -- Extensible: add email, display_name, locale, etc. here later
);

CREATE TABLE refresh_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,      -- SHA-256 of raw token
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### Migration to existing `travels` table

```sql
ALTER TABLE travels ADD COLUMN user_id INTEGER REFERENCES users(id);
-- All existing rows (user_id IS NULL) assigned to admin user at startup
```

Migration is idempotent: wrapped in try/except, safe to run on every startup.

---

## Authentication Flow

### Token strategy

- **Access token:** JWT (HS256, 15-minute TTL), returned in response body, stored in a JS module variable (not localStorage, not sessionStorage — intentionally lost on page refresh)
- **Refresh token:** opaque UUID (7-day TTL), stored as HTTP-only + SameSite=Strict cookie, hash stored in DB

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Validate credentials, issue access + refresh tokens |
| POST | `/api/auth/refresh` | Validate refresh cookie, issue new access token + rotate refresh token |
| POST | `/api/auth/logout` | Delete refresh token from DB, clear cookie |
| GET | `/api/auth/me` | Return current user info (`id`, `username`, `is_admin`) |

### Login flow

```
POST /api/auth/login { username, password }
→ Argon2id verify(password, hash)
→ issue access_token (JWT, 15min, in response body)
→ issue refresh_token (UUID, 7 days, HTTP-only cookie)
→ store SHA-256(refresh_token) in refresh_tokens table
```

### Refresh flow

```
POST /api/auth/refresh  (cookie sent automatically)
→ validate token_hash in DB + check expires_at
→ delete old refresh_tokens row
→ issue new access_token (15min)
→ issue new refresh_token (7 days, rotated)
```

### Page load flow

```
page loads
  → auth.silentRefresh()
      success → store access token, fetch /api/auth/me, populate S.currentUser, show app
      fail    → show #login-section, hide all other sections
```

### 401 handling in api.js

```
request returns 401
  → attempt one silent refresh (serialized — see auth.js notes below)
      success → retry original request
      fail    → show login screen, clear state
```

---

## Backend Architecture

### New files

| File | Purpose |
|------|---------|
| `backend/utils/auth_db.py` | users + refresh_tokens CRUD (get_user_by_username, create_user, store_refresh_token, validate_refresh_token, delete_refresh_token, list_users, delete_user) |
| `backend/utils/auth.py` | JWT create/validate, Argon2id hash/verify, get_current_user dependency, require_admin dependency |
| `backend/routers/auth.py` | `/api/auth/*` endpoints |
| `backend/routers/admin.py` | `/api/admin/users` endpoints (list, create, delete, `PATCH /{id}/password`) — admin only |

### Changes to existing files

**`backend/main.py`:**
- Include `auth_router` and `admin_router`
- Add `Depends(get_current_user)` to all existing endpoints
- Run startup migration (add user_id column, create admin user, assign orphan trips)
- Update CORS `allow_headers` to include `"Authorization"` (required for JWT Bearer tokens in Docker setup where frontend and backend may be on different origins)
- SSE endpoint `/api/progress/{job_id}`: validate that `current_user.id` matches the `user_id` stored in the Redis job state (set at job creation time); return 403 if mismatch

**`backend/utils/travel_db.py`:**
- All functions gain `user_id: int` parameter
- `list_travels(user_id)` — filters by user_id
- `save_travel(plan, user_id)` — stores with user_id
- `get_travel(travel_id, user_id)` — validates ownership; returns None if not owned
- `delete_travel(travel_id, user_id)` — validates ownership
- `update_travel(travel_id, user_id, ...)` — validates ownership before updating custom_name/rating
- `update_plan_json(travel_id, user_id, ...)` — validates ownership before replacing plan JSON

**`backend/tasks/run_planning_job.py` (Celery):**
- The `user_id` that initiated the job is stored in Redis job state at `/api/init-job` time
- Celery task reads `user_id` from Redis job state and passes it to `save_travel(plan, user_id=...)`
- **Also update the asyncio fallback path** (`_run_job` function) which also calls `save_travel(result)` — this must be updated identically, otherwise the fallback path writes trips without `user_id`

**`backend/requirements.txt`:**
- Add `PyJWT` (actively maintained; replaces `python-jose` which has known CVEs and is unmaintained)
- Add `passlib[argon2]`

**`docker-compose.yml`:**
- Add env vars to **both** `backend` and `celery` services: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `JWT_SECRET`, `COOKIE_SECURE`

### FastAPI dependencies

```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # Validates JWT signature + expiry
    # Returns User(id, username, is_admin)
    # Raises HTTP 401 if invalid or expired

async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403)
    return user
```

### Admin bootstrap (runs on startup)

1. Check if `ADMIN_USERNAME` + `ADMIN_PASSWORD` env vars are set
2. If no admin user exists → create one (Argon2id hash password)
3. `ALTER TABLE travels ADD COLUMN user_id INTEGER` (idempotent, wrapped in try/except)
4. `UPDATE travels SET user_id = <admin_id> WHERE user_id IS NULL`

**Note:** Admin self-deletion is blocked by the `/api/admin/users/{id}` endpoint — it returns HTTP 400 if `user_id == current_user.id`. This prevents accidental lockout.

**Password minimum length:** 8 characters minimum enforced at both the admin panel form (frontend) and the `POST /api/admin/users` endpoint (backend). Applies to all user creation.

**Password change:** `PATCH /api/admin/users/{id}/password` endpoint allows the admin to reset any user's password. This is the only supported path for password rotation (including the admin's own password). The admin bootstrap only runs "if no admin user exists" — changing `ADMIN_PASSWORD` in the environment after first boot has no effect on the existing admin account. This is intentional and documented: to rotate the admin password, use the admin panel.

**`routers/` package:** The `backend/routers/` directory does not yet exist. It must be created with an `__init__.py` file. Routers are registered in `main.py` with `app.include_router(auth_router, prefix="/api")` and `app.include_router(admin_router, prefix="/api")`.

**`JWT_SECRET` startup check:** On startup, if `JWT_SECRET` is set but shorter than 32 characters, log a `WARNING` and refuse to start (raise `RuntimeError`). This prevents silent weak-secret deployments.

---

## Frontend Architecture

### New file: `frontend/js/auth.js`

Responsibilities:
- In-memory access token store (module variable)
- `login(username, password)` → calls apiLogin, stores token, fetches /me
- `logout()` → calls apiLogout, clears token + S.currentUser, shows login screen
- `silentRefresh()` → calls /api/auth/refresh, stores new token
- `getToken()` → returns current access token for injection into requests
- **Refresh serialization:** if a refresh is already in-flight, all callers queue onto the same Promise rather than issuing parallel refresh requests. This prevents concurrent 401s from causing multiple refresh attempts and false logouts due to token rotation invalidating the first refresh.

### Changes to existing files

**`frontend/js/api.js`:**
- Import `getToken` from auth.js
- All fetch wrappers inject `Authorization: Bearer <token>`
- On 401 → `silentRefresh()` (serialized) → retry once → on failure → show login screen
- New functions: `apiLogin()`, `apiLogout()`, `apiRefresh()`, `apiGetMe()`

**`frontend/js/state.js`:**
- Add `currentUser: null` to `S` object (`{ id, username, is_admin }`)

**`frontend/js/travels.js`:**
- No functional changes needed — trip filtering is server-side
- Verify rendered fields don't expose `user_id` unexpectedly (it won't appear in list response)

**`frontend/index.html`:**
- New `#login-section` — shown when unauthenticated; username + password fields, Anmelden button, error display
- New `#admin-section` — hidden section like `#settings-section`; user management table + create form; only shown for `S.currentUser.is_admin`
- Header additions: username display, Abmelden button (logout), Admin button (admin only)

### Admin panel (`#admin-section`) UI

- **User list table:** Benutzername | Erstellt am | Admin (badge) | Aktionen (Löschen button)
- **Create user form:** Benutzername field + Passwort field (min 8 chars) + Erstellen button
- All text in German per project convention

### Trips user-scoping

- `GET /api/travels` now returns only the current user's trips (enforced server-side)
- No frontend changes needed for "Meine Reisen" — the filter happens in the backend

---

## Security Measures

| Measure | Implementation |
|---------|---------------|
| Password hashing | Argon2id via `passlib[argon2]` (memory-hard) |
| Refresh token storage | SHA-256 hash in DB; raw token only in HTTP-only cookie |
| JWT signing | HS256 + `JWT_SECRET` env var (min 32 chars) |
| Refresh token rotation | Old token deleted on each use; new one issued |
| Cookie flags | `HttpOnly=True`, `SameSite=strict`, `Secure` controlled by `COOKIE_SECURE` env var (default `false` for HTTP self-hosted) |
| Role enforcement | `require_admin` dependency raises 403 for non-admins |
| SSE stream protection | `/api/progress/{job_id}` compares `current_user.id` against `user_id` in Redis job state |
| Admin bootstrap | Idempotent; only runs if no admin exists |
| Admin self-deletion guard | `/api/admin/users/{id}` returns 400 if deleting own account |
| Password minimum length | 8 chars enforced at backend and frontend |

---

## Tests (`backend/tests/test_auth.py`)

- Login with valid credentials → 200, access token returned, cookie set
- Login with wrong password → 401
- Access protected endpoint without token → 401
- Access protected endpoint with valid token → 200
- Access admin endpoint as regular user → 403
- Access admin endpoint as admin → 200
- Token refresh with valid cookie → new access token issued, old token rotated
- Token refresh with expired/missing cookie → 401
- Logout → cookie cleared, DB row deleted
- Admin creates user → new user can login
- `GET /api/auth/me` with valid token → returns correct `id`, `username`, `is_admin` fields
- User sees only own trips in `GET /api/travels`
- User cannot access another user's trip by ID → 403
- Admin cannot delete own account → 400

---

## Environment Variables

```bash
ADMIN_USERNAME=admin          # Required for admin bootstrap
ADMIN_PASSWORD=<strong-pass>  # Required for admin bootstrap
JWT_SECRET=<min-32-chars>     # Required for JWT signing
COOKIE_SECURE=false           # Set to true when serving over HTTPS
```

---

## New Files Summary

```
backend/
  utils/
    auth_db.py       # users + refresh_tokens DB layer
    auth.py          # JWT, Argon2id, FastAPI dependencies
  routers/
    auth.py          # /api/auth/* endpoints
    admin.py         # /api/admin/users endpoints
  tests/
    test_auth.py     # 14 auth test cases
frontend/
  js/
    auth.js          # token store + login/logout/silentRefresh (with refresh serialization)
```

## Modified Files Summary

```
backend/
  main.py                    # auth deps on all endpoints, startup migration, routers, CORS update
  utils/travel_db.py         # user_id filtering on all CRUD including update_travel + update_plan_json
  tasks/run_planning_job.py  # read user_id from Redis state, pass to save_travel
  requirements.txt           # PyJWT, passlib[argon2]
frontend/
  index.html         # #login-section, #admin-section, header auth UI
  js/api.js          # token injection, 401 handling, auth API calls
  js/state.js        # S.currentUser field
  js/travels.js      # verify no user_id exposure (no functional change expected)
docker-compose.yml   # ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET, COOKIE_SECURE (backend + celery)
```
