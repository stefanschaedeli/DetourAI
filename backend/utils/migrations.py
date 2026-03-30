"""
Versioned SQLite migration runner.

Add new migrations by appending to MIGRATIONS — never modify existing entries.
Each migration runs in a transaction; failure rolls back and raises (startup aborts).
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Callable, List, Tuple, Union


def _fix_arrival_day_chaining(conn: sqlite3.Connection) -> None:
    """Re-chain arrival_day on all saved travels to fix v1.1 nights-edit drift."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='travels'"
    )
    if cur.fetchone() is None:
        return
    rows = conn.execute("SELECT id, plan_json FROM travels").fetchall()
    for row in rows:
        try:
            plan = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            continue
        stops = plan.get("stops")
        if not stops or len(stops) == 0:
            continue
        # Rechain arrival_day: stop 0 = day 1, each subsequent = prev + prev.nights + 1
        changed = False
        expected = 1
        for stop in stops:
            if stop.get("arrival_day") != expected:
                stop["arrival_day"] = expected
                changed = True
            expected = expected + stop.get("nights", 1) + 1
        if changed:
            conn.execute(
                "UPDATE travels SET plan_json = ? WHERE id = ?",
                (json.dumps(plan), row[0]),
            )


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
    (
        4,
        "travels_add_token_columns",
        lambda conn: [
            _add_column_if_missing(conn, "travels", "total_input_tokens",  "INTEGER NOT NULL DEFAULT 0"),
            _add_column_if_missing(conn, "travels", "total_output_tokens", "INTEGER NOT NULL DEFAULT 0"),
            _add_column_if_missing(conn, "travels", "total_tokens",        "INTEGER NOT NULL DEFAULT 0"),
        ],
    ),
    (
        5,
        "users_add_token_quota",
        lambda conn: _add_column_if_missing(conn, "users", "token_quota", "INTEGER"),
    ),
    (
        6,
        "travels_add_share_token",
        lambda conn: _add_column_if_missing(conn, "travels", "share_token", "TEXT"),
    ),
    (
        7,
        "fix_arrival_day_chaining",
        _fix_arrival_day_chaining,
    ),
    (
        8,
        "travels_add_language",
        lambda conn: _add_column_if_missing(conn, "travels", "language", "TEXT NOT NULL DEFAULT 'de'"),
    ),
]


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    # SECURITY: table, column, and col_def MUST be hardcoded constants — never pass
    # user-supplied input here, as the values are interpolated directly into SQL.
    # If the table doesn't exist yet (fresh DB without legacy data), skip silently.
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    if cur.fetchone() is None:
        return
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
    # Assert migrations are in strictly ascending version order.
    versions = [m[0] for m in MIGRATIONS]
    assert versions == sorted(versions) and len(versions) == len(set(versions)), (
        "MIGRATIONS must be in strictly ascending version order without duplicates"
    )

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
