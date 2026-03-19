"""
CRUD for users and refresh_tokens tables.
All functions are synchronous (called via asyncio.to_thread from async context).
"""
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _db_path() -> str:
    default = str(Path(__file__).parent.parent.parent / "data")
    data_dir = os.getenv("DATA_DIR", default)
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
        # Check if travels table exists before trying to JOIN
        has_travels = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='travels'"
        ).fetchone() is not None
        if has_travels:
            rows = conn.execute(
                """SELECT u.id, u.username, u.is_admin, u.created_at, u.token_quota,
                          COALESCE(SUM(t.total_tokens), 0) AS token_total
                   FROM users u
                   LEFT JOIN travels t ON t.user_id = u.id
                   GROUP BY u.id
                   ORDER BY u.id"""
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, username, is_admin, created_at, token_quota, 0 AS token_total FROM users ORDER BY id"
            ).fetchall()
    return [dict(r) for r in rows]


def get_quota(user_id: int) -> Optional[int]:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT token_quota FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["token_quota"] if row else None
    except Exception:
        return None


def set_quota(user_id: int, quota: Optional[int]) -> bool:
    with _conn() as conn:
        cur = conn.execute("UPDATE users SET token_quota = ? WHERE id = ?", (quota, user_id))
        conn.commit()
    return cur.rowcount > 0


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
