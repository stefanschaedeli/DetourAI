import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
DB_PATH  = DATA_DIR / "travels.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS travels (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id         TEXT    NOT NULL,
                title          TEXT    NOT NULL,
                created_at     TEXT    NOT NULL,
                start_location TEXT    NOT NULL,
                destination    TEXT    NOT NULL,
                total_days     INTEGER NOT NULL,
                num_stops      INTEGER NOT NULL,
                total_cost_chf REAL    NOT NULL,
                plan_json      TEXT    NOT NULL,
                has_travel_guide INTEGER NOT NULL DEFAULT 0,
                UNIQUE(job_id)
            )
        """)
        # Migration: add column if it doesn't exist yet (for existing DBs)
        try:
            conn.execute("ALTER TABLE travels ADD COLUMN has_travel_guide INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists


def _build_title(plan: dict) -> str:
    stops = plan.get("stops", [])
    dest  = stops[-1]["region"] if stops else "?"
    days  = len(plan.get("day_plans", []))
    return f"{plan.get('start_location', '?')} → {dest} ({days} Tage)"


def _sync_save(plan: dict) -> Optional[int]:
    """INSERT OR IGNORE — duplicate job_ids silently skipped."""
    stops = plan.get("stops", [])
    cost  = plan.get("cost_estimate", {})
    has_guide = int(any(s.get("travel_guide") for s in stops))
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO travels
               (job_id,title,created_at,start_location,destination,
                total_days,num_stops,total_cost_chf,plan_json,has_travel_guide)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (plan.get("job_id", ""), _build_title(plan),
             datetime.utcnow().isoformat(),
             plan.get("start_location", ""),
             stops[-1]["region"] if stops else "",
             len(plan.get("day_plans", [])), len(stops),
             cost.get("total_chf", 0.0), json.dumps(plan), has_guide),
        )
        return cur.lastrowid if cur.rowcount else None


def _sync_list() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id,job_id,title,created_at,start_location,"
            "destination,total_days,num_stops,total_cost_chf,has_travel_guide "
            "FROM travels ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def _sync_get(travel_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT plan_json FROM travels WHERE id=?", (travel_id,)
        ).fetchone()
    return json.loads(row["plan_json"]) if row else None


def _sync_delete(travel_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM travels WHERE id=?", (travel_id,))
    return cur.rowcount > 0


# Async wrappers (matches existing asyncio.to_thread pattern in retry_helper.py)
async def save_travel(plan: dict) -> Optional[int]:
    return await asyncio.to_thread(_sync_save, plan)


async def list_travels() -> list:
    return await asyncio.to_thread(_sync_list)


async def get_travel(travel_id: int) -> Optional[dict]:
    return await asyncio.to_thread(_sync_get, travel_id)


async def delete_travel(travel_id: int) -> bool:
    return await asyncio.to_thread(_sync_delete, travel_id)
