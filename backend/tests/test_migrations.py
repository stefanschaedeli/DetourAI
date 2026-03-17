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


def test_failed_migration_rolls_back():
    """If a migration raises, the DB must not have a partial schema_migrations row."""
    import unittest.mock as mock
    path = make_db()
    try:
        # Create a copy of MIGRATIONS with a failing 4th migration
        failing_migrations = list(MIGRATIONS) + [(4, "fail_migration", "INVALID SQL !!!")]
        with mock.patch("utils.migrations.MIGRATIONS", failing_migrations):
            try:
                run_migrations(path)
            except RuntimeError:
                pass
        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = [row[0] for row in cur.fetchall()]
        # Only versions 1-3 should be present, not 4
        assert 4 not in applied
        assert applied == [1, 2, 3]
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
