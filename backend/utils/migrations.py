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
