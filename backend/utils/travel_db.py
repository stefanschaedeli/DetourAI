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
                user_id        INTEGER REFERENCES users(id),
                UNIQUE(job_id)
            )
        """)
        # Migration: add column if it doesn't exist yet (for existing DBs)
        try:
            conn.execute("ALTER TABLE travels ADD COLUMN has_travel_guide INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE travels ADD COLUMN custom_name TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE travels ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE travels ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except Exception:
            pass


def _build_title(plan: dict) -> str:
    stops = plan.get("stops", [])
    dest  = stops[-1]["region"] if stops else "?"
    days  = len(plan.get("day_plans", []))
    return f"{plan.get('start_location', '?')} → {dest} ({days} Tage)"


def _sync_save(plan: dict, user_id: int) -> Optional[int]:
    """INSERT OR IGNORE — duplicate job_ids silently skipped."""
    stops = plan.get("stops", [])
    cost  = plan.get("cost_estimate", {})
    has_guide = int(any(s.get("travel_guide") for s in stops))
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO travels
               (job_id,title,created_at,start_location,destination,
                total_days,num_stops,total_cost_chf,plan_json,has_travel_guide,user_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (plan.get("job_id", ""), _build_title(plan),
             datetime.utcnow().isoformat(),
             plan.get("start_location", ""),
             stops[-1]["region"] if stops else "",
             len(plan.get("day_plans", [])), len(stops),
             cost.get("total_chf", 0.0), json.dumps(plan), has_guide, user_id),
        )
        return cur.lastrowid if cur.rowcount else None


def _sync_list(user_id: int) -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id,job_id,title,created_at,start_location,"
            "destination,total_days,num_stops,total_cost_chf,has_travel_guide,"
            "custom_name,rating "
            "FROM travels WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _sync_get(travel_id: int, user_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT plan_json FROM travels WHERE id=? AND user_id=?",
            (travel_id, user_id),
        ).fetchone()
    return json.loads(row["plan_json"]) if row else None


def _sync_delete(travel_id: int, user_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM travels WHERE id=? AND user_id=?",
            (travel_id, user_id),
        )
    return cur.rowcount > 0


def _sync_update_plan_json(travel_id: int, user_id: int, plan: dict) -> bool:
    """Replace plan_json and refresh derived columns (num_stops, total_cost, etc.)."""
    stops = plan.get("stops", [])
    cost = plan.get("cost_estimate", {})
    has_guide = int(any(s.get("travel_guide") for s in stops))
    with _get_conn() as conn:
        cur = conn.execute(
            """UPDATE travels
               SET plan_json = ?, title = ?, num_stops = ?,
                   total_cost_chf = ?, has_travel_guide = ?,
                   total_days = ?, destination = ?
               WHERE id = ? AND user_id = ?""",
            (json.dumps(plan), _build_title(plan), len(stops),
             cost.get("total_chf", 0.0), has_guide,
             len(plan.get("day_plans", [])),
             stops[-1]["region"] if stops else "",
             travel_id, user_id),
        )
    return cur.rowcount > 0


def _sync_update(travel_id: int, user_id: int, custom_name: Optional[str], rating: Optional[int]) -> bool:
    fields: list = []
    values: list = []
    if custom_name is not None:
        fields.append("custom_name = ?")
        values.append(custom_name.strip() or None)
    if rating is not None:
        fields.append("rating = ?")
        values.append(max(0, min(5, rating)))
    if not fields:
        return True
    values.extend([travel_id, user_id])
    with _get_conn() as conn:
        cur = conn.execute(
            f"UPDATE travels SET {', '.join(fields)} WHERE id=? AND user_id=?",
            values,
        )
    return cur.rowcount > 0


# Async wrappers
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
