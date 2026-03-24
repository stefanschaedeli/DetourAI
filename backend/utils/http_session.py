"""Shared aiohttp ClientSession mit Connection-Pooling.

Verhindert Socket-/FD-Leaks durch Wiederverwendung einer einzelnen Session
über die gesamte Lebensdauer des Prozesses (FastAPI oder Celery-Worker).
"""

from typing import Optional
import aiohttp

_session: Optional[aiohttp.ClientSession] = None


async def get_session() -> aiohttp.ClientSession:
    """Gibt die gemeinsame ClientSession zurück (lazy-initialisiert)."""
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
        )
        _session = aiohttp.ClientSession(connector=connector)
    return _session


async def close_session() -> None:
    """Schliesst die gemeinsame Session (Shutdown-Cleanup)."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
