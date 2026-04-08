"""Redis-based advisory edit lock per travel.

Prevents concurrent route modifications on the same travel.
Uses SET ... NX EX pattern for atomic lock acquisition.
TTL = 300s as safety net against abandoned locks.
"""

import os

EDIT_LOCK_TTL = 300  # 5 minutes


def _get_redis():
    """Return Redis client (from services.redis_store)."""
    from services.redis_store import redis_client
    return redis_client


def acquire_edit_lock(travel_id: int) -> bool:
    """Acquire an advisory edit lock for a travel. Returns True if acquired."""
    r = _get_redis()
    if hasattr(r, 'set'):
        return bool(r.set(f"edit_lock:{travel_id}", "1", nx=True, ex=EDIT_LOCK_TTL))
    # InMemoryStore fallback: always allow (single process)
    return True


def release_edit_lock(travel_id: int) -> None:
    """Release the advisory edit lock for a travel."""
    r = _get_redis()
    if hasattr(r, 'delete'):
        r.delete(f"edit_lock:{travel_id}")
