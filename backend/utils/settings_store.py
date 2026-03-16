"""SQLite Key-Value Store für Tool-Einstellungen — folgt dem Pattern von travel_db.py."""
import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
DB_PATH = DATA_DIR / "settings.db"

# ── Cache ──
_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0

DEFAULTS: dict[str, Any] = {
    # ── Agent-Modelle ──
    "agent.route_architect.model": "claude-opus-4-5",
    "agent.stop_options_finder.model": "claude-haiku-4-5",
    "agent.region_planner.model": "claude-opus-4-5",
    "agent.accommodation_researcher.model": "claude-sonnet-4-5",
    "agent.activities.model": "claude-sonnet-4-5",
    "agent.restaurants.model": "claude-sonnet-4-5",
    "agent.day_planner.model": "claude-opus-4-5",
    "agent.travel_guide.model": "claude-sonnet-4-5",
    "agent.trip_analysis.model": "claude-opus-4-5",

    # ── Agent max_tokens ──
    "agent.route_architect.max_tokens": 2048,
    "agent.stop_options_finder.max_tokens": 1500,
    "agent.region_planner.max_tokens": 4096,
    "agent.accommodation_researcher.max_tokens": 3500,
    "agent.activities.max_tokens": 2048,
    "agent.restaurants.max_tokens": 1024,
    "agent.day_planner.max_tokens": 2048,
    "agent.travel_guide.max_tokens": 4096,
    "agent.trip_analysis.max_tokens": 2048,

    # ── Budget-Standardwerte ──
    "budget.accommodation_pct": 45,
    "budget.fallback_accommodation_chf": 120,
    "budget.fallback_activities_chf": 80,
    "budget.fallback_food_chf": 50,
    "budget.fuel_chf_per_hour": 12,
    "budget.acc_multiplier_min": 0.75,
    "budget.acc_multiplier_max": 1.30,

    # ── API & Performance ──
    "api.wikipedia_timeout_s": 8,
    "api.retry_max_attempts": 5,
    "api.accommodation_parallelism": 2,

    # ── Geografie ──
    "geo.corridor_buffer_km": 30,

    # ── System ──
    "system.test_mode": True,
    "system.log_retention_days": 30,
    "system.redis_job_ttl_s": 86400,
}

ALLOWED_MODELS = ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"]

# ── Validation ranges ──
_RANGES: dict[str, tuple[Any, Any]] = {
    "agent.route_architect.max_tokens": (512, 8192),
    "agent.stop_options_finder.max_tokens": (512, 8192),
    "agent.region_planner.max_tokens": (512, 8192),
    "agent.accommodation_researcher.max_tokens": (512, 8192),
    "agent.activities.max_tokens": (512, 8192),
    "agent.restaurants.max_tokens": (512, 8192),
    "agent.day_planner.max_tokens": (512, 8192),
    "agent.travel_guide.max_tokens": (512, 8192),
    "agent.trip_analysis.max_tokens": (512, 8192),
    "budget.accommodation_pct": (5, 80),
    "budget.fallback_accommodation_chf": (10, 500),
    "budget.fallback_activities_chf": (10, 300),
    "budget.fallback_food_chf": (10, 200),
    "budget.fuel_chf_per_hour": (5, 50),
    "budget.acc_multiplier_min": (0.5, 2.0),
    "budget.acc_multiplier_max": (0.5, 2.0),
    "api.wikipedia_timeout_s": (1, 30),
    "api.retry_max_attempts": (1, 10),
    "api.accommodation_parallelism": (1, 5),
    "geo.corridor_buffer_km": (10, 100),
    "system.log_retention_days": (1, 365),
    "system.redis_job_ttl_s": (3600, 604800),
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)


_init_db()


def _invalidate_cache() -> None:
    global _cache, _cache_ts
    _cache = {}
    _cache_ts = 0.0


def _load_cache() -> dict[str, Any]:
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache
    with _get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    _cache = {row["key"]: json.loads(row["value"]) for row in rows}
    _cache_ts = now
    return _cache


def _sync_get_setting(key: str) -> Any:
    """Gibt den gespeicherten Wert oder den Default zurück."""
    stored = _load_cache()
    if key in stored:
        return stored[key]
    return DEFAULTS.get(key)


def _sync_set_setting(key: str, value: Any) -> None:
    """Setzt einen einzelnen Wert."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
    _invalidate_cache()


def _sync_get_all() -> dict[str, Any]:
    """Gibt alle Settings zurück (Defaults + Overrides)."""
    stored = _load_cache()
    merged = dict(DEFAULTS)
    merged.update(stored)
    return merged


def _sync_reset_section(prefix: str) -> int:
    """Löscht alle gespeicherten Werte mit dem gegebenen Prefix."""
    with _get_conn() as conn:
        if prefix == "all":
            cur = conn.execute("DELETE FROM settings")
        else:
            cur = conn.execute("DELETE FROM settings WHERE key LIKE ?", (f"{prefix}.%",))
    _invalidate_cache()
    return cur.rowcount


def validate_setting(key: str, value: Any) -> Optional[str]:
    """Validiert einen Wert. Gibt Fehlermeldung zurück oder None bei Erfolg."""
    if key not in DEFAULTS:
        return f"Unbekannter Schlüssel: {key}"

    default = DEFAULTS[key]

    # Typ-Check
    if isinstance(default, bool):
        if not isinstance(value, bool):
            return f"{key}: Boolean erwartet"
    elif isinstance(default, int):
        if not isinstance(value, (int, float)):
            return f"{key}: Zahl erwartet"
        value = int(value)
    elif isinstance(default, float):
        if not isinstance(value, (int, float)):
            return f"{key}: Zahl erwartet"
        value = float(value)
    elif isinstance(default, str):
        if not isinstance(value, str):
            return f"{key}: String erwartet"

    # Model-Allowlist
    if key.endswith(".model"):
        if value not in ALLOWED_MODELS:
            return f"{key}: Modell muss eines von {ALLOWED_MODELS} sein"

    # Range-Check
    if key in _RANGES:
        lo, hi = _RANGES[key]
        if isinstance(value, (int, float)) and not (lo <= value <= hi):
            return f"{key}: Wert muss zwischen {lo} und {hi} liegen"

    return None


# ── Sync API ──

def get_setting(key: str) -> Any:
    return _sync_get_setting(key)


def set_setting(key: str, value: Any) -> None:
    _sync_set_setting(key, value)


def get_all_settings() -> dict[str, Any]:
    return _sync_get_all()


def reset_section(prefix: str) -> int:
    return _sync_reset_section(prefix)


# ── Async Wrapper ──

async def async_get_setting(key: str) -> Any:
    return await asyncio.to_thread(_sync_get_setting, key)


async def async_set_setting(key: str, value: Any) -> None:
    await asyncio.to_thread(_sync_set_setting, key, value)


async def async_get_all_settings() -> dict[str, Any]:
    return await asyncio.to_thread(_sync_get_all)


async def async_reset_section(prefix: str) -> int:
    return await asyncio.to_thread(_sync_reset_section, prefix)
