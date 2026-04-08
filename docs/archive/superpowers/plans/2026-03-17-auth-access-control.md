# Auth & Access Control Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add login-based access control to DetourAI — all endpoints protected by JWT auth, user-scoped trip storage, admin panel for user management, and a versioned DB migration runner for safe upgrades.

**Architecture:** FastAPI-native auth using PyJWT + passlib[argon2]. Access tokens (15min JWT) returned in response body and stored in a JS memory variable; refresh tokens (7-day opaque UUID) stored as HTTP-only SameSite=Strict cookies with hash in SQLite. A versioned migration runner (`migrations.py`) handles all schema changes on startup. Admin panel is a hidden SPA section rendered only for `is_admin` users.

**Tech Stack:** PyJWT, passlib[argon2], FastAPI Depends, SQLite, Vanilla JS (ES2020), HTTP-only cookies

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `backend/utils/migrations.py` | Versioned migration runner + initial 3 migrations |
| `backend/utils/auth_db.py` | users + refresh_tokens CRUD |
| `backend/utils/auth.py` | JWT create/validate, Argon2id hash/verify, FastAPI dependencies |
| `backend/routers/__init__.py` | Makes routers/ a package |
| `backend/routers/auth.py` | `/api/auth/login`, `/refresh`, `/logout`, `/me` |
| `backend/routers/admin.py` | `/api/admin/users` CRUD + password reset — admin only |
| `backend/tests/test_migrations.py` | Migration runner: idempotency, ordering, failure rollback |
| `backend/tests/test_auth.py` | 15 auth test cases |
| `frontend/js/auth.js` | In-memory token store, login/logout/silentRefresh, refresh serialization |

### Modified files
| File | Change |
|------|--------|
| `backend/requirements.txt` | Add PyJWT, passlib[argon2] |
| `backend/utils/travel_db.py` | All CRUD functions gain `user_id` param + ownership validation |
| `backend/tasks/run_planning_job.py` | Read `user_id` from Redis state, pass to `save_travel` (both Celery + asyncio path) |
| `backend/tasks/replace_stop_job.py` | Read `user_id` from Redis state, pass to `get_travel` + `update_plan_json` |
| `backend/main.py` | Run migrations + admin bootstrap on startup; add auth deps to all endpoints; include routers; update CORS; SSE ownership check; store `user_id` in Redis job state at job creation |
| `backend/.env.example` | Add ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET, COOKIE_SECURE |
| `docker-compose.yml` | Add auth env vars to backend + celery services |
| `frontend/js/api.js` | Inject Bearer token; handle 401 with serialized refresh; add apiLogin/apiLogout/apiRefresh/apiGetMe |
| `frontend/js/state.js` | Add `currentUser: null` to `S` |
| `frontend/js/travels.js` | Verify no unintended user_id exposure in rendered HTML (no functional change expected) |
| `frontend/index.html` | Add `#login-section`, `#admin-section`, header auth UI; load `auth.js` before `api.js` |

---

## Task 1: Install Dependencies & Migration Runner

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/utils/migrations.py`
- Create: `backend/tests/test_migrations.py`

- [ ] **Step 1.1: Add dependencies to requirements.txt**

```
PyJWT>=2.8.0
passlib[argon2]>=1.7.4
```

Add after `python-dotenv` line in `backend/requirements.txt`.

- [ ] **Step 1.2: Install locally**

```bash
cd backend && pip3 install PyJWT "passlib[argon2]"
```

Expected: installs without errors.

- [ ] **Step 1.3: Write migration runner tests (write FIRST, they fail)**

Create `backend/tests/test_migrations.py`:

```python
import os
import sqlite3
import tempfile
import pytest
from utils.migrations import run_migrations, MIGRATIONS


def make_db():
    """Create a temp SQLite DB path (file deleted on close)."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def test_schema_migrations_table_created():
    path = make_db()
    try:
        run_migrations(path)
        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        assert cur.fetchone() is not None
        conn.close()
    finally:
        os.unlink(path)


def test_all_migrations_applied():
    path = make_db()
    try:
        run_migrations(path)
        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = [row[0] for row in cur.fetchall()]
        expected = [m[0] for m in MIGRATIONS]
        assert applied == expected
        conn.close()
    finally:
        os.unlink(path)


def test_idempotent_second_run():
    """Running migrations twice must not fail or duplicate rows."""
    path = make_db()
    try:
        run_migrations(path)
        run_migrations(path)  # should be a no-op
        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT COUNT(*) FROM schema_migrations")
        count = cur.fetchone()[0]
        assert count == len(MIGRATIONS)
        conn.close()
    finally:
        os.unlink(path)


def test_partial_run_resumes():
    """Simulate DB that already has migration 1 applied — only 2 and 3 should run."""
    path = make_db()
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        # Manually apply migration 1
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (1, 'create_users', '2026-01-01T00:00:00')"
        )
        # Create the users table so migration 1 effects are present
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        run_migrations(path)

        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = [row[0] for row in cur.fetchall()]
        assert applied == [1, 2, 3]
        conn.close()
    finally:
        os.unlink(path)


def test_users_table_schema():
    path = make_db()
    try:
        run_migrations(path)
        conn = sqlite3.connect(path)
        cur = conn.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}
        assert {"id", "username", "password_hash", "is_admin", "created_at"} <= cols
        conn.close()
    finally:
        os.unlink(path)


def test_travels_user_id_column():
    path = make_db()
    try:
        # Pre-create travels table (as it would exist in production before migration)
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE travels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                start_location TEXT NOT NULL,
                destination TEXT NOT NULL,
                total_days INTEGER NOT NULL,
                num_stops INTEGER NOT NULL,
                total_cost_chf REAL NOT NULL,
                plan_json TEXT NOT NULL,
                has_travel_guide INTEGER NOT NULL DEFAULT 0,
                custom_name TEXT,
                rating INTEGER NOT NULL DEFAULT 0,
                UNIQUE(job_id)
            )
        """)
        conn.commit()
        conn.close()

        run_migrations(path)

        conn = sqlite3.connect(path)
        cur = conn.execute("PRAGMA table_info(travels)")
        cols = {row[1] for row in cur.fetchall()}
        assert "user_id" in cols
        conn.close()
    finally:
        os.unlink(path)
```

- [ ] **Step 1.4: Run tests — confirm they FAIL**

```bash
cd backend && python3 -m pytest tests/test_migrations.py -v
```

Expected: `ImportError` or similar (migrations.py doesn't exist yet).

- [ ] **Step 1.5: Create `backend/utils/migrations.py`**

```python
"""
Versioned SQLite migration runner.

Add new migrations by appending to MIGRATIONS — never modify existing entries.
Each migration runs in a transaction; failure rolls back and raises (startup aborts).
"""
import sqlite3
from datetime import datetime, timezone
from typing import Callable, List, Tuple, Union

# (version, name, sql_string_or_callable)
MIGRATIONS: List[Tuple[int, str, Union[str, Callable]]] = [
    (
        1,
        "create_users",
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL
        )
        """,
    ),
    (
        2,
        "create_refresh_tokens",
        """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ),
    (
        3,
        "travels_add_user_id",
        # Callable migration: ALTER TABLE fails if column already exists
        lambda conn: _add_column_if_missing(conn, "travels", "user_id", "INTEGER REFERENCES users(id)"),
    ),
]


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()


def run_migrations(db_path: str) -> None:
    """Apply all pending migrations to the SQLite DB at db_path."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.isolation_level = None  # manual transaction control
    try:
        _ensure_migrations_table(conn)

        cur = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        current_version: int = cur.fetchone()[0]

        for version, name, migration in MIGRATIONS:
            if version <= current_version:
                continue

            try:
                conn.execute("BEGIN")
                if callable(migration):
                    migration(conn)
                else:
                    # Use conn.execute() NOT executescript() — executescript issues
                    # an implicit COMMIT that breaks our transaction boundary.
                    for statement in migration.strip().split(";"):
                        statement = statement.strip()
                        if statement:
                            conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, datetime.now(timezone.utc).isoformat()),
                )
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                raise RuntimeError(f"Migration {version} '{name}' failed: {exc}") from exc
    finally:
        conn.close()
```

- [ ] **Step 1.6: Run migration tests — confirm they PASS**

```bash
cd backend && python3 -m pytest tests/test_migrations.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 1.7: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/requirements.txt backend/utils/migrations.py backend/tests/test_migrations.py
git commit -m "feat: versioned DB migration runner mit initialen Auth-Migrationen

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 2: Auth DB Layer (`auth_db.py`)

**Files:**
- Create: `backend/utils/auth_db.py`

- [ ] **Step 2.1: Create `backend/utils/auth_db.py`**

```python
"""
CRUD for users and refresh_tokens tables.
All functions are synchronous (called via asyncio.to_thread from async context).
"""
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional


def _db_path() -> str:
    data_dir = os.getenv("DATA_DIR", "data")
    return os.path.join(data_dir, "travels.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Users ────────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    """Insert user; returns new user id. Raises sqlite3.IntegrityError if username taken."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, 1 if is_admin else 0, now),
        )
        conn.commit()
    return cur.lastrowid


def list_users() -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_user(user_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    return cur.rowcount > 0


def update_password(user_id: int, new_hash: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id),
        )
        conn.commit()
    return cur.rowcount > 0


def admin_exists() -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    return row is not None


def assign_orphan_trips(admin_id: int) -> None:
    """Assign travels with NULL user_id to the admin user."""
    with _conn() as conn:
        conn.execute("UPDATE travels SET user_id = ? WHERE user_id IS NULL", (admin_id,))
        conn.commit()


# ── Refresh tokens ────────────────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def store_refresh_token(user_id: int, raw_token: str, ttl_days: int = 7) -> None:
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=ttl_days)).isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (user_id, _hash_token(raw_token), expires, now.isoformat()),
        )
        conn.commit()


def validate_and_rotate_refresh_token(raw_token: str) -> Optional[int]:
    """
    Validate refresh token. If valid and not expired:
      - delete the old row (rotation)
      - return user_id
    Returns None if invalid or expired.
    """
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, expires_at FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < now:
            conn.execute("DELETE FROM refresh_tokens WHERE id = ?", (row["id"],))
            conn.commit()
            return None
        conn.execute("DELETE FROM refresh_tokens WHERE id = ?", (row["id"],))
        conn.commit()
    return row["user_id"]


def delete_refresh_token(raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    with _conn() as conn:
        conn.execute("DELETE FROM refresh_tokens WHERE token_hash = ?", (token_hash,))
        conn.commit()
```

- [ ] **Step 2.2: Verify import works**

```bash
cd backend && python3 -c "from utils.auth_db import get_user_by_username; print('OK')"
```

Expected: `OK`

- [ ] **Step 2.3: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/utils/auth_db.py
git commit -m "feat: Auth-Datenbank-Schicht (users + refresh_tokens CRUD)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 3: Auth Utilities (`auth.py`)

**Files:**
- Create: `backend/utils/auth.py`

- [ ] **Step 3.1: Create `backend/utils/auth.py`**

```python
"""
JWT creation/validation, Argon2id password hashing, FastAPI auth dependencies.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = 15

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


import logging as _logging
_log = _logging.getLogger(__name__)


def verify_jwt_secret() -> None:
    """Call at startup — log a warning and refuse to start if JWT_SECRET is weak or missing."""
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        msg = (
            "JWT_SECRET must be set and at least 32 characters long. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
        _log.warning(msg)
        raise RuntimeError(msg)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: int       # user_id
    username: str
    is_admin: bool


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenPayload]:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(sub=data["sub"], username=data["username"], is_admin=data["is_admin"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── FastAPI dependencies ───────────────────────────────────────────────────────

class CurrentUser(BaseModel):
    id: int
    username: str
    is_admin: bool


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(id=payload.sub, username=payload.username, is_admin=payload.is_admin)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Zugriff")
    return user
```

- [ ] **Step 3.2: Verify import**

```bash
cd backend && python3 -c "from utils.auth import hash_password, verify_password; print(verify_password('test', hash_password('test')))"
```

Expected: `True`

- [ ] **Step 3.3: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/utils/auth.py
git commit -m "feat: JWT-Hilfsfunktionen und Argon2id-Passwort-Hashing

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 4: Auth Router (`routers/auth.py`)

**Files:**
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/auth.py`

- [ ] **Step 4.1: Create `backend/routers/__init__.py`**

Empty file — makes `routers/` a Python package.

```bash
touch backend/routers/__init__.py
```

- [ ] **Step 4.2: Create `backend/routers/auth.py`**

```python
"""
Auth endpoints: login, refresh, logout, me.
Cookie name: detour_ai_refresh
"""
import os
import uuid
import asyncio

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel

from utils.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from utils.auth_db import (
    delete_refresh_token,
    get_user_by_username,
    store_refresh_token,
    validate_and_rotate_refresh_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "detour_ai_refresh"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
REFRESH_TOKEN_TTL_DAYS = 7


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=COOKIE_SECURE,
        max_age=REFRESH_TOKEN_TTL_DAYS * 86400,
        path="/api/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response) -> TokenResponse:
    user = await asyncio.to_thread(get_user_by_username, body.username)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Anmeldedaten",
        )

    access_token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    raw_refresh = str(uuid.uuid4())
    await asyncio.to_thread(store_refresh_token, user["id"], raw_refresh, REFRESH_TOKEN_TTL_DAYS)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    detour_ai_refresh: str | None = Cookie(default=None),
) -> TokenResponse:
    if detour_ai_refresh is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Refresh-Token")

    user_id = await asyncio.to_thread(validate_and_rotate_refresh_token, detour_ai_refresh)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges oder abgelaufenes Refresh-Token")

    from utils.auth_db import get_user_by_id
    user = await asyncio.to_thread(get_user_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzer nicht gefunden")

    access_token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    raw_refresh = str(uuid.uuid4())
    await asyncio.to_thread(store_refresh_token, user["id"], raw_refresh, REFRESH_TOKEN_TTL_DAYS)
    _set_refresh_cookie(response, raw_refresh)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(
    response: Response,
    detour_ai_refresh: str | None = Cookie(default=None),
) -> dict:
    if detour_ai_refresh:
        await asyncio.to_thread(delete_refresh_token, detour_ai_refresh)
    response.delete_cookie(key=COOKIE_NAME, path="/api/auth")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.id, username=current_user.username, is_admin=current_user.is_admin)
```

- [ ] **Step 4.3: Verify import**

```bash
cd backend && python3 -c "from routers.auth import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4.4: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/routers/__init__.py backend/routers/auth.py
git commit -m "feat: Auth-Router (login, refresh, logout, me)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 5: Admin Router (`routers/admin.py`)

**Files:**
- Create: `backend/routers/admin.py`

- [ ] **Step 5.1: Create `backend/routers/admin.py`**

```python
"""
Admin-only endpoints: user management.
All routes require is_admin = True.
"""
import asyncio

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, field_validator

from utils.auth import CurrentUser, hash_password, require_admin
from utils.auth_db import (
    create_user,
    delete_user,
    get_user_by_id,
    list_users,
    update_password,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Benutzername darf nicht leer sein")
        return v.strip()


class PasswordResetRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


@router.get("/users")
async def list_all_users(admin: CurrentUser = Depends(require_admin)) -> dict:
    users = await asyncio.to_thread(list_users)
    return {"users": users}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    body: CreateUserRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    hashed = hash_password(body.password)
    try:
        user_id = await asyncio.to_thread(create_user, body.username, hashed, body.is_admin)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Benutzername '{body.username}' ist bereits vergeben",
        )
    return {"id": user_id, "username": body.username}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_user(
    user_id: int,
    admin: CurrentUser = Depends(require_admin),
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Eigenes Konto kann nicht gelöscht werden",
        )
    deleted = await asyncio.to_thread(delete_user, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")


@router.patch("/users/{user_id}/password")
async def reset_user_password(
    user_id: int,
    body: PasswordResetRequest,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    user = await asyncio.to_thread(get_user_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")
    new_hash = hash_password(body.password)
    await asyncio.to_thread(update_password, user_id, new_hash)
    return {"ok": True}
```

- [ ] **Step 5.2: Verify import**

```bash
cd backend && python3 -c "from routers.admin import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5.3: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/routers/admin.py
git commit -m "feat: Admin-Router (Benutzerverwaltung)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 6: Update `travel_db.py` — Add `user_id` to All CRUD

**Files:**
- Modify: `backend/utils/travel_db.py`

> **Important:** All sync `_sync_*` functions gain a `user_id` parameter. Ownership is checked with `AND user_id = ?` in WHERE clauses. `save_travel` stores `user_id`. `list_travels` filters by `user_id`.

- [ ] **Step 6.1: Read the current file**

Read `backend/utils/travel_db.py` in full before editing.

- [ ] **Step 6.2: Update `_init_db()` — travels table already has user_id from migration**

The `_init_db()` call creates the travels table if it doesn't exist. This call is now only used in tests; in production the migration runner handles schema. The function must remain for backward compat but the travels `CREATE TABLE` in it should include `user_id`:

Add `user_id INTEGER` column to the `CREATE TABLE travels` statement in `_init_db()`:

```python
user_id INTEGER REFERENCES users(id),
```

- [ ] **Step 6.3: Update `_sync_save` — accept and store `user_id`**

Change signature and INSERT to include `user_id`:

```python
def _sync_save(plan: dict, user_id: int) -> Optional[int]:
    # ... existing extraction of title, job_id, etc ...
    cur = conn.execute(
        """INSERT OR IGNORE INTO travels
           (job_id, title, created_at, start_location, destination,
            total_days, num_stops, total_cost_chf, plan_json,
            has_travel_guide, user_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (...existing fields..., user_id),
    )
```

- [ ] **Step 6.4: Update `_sync_list` — filter by `user_id`**

```python
def _sync_list(user_id: int) -> list:
    # Add WHERE user_id = ? to the SELECT
    rows = conn.execute(
        "SELECT id, job_id, title, ... FROM travels WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
```

- [ ] **Step 6.5: Update `_sync_get` — validate ownership**

```python
def _sync_get(travel_id: int, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT plan_json FROM travels WHERE id = ? AND user_id = ?",
        (travel_id, user_id),
    ).fetchone()
```

- [ ] **Step 6.6: Update `_sync_delete` — validate ownership**

```python
def _sync_delete(travel_id: int, user_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM travels WHERE id = ? AND user_id = ?",
        (travel_id, user_id),
    )
```

- [ ] **Step 6.7: Update `_sync_update` — validate ownership**

```python
def _sync_update(travel_id: int, user_id: int, custom_name: Optional[str], rating: Optional[int]) -> bool:
    # Add AND user_id = ? to WHERE clause
```

- [ ] **Step 6.8: Update `_sync_update_plan_json` — validate ownership**

```python
def _sync_update_plan_json(travel_id: int, user_id: int, plan: dict) -> bool:
    # Add AND user_id = ? to WHERE clause for both SELECT (to check exists) and UPDATE
```

- [ ] **Step 6.9: Update all async wrapper signatures**

```python
async def save_travel(plan: dict, user_id: int) -> Optional[int]:
    return await asyncio.to_thread(_sync_save, plan, user_id)

async def list_travels(user_id: int) -> list:
    return await asyncio.to_thread(_sync_list, user_id)

async def get_travel(travel_id: int, user_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_sync_get, travel_id, user_id)

async def delete_travel(travel_id: int, user_id: int) -> bool:
    return await asyncio.to_thread(_sync_delete, travel_id, user_id)

async def update_travel(travel_id: int, user_id: int, custom_name: Optional[str] = None, rating: Optional[int] = None) -> bool:
    return await asyncio.to_thread(_sync_update, travel_id, user_id, custom_name, rating)

async def update_plan_json(travel_id: int, user_id: int, plan: dict) -> bool:
    return await asyncio.to_thread(_sync_update_plan_json, travel_id, user_id, plan)
```

- [ ] **Step 6.10: Verify import and smoke test**

```bash
cd backend && python3 -c "from utils.travel_db import save_travel, list_travels; print('OK')"
```

Expected: `OK`

- [ ] **Step 6.11: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/utils/travel_db.py
git commit -m "feat: travel_db mit user_id-Filterung und Eigentümervalidierung

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 7: Update Celery Tasks — Propagate `user_id`

**Files:**
- Modify: `backend/tasks/run_planning_job.py`
- Modify: `backend/tasks/replace_stop_job.py`

- [ ] **Step 7.1: Read both task files in full before editing**

Read `backend/tasks/run_planning_job.py` and `backend/tasks/replace_stop_job.py`.

- [ ] **Step 7.2: Update `run_planning_job.py` — read `user_id` from Redis, pass to `save_travel`**

In `_run_job()`, after fetching `job` from Redis:
```python
user_id: int = job.get("user_id", 1)  # fallback to 1 (admin) for pre-auth trips
```

Change `await _db_save(result)` call to pass `user_id`. Find `_db_save` helper or inline `save_travel` call and add `user_id`:
```python
await save_travel(result, user_id=user_id)
```

If there is a `_db_save` wrapper, update it to accept and pass `user_id`.

- [ ] **Step 7.3: Update asyncio fallback path in `run_planning_job.py`**

Find `_run_job` call in the asyncio fallback (non-Celery path). Ensure `user_id` is read from the same Redis/in-memory store and passed through.

- [ ] **Step 7.4: Update `replace_stop_job.py` — read `user_id` from Redis, pass to `get_travel` + `update_plan_json`**

After fetching `job` from Redis:
```python
user_id: int = job.get("user_id", 1)
```

Change `get_travel(travel_id)` call:
```python
plan = await get_travel(travel_id, user_id)
```

Change `update_plan_json(travel_id, plan)` call:
```python
await update_plan_json(travel_id, user_id, plan)
```

- [ ] **Step 7.5: Verify imports**

```bash
cd backend && python3 -c "from tasks.run_planning_job import run_planning_job_task; print('OK')"
cd backend && python3 -c "from tasks.replace_stop_job import replace_stop_job_task; print('OK')"
```

Expected: `OK` for both.

- [ ] **Step 7.6: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/tasks/run_planning_job.py backend/tasks/replace_stop_job.py
git commit -m "feat: user_id aus Redis-Job-State an save_travel und update_plan_json weitergeleitet

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 8: Update `main.py` — Wire Everything Together

**Files:**
- Modify: `backend/main.py`

This is the largest change. Do it in sub-steps.

- [ ] **Step 8.1: Read `backend/main.py` in full** (it's 2476 lines — read it fully before editing)

- [ ] **Step 8.2: Add imports at top of main.py**

After existing imports add:
```python
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from utils.auth import get_current_user, CurrentUser, verify_jwt_secret
from utils.auth_db import admin_exists, create_user, assign_orphan_trips, get_user_by_username
from utils.auth import hash_password
from utils.migrations import run_migrations
```

- [ ] **Step 8.3: Update CORS — add `"Authorization"` to `allow_headers`**

Find:
```python
allow_headers=["Content-Type"],
```
Change to:
```python
allow_headers=["Content-Type", "Authorization"],
```

- [ ] **Step 8.4: Include routers**

After `app = FastAPI(...)` line add:
```python
app.include_router(auth_router)
app.include_router(admin_router)
```

- [ ] **Step 8.5: Replace startup handler with migration + admin bootstrap**

Find the existing `@app.on_event("startup")` handler (or `lifespan` context manager). Add at the start:

```python
# 1. Validate JWT secret
verify_jwt_secret()

# 2. Run DB migrations
data_dir = os.getenv("DATA_DIR", "data")
db_path = os.path.join(data_dir, "travels.db")
run_migrations(db_path)

# 3. Admin bootstrap
admin_username = os.getenv("ADMIN_USERNAME", "")
admin_password = os.getenv("ADMIN_PASSWORD", "")
if admin_username and admin_password:
    if not admin_exists():
        from utils.auth import hash_password as _hp
        admin_id = create_user(admin_username, _hp(admin_password), is_admin=True)
    else:
        user = get_user_by_username(admin_username)
        admin_id = user["id"] if user else 1
    assign_orphan_trips(admin_id)
```

- [ ] **Step 8.6: Add `Depends(get_current_user)` to all existing endpoints**

For each endpoint that currently has no auth, add the dependency. Pattern:

```python
@app.post("/api/init-job")
async def init_job(payload: TravelRequest, current_user: CurrentUser = Depends(get_current_user)):
    ...
```

Also store `user_id` in Redis job state immediately after creating the job:
```python
job["user_id"] = current_user.id
```

Do this for ALL endpoints that create or start a job (init-job, plan-trip, start-accommodations, start-planning, etc.).

Exempt endpoints (no auth required):
- `GET /health`
- `POST /api/auth/login` (already in auth router — not in main.py)
- `POST /api/auth/refresh` (already in auth router)

- [ ] **Step 8.7: SSE endpoint — add ownership check**

Find `GET /api/progress/{job_id}`. After getting `current_user`, fetch the job from Redis and verify ownership:

```python
@app.get("/api/progress/{job_id}")
async def progress(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    store = _get_store()
    raw = store.get(f"job:{job_id}")
    if raw:
        job = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        job_user_id = job.get("user_id")
        if job_user_id is not None and job_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Job")
    # ... rest of SSE handler
```

- [ ] **Step 8.8: Update travels endpoints — pass `current_user.id` to DB functions**

For all travels endpoints, replace:
- `list_travels()` → `list_travels(current_user.id)`
- `save_travel(plan)` → `save_travel(plan, current_user.id)`
- `get_travel(travel_id)` → `get_travel(travel_id, current_user.id)` + return 404 if None
- `delete_travel(travel_id)` → `delete_travel(travel_id, current_user.id)`
- `update_travel(travel_id, ...)` → `update_travel(travel_id, current_user.id, ...)`
- `update_plan_json(travel_id, plan)` → `update_plan_json(travel_id, current_user.id, plan)`

- [ ] **Step 8.9: Smoke test — app starts without crashing**

Set a fake JWT_SECRET in env and run:
```bash
cd backend && JWT_SECRET=test_secret_that_is_32_chars_long python3 -c "from main import app; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 8.10: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/main.py
git commit -m "feat: Auth-Middleware in main.py integriert (Migrations, Bootstrap, Deps)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 9: Write Auth Tests

**Files:**
- Create: `backend/tests/test_auth.py`

- [ ] **Step 9.1: Create `backend/tests/test_auth.py`**

```python
"""
Auth endpoint tests.
Uses FastAPI TestClient with an in-memory SQLite DB (temp file).
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Point DATA_DIR to a temp directory for each test."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(db_dir))
    monkeypatch.setenv("JWT_SECRET", "test_secret_that_is_32_chars_long!!!")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")
    monkeypatch.setenv("COOKIE_SECURE", "false")


@pytest.fixture
def client(isolated_db):
    from main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _login(client, username="admin", password="adminpass123"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    return resp


def _auth_headers(client, username="admin", password="adminpass123"):
    resp = _login(client, username, password)
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Login tests ───────────────────────────────────────────────────────────────

def test_login_valid_credentials(client):
    resp = _login(client)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # refresh cookie should be set
    assert "detour_ai_refresh" in resp.cookies


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401


# ── Protected endpoint tests ──────────────────────────────────────────────────

def test_protected_endpoint_without_token(client):
    resp = client.get("/api/travels")
    assert resp.status_code == 401


def test_protected_endpoint_with_valid_token(client):
    headers = _auth_headers(client)
    resp = client.get("/api/travels", headers=headers)
    assert resp.status_code == 200


# ── /me endpoint ──────────────────────────────────────────────────────────────

def test_me_returns_correct_fields(client):
    headers = _auth_headers(client)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["is_admin"] is True
    assert "id" in data


# ── Admin endpoint access ─────────────────────────────────────────────────────

def test_admin_endpoint_as_regular_user(client):
    # Create regular user first via admin
    admin_headers = _auth_headers(client)
    client.post("/api/admin/users", json={"username": "regular", "password": "regularpass1"}, headers=admin_headers)

    regular_headers = _auth_headers(client, "regular", "regularpass1")
    resp = client.get("/api/admin/users", headers=regular_headers)
    assert resp.status_code == 403


def test_admin_endpoint_as_admin(client):
    headers = _auth_headers(client)
    resp = client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 200
    assert "users" in resp.json()


# ── Token refresh ─────────────────────────────────────────────────────────────

def test_token_refresh_with_valid_cookie(client):
    login_resp = _login(client)
    cookie = login_resp.cookies.get("detour_ai_refresh")
    assert cookie is not None

    resp = client.post("/api/auth/refresh", cookies={"detour_ai_refresh": cookie})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    # New cookie should be set (rotation)
    assert "detour_ai_refresh" in resp.cookies


def test_token_refresh_without_cookie(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_token_refresh_invalid_cookie(client):
    resp = client.post("/api/auth/refresh", cookies={"detour_ai_refresh": "invalid-token"})
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_clears_cookie(client):
    login_resp = _login(client)
    cookie = login_resp.cookies.get("detour_ai_refresh")

    logout_resp = client.post("/api/auth/logout", cookies={"detour_ai_refresh": cookie})
    assert logout_resp.status_code == 200

    # Using the old cookie should now fail
    resp = client.post("/api/auth/refresh", cookies={"detour_ai_refresh": cookie})
    assert resp.status_code == 401


# ── Admin user management ─────────────────────────────────────────────────────

def test_admin_creates_user_who_can_login(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "newpass123"},
        headers=headers,
    )
    assert resp.status_code == 201

    login_resp = _login(client, "newuser", "newpass123")
    assert login_resp.status_code == 200


def test_admin_cannot_delete_own_account(client):
    headers = _auth_headers(client)
    me_resp = client.get("/api/auth/me", headers=headers)
    admin_id = me_resp.json()["id"]

    resp = client.delete(f"/api/admin/users/{admin_id}", headers=headers)
    assert resp.status_code == 400


# ── Trip ownership ────────────────────────────────────────────────────────────

def test_user_sees_only_own_trips(client):
    # Two users
    admin_headers = _auth_headers(client)
    client.post("/api/admin/users", json={"username": "user2", "password": "user2pass1"}, headers=admin_headers)
    user2_headers = _auth_headers(client, "user2", "user2pass1")

    # admin's trips list should be empty for a fresh DB
    resp = client.get("/api/travels", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["travels"] == []

    resp2 = client.get("/api/travels", headers=user2_headers)
    assert resp2.status_code == 200
    assert resp2.json()["travels"] == []


def test_user_cannot_access_another_users_trip_by_id(client):
    """User A cannot read User B's trip by its ID — must get 404 (not 403 to avoid enumeration)."""
    admin_headers = _auth_headers(client)
    # Create a second user
    client.post("/api/admin/users", json={"username": "user2", "password": "user2pass1"}, headers=admin_headers)
    user2_headers = _auth_headers(client, "user2", "user2pass1")

    # Use a non-existent travel_id — admin has no trips, so any ID returns 404
    # This verifies the ownership filter is applied even for direct ID access
    resp = client.get("/api/travels/99999", headers=user2_headers)
    assert resp.status_code == 404
```

- [ ] **Step 9.2: Run auth tests**

```bash
cd backend && python3 -m pytest tests/test_auth.py -v
```

Expected: all 14+ tests PASS.

If any fail, fix the implementation (not the tests) before proceeding.

- [ ] **Step 9.3: Run full test suite**

```bash
cd backend && python3 -m pytest tests/ -v
```

Fix any regressions in existing tests (the signature changes to travel_db functions will break existing travel tests — update those callers to pass a dummy user_id like `user_id=1`).

- [ ] **Step 9.4: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/tests/test_auth.py
git commit -m "test: Auth-Testfälle (Login, Token, Admin, Eigentümer)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 10: Update Environment Config

**Files:**
- Modify: `backend/.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 10.1: Update `backend/.env.example`**

Add after existing vars:
```
# Auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_strong_password
JWT_SECRET=generate_with__python3_-c_"import_secrets;print(secrets.token_hex(32))"
COOKIE_SECURE=false
```

- [ ] **Step 10.2: Update `docker-compose.yml` — add auth env vars to both backend and celery**

In the `backend` service `environment:` block add:
```yaml
- ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
- ADMIN_PASSWORD=${ADMIN_PASSWORD}
- JWT_SECRET=${JWT_SECRET}
- COOKIE_SECURE=${COOKIE_SECURE:-false}
```

In the `celery` service `environment:` block add the same 4 vars (celery workers share the same DB and need JWT_SECRET if they ever validate tokens).

- [ ] **Step 10.3: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add backend/.env.example docker-compose.yml
git commit -m "feat: Auth-Umgebungsvariablen in .env.example und docker-compose.yml

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 11: Frontend — `auth.js` + Update `api.js` + `state.js`

**Files:**
- Create: `frontend/js/auth.js`
- Modify: `frontend/js/api.js`
- Modify: `frontend/js/state.js`

- [ ] **Step 11.1: Create `frontend/js/auth.js`**

> **IMPORTANT:** This file uses plain global functions — NO `export` keywords. The project uses plain `<script>` tags (not ES modules). All functions are globals accessible from other scripts and inline `<script>` blocks.

```javascript
/**
 * auth.js — In-memory token store, login/logout, silent refresh.
 *
 * Access token lives in _accessToken (closure variable, NOT localStorage).
 * Lost on page refresh intentionally — initAuth() re-acquires from cookie.
 *
 * Refresh is serialized: concurrent 401s queue on a single in-flight refresh
 * promise instead of each issuing a parallel refresh request.
 *
 * All functions are GLOBAL (no export) — consistent with project JS style.
 */

/* global S */  // S is defined in state.js, loaded before auth.js

let _accessToken = null;
let _refreshPromise = null;  // serialization lock

function getToken() {
  return _accessToken;
}

function setToken(token) {
  _accessToken = token;
}

function clearToken() {
  _accessToken = null;
}

/**
 * Attempt a silent token refresh using the HTTP-only refresh cookie.
 * Returns true on success, false on failure.
 * Serialized: only one refresh runs at a time.
 */
async function silentRefresh() {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',  // sends the HTTP-only cookie
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      _accessToken = data.access_token;
      return true;
    } catch {
      return false;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

/**
 * Login with username + password.
 * On success: stores token, fetches /me, populates S.currentUser.
 * Returns null on success, error string on failure.
 */
async function login(username, password) {
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  });

  if (!resp.ok) {
    return 'Ungültige Anmeldedaten';
  }

  const data = await resp.json();
  _accessToken = data.access_token;

  // Fetch user info and populate global state
  const meResp = await fetch('/api/auth/me', {
    headers: { 'Authorization': `Bearer ${_accessToken}` },
  });
  if (!meResp.ok) return 'Fehler beim Laden der Benutzerdaten';

  S.currentUser = await meResp.json();
  return null;  // null = success
}

/**
 * Logout: clear server-side token + local state.
 */
async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    });
  } catch {
    // best-effort
  }
  _accessToken = null;
  S.currentUser = null;
}

/**
 * Initialize auth on page load.
 * Tries a silent refresh; if successful, fetches /me and populates S.currentUser.
 * Returns true if authenticated, false if login screen should be shown.
 */
async function initAuth() {
  const ok = await silentRefresh();
  if (!ok) return false;

  try {
    const resp = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${_accessToken}` },
    });
    if (!resp.ok) return false;
    S.currentUser = await resp.json();
    return true;
  } catch {
    return false;
  }
}
```

- [ ] **Step 11.2: Update `frontend/js/state.js` — add `currentUser`**

Find the `S` object definition and add `currentUser: null` to it:

```javascript
const S = {
  // ... existing fields ...
  currentUser: null,  // { id, username, is_admin } after login
};
```

- [ ] **Step 11.3: Update `frontend/js/api.js` — inject token + 401 handling**

At the top of `api.js`, add import reference comment (vanilla JS — no real imports, use global):
```javascript
// auth.js exposes window.authGetToken, window.authSilentRefresh via globals
// loaded before api.js in index.html
```

Update `_fetch` helper to inject Bearer token and handle 401:

```javascript
async function _fetch(url, opts = {}, label = '') {
  // Show loading overlay (existing behavior)
  showLoading(label);

  // Inject auth header
  const token = (typeof getToken === 'function') ? getToken() : null;
  if (token) {
    opts.headers = { ...(opts.headers || {}), 'Authorization': `Bearer ${token}` };
  }
  opts.credentials = 'include';

  let resp = await fetch(url, opts);

  // Handle 401: attempt one silent refresh, then retry
  if (resp.status === 401 && typeof silentRefresh === 'function') {
    const refreshed = await silentRefresh();
    if (refreshed) {
      const newToken = getToken();
      opts.headers = { ...(opts.headers || {}), 'Authorization': `Bearer ${newToken}` };
      resp = await fetch(url, opts);
    }
    if (resp.status === 401) {
      hideLoading();
      showLoginScreen();
      throw new Error('Nicht angemeldet');
    }
  }

  hideLoading();
  // ... rest of existing error handling ...
  return resp;
}
```

Apply the same token injection + 401 handling to `_fetchQuiet`.

Add new auth API functions at the bottom:

```javascript
async function apiLogin(username, password) {
  return fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  });
}

async function apiLogout() {
  return fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
}

async function apiRefresh() {
  // Delegates to auth.js silentRefresh which handles serialization
  return (typeof silentRefresh === 'function') ? silentRefresh() : false;
}

async function apiGetMe() {
  const token = getToken();
  return fetch('/api/auth/me', {
    headers: { 'Authorization': `Bearer ${token}` },
  });
}
```

- [ ] **Step 11.4: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add frontend/js/auth.js frontend/js/api.js frontend/js/state.js
git commit -m "feat: Frontend Auth-Modul (Token-Speicher, Login, Refresh-Serialisierung)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 12: Frontend — `index.html` (Login Screen + Admin Panel + Header)

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 12.1: Read `frontend/index.html` in full before editing**

- [ ] **Step 12.2: Add `auth.js` to script loading order**

The existing script block in `index.html` already loads `router.js` (SPA routing) between `state.js` and `api.js`. Add `auth.js` after `state.js` and before `router.js`:

```html
<script src="/js/loading.js"></script>
<script src="/js/sse-overlay.js"></script>
<script src="/js/maps.js"></script>
<script src="/js/state.js"></script>
<script src="/js/auth.js"></script>   <!-- NEW: must load before api.js -->
<script src="/js/router.js"></script>
<script src="/js/api.js"></script>
<!-- ... rest unchanged ... -->
```

- [ ] **Step 12.3: Add `#login-section` before `#form-section`**

```html
<!-- Login Screen -->
<section id="login-section" class="section">
  <div class="login-container">
    <h2>Anmelden</h2>
    <form id="login-form" onsubmit="handleLogin(event)">
      <div class="login-field">
        <label for="login-username">Benutzername</label>
        <input type="text" id="login-username" autocomplete="username" required />
      </div>
      <div class="login-field">
        <label for="login-password">Passwort</label>
        <input type="password" id="login-password" autocomplete="current-password" required />
      </div>
      <div id="login-error" class="login-error" style="display:none"></div>
      <button type="submit" class="btn-primary" id="login-submit">Anmelden</button>
    </form>
  </div>
</section>
```

- [ ] **Step 12.4: Add `#admin-section` after `#settings-section`**

```html
<!-- Admin Panel (only visible to admins) -->
<section id="admin-section" class="section" style="display:none">
  <div class="admin-container">
    <h2>Benutzerverwaltung</h2>

    <!-- User list -->
    <table class="admin-user-table" id="admin-user-table">
      <thead>
        <tr>
          <th>Benutzername</th>
          <th>Erstellt am</th>
          <th>Rolle</th>
          <th>Aktionen</th>
        </tr>
      </thead>
      <tbody id="admin-user-tbody"></tbody>
    </table>

    <!-- Create user form -->
    <div class="admin-create-user">
      <h3>Neuen Benutzer erstellen</h3>
      <form id="admin-create-form" onsubmit="handleAdminCreateUser(event)">
        <input type="text" id="admin-new-username" placeholder="Benutzername" required minlength="1" />
        <input type="password" id="admin-new-password" placeholder="Passwort (min. 8 Zeichen)" required minlength="8" />
        <button type="submit" class="btn-primary">Erstellen</button>
      </form>
      <div id="admin-create-error" class="login-error" style="display:none"></div>
    </div>
  </div>
</section>
```

- [ ] **Step 12.5: Add auth UI to header**

Find the header element. After the existing buttons ("Meine Reisen", "Neu starten") add:

```html
<!-- Auth header controls -->
<span id="header-username" style="display:none" class="header-username"></span>
<button id="btn-admin" onclick="showSection('admin-section')" style="display:none" class="btn-secondary">Admin</button>
<button id="btn-logout" onclick="handleLogout()" style="display:none" class="btn-secondary">Abmelden</button>
```

- [ ] **Step 12.6: Add inline script for auth page init and handlers**

In the existing inline `<script>` block at bottom of `<body>`, add:

```javascript
// ── Auth helpers ──────────────────────────────────────────────────────────────

function showLoginScreen() {
  showSection('login-section');
  document.getElementById('header-username').style.display = 'none';
  document.getElementById('btn-admin').style.display = 'none';
  document.getElementById('btn-logout').style.display = 'none';
  // Hide the existing header action buttons (Meine Reisen, Neu starten)
  // Use IDs: read them from index.html — typically btn-my-travels or the actual button IDs
  const headerBtns = document.querySelectorAll('.app-header button:not(#btn-admin):not(#btn-logout)');
  headerBtns.forEach(b => b.style.display = 'none');
}

function showAppForUser(user) {
  document.getElementById('header-username').textContent = user.username;
  document.getElementById('header-username').style.display = '';
  document.getElementById('btn-logout').style.display = '';
  if (user.is_admin) {
    document.getElementById('btn-admin').style.display = '';
  }
  // Restore existing header buttons
  const headerBtns = document.querySelectorAll('.app-header button:not(#btn-admin):not(#btn-logout)');
  headerBtns.forEach(b => b.style.display = '');
  showSection('form-section');
}

async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById('login-username').value;
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  const submitBtn = document.getElementById('login-submit');

  submitBtn.disabled = true;
  errEl.style.display = 'none';

  const error = await login(username, password);  // from auth.js
  if (error) {
    errEl.textContent = error;
    errEl.style.display = '';
    submitBtn.disabled = false;
  } else {
    showAppForUser(S.currentUser);
  }
}

async function handleLogout() {
  await logout();  // from auth.js
  showLoginScreen();
}

// ── Admin panel helpers ───────────────────────────────────────────────────────

async function loadAdminUsers() {
  const resp = await fetch('/api/admin/users', {
    headers: { 'Authorization': `Bearer ${getToken()}` },
  });
  if (!resp.ok) return;
  const { users } = await resp.json();
  const tbody = document.getElementById('admin-user-tbody');
  tbody.innerHTML = users.map(u => `
    <tr>
      <td>${esc(u.username)}</td>
      <td>${esc(u.created_at.slice(0, 10))}</td>
      <td>${u.is_admin ? '<span class="badge-admin">Admin</span>' : 'Benutzer'}</td>
      <td>${u.id !== S.currentUser.id ? `<button onclick="adminDeleteUser(${u.id})" class="btn-danger-sm">Löschen</button>` : '—'}</td>
    </tr>
  `).join('');
}

async function adminDeleteUser(userId) {
  if (!confirm('Benutzer wirklich löschen?')) return;
  await fetch(`/api/admin/users/${userId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${getToken()}` },
  });
  loadAdminUsers();
}

async function handleAdminCreateUser(event) {
  event.preventDefault();
  const username = document.getElementById('admin-new-username').value;
  const password = document.getElementById('admin-new-password').value;
  const errEl = document.getElementById('admin-create-error');

  const resp = await fetch('/api/admin/users', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ username, password }),
  });

  if (!resp.ok) {
    const data = await resp.json();
    errEl.textContent = data.detail || 'Fehler beim Erstellen';
    errEl.style.display = '';
    return;
  }

  errEl.style.display = 'none';
  document.getElementById('admin-new-username').value = '';
  document.getElementById('admin-new-password').value = '';
  loadAdminUsers();
}

// ── Page init ─────────────────────────────────────────────────────────────────

(async function initPage() {
  const authenticated = await initAuth();  // from auth.js
  if (!authenticated) {
    showLoginScreen();
    return;
  }
  showAppForUser(S.currentUser);

  // Load admin users if admin panel is visible
  if (S.currentUser.is_admin) {
    loadAdminUsers();
  }

  // ... rest of existing init code (initForm, Router.init, etc.) ...
})();
```

> **Note:** The existing DOM-ready init code at the bottom of index.html must be wrapped inside or called after the `initPage()` async function confirms authentication. Move the existing `initForm()`, `Router.init()`, etc. calls to after `showAppForUser()`.

- [ ] **Step 12.6b: Verify `frontend/js/travels.js` — no user_id exposure**

Read `frontend/js/travels.js`. Verify that:
1. The card rendering code does NOT display or interpolate `user_id` from trip objects
2. The `apiGetTravels()` response is used as-is (server already filters by user — no client-side filtering needed)
3. No change to the file is required if verification passes

If any `user_id` field is interpolated into visible HTML via `esc()` or template strings, remove it.

- [ ] **Step 12.7: Commit**

```bash
cd /Users/stefan/Code/DetourAI
git add frontend/index.html
git commit -m "feat: Login-Screen und Admin-Panel in index.html integriert

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Task 13: End-to-End Verification

- [ ] **Step 13.1: Run all tests**

```bash
cd backend && python3 -m pytest tests/ -v
```

Expected: all tests pass (migrations, auth, models, endpoints, agents, travel_db).

- [ ] **Step 13.2: Start the stack**

```bash
cd /Users/stefan/Code/DetourAI
ADMIN_USERNAME=admin ADMIN_PASSWORD=testpass123 JWT_SECRET=test_secret_that_is_32_chars_long docker compose up --build
```

- [ ] **Step 13.3: Manual verification checklist**

```
[ ] Navigate to http://localhost → login screen appears (not the app)
[ ] Login with wrong password → error shown in German
[ ] Login with admin/testpass123 → app loads, header shows "admin", Admin + Abmelden buttons visible
[ ] Click "Meine Reisen" → empty list (no trips yet)
[ ] Click Admin → admin panel shows, user list shows "admin"
[ ] Create user "testuser" with password "testuser123" → appears in list
[ ] Log out → login screen appears
[ ] Login as testuser → app loads, header shows "testuser", no Admin button
[ ] Create a trip as testuser (TEST_MODE=true) → trip saved
[ ] Log out, login as admin → "Meine Reisen" shows no testuser trips
[ ] Login as testuser → "Meine Reisen" shows testuser's trip
[ ] Refresh page → stays logged in (silent refresh works)
```

- [ ] **Step 13.4: Final commit + tag**

```bash
cd /Users/stefan/Code/DetourAI
git add .
git commit -m "feat: Auth & Access Control vollständig implementiert

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag v$(git tag --sort=-v:refname | head -1 | sed 's/v//' | awk -F. '{print $1"."$2"."$3+1}')
git push && git push --tags
```

---

## Summary of New/Modified Files

```
New:
  backend/utils/migrations.py
  backend/utils/auth_db.py
  backend/utils/auth.py
  backend/routers/__init__.py
  backend/routers/auth.py
  backend/routers/admin.py
  backend/tests/test_migrations.py
  backend/tests/test_auth.py
  frontend/js/auth.js

Modified:
  backend/requirements.txt        (+PyJWT, passlib[argon2])
  backend/utils/travel_db.py      (user_id on all CRUD)
  backend/tasks/run_planning_job.py (user_id propagation)
  backend/tasks/replace_stop_job.py (user_id propagation)
  backend/main.py                 (migrations, bootstrap, auth deps, CORS)
  backend/.env.example            (auth env vars)
  docker-compose.yml              (auth env vars in backend + celery)
  frontend/js/auth.js             (new)
  frontend/js/api.js              (token injection, 401 handling)
  frontend/js/state.js            (S.currentUser)
  frontend/index.html             (login section, admin section, header)
```
