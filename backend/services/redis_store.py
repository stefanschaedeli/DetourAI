"""Redis job store — get/save job state with in-memory fallback for local development."""
import json
import os
import re

import redis as redis_lib
from fastapi import HTTPException
from utils.i18n import t as i18n_t

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ---------------------------------------------------------------------------
# Redis client with in-memory fallback for local dev (no Redis installed)
# ---------------------------------------------------------------------------

class _InMemoryStore:
    """Drop-in Redis replacement for local dev when Redis is unavailable."""
    def __init__(self):
        self._store: dict = {}

    def get(self, key):
        return self._store.get(key)

    def setex(self, key, ttl, value):
        self._store[key] = value

    def keys(self, pattern="*"):
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    def delete(self, key):
        self._store.pop(key, None)


def _make_redis_client():
    """Connect to Redis and return the client, or fall back to _InMemoryStore on failure."""
    try:
        client = redis_lib.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        print(f"\033[92m[INFO] Redis connected: {REDIS_URL}\033[0m")
        return client
    except Exception:
        print("\033[93m[WARNING] Redis nicht erreichbar — verwende In-Memory-Speicher (nur für lokale Entwicklung)\033[0m")
        return _InMemoryStore()


redis_client = _make_redis_client()
_USE_CELERY = not isinstance(redis_client, _InMemoryStore)

_JOB_ID_RE = re.compile(r'^[a-f0-9]{32}$')


def _job_lang(job: dict) -> str:
    """Extract language from a stored job dict (falls back to 'de')."""
    return job.get("request", {}).get("language", "de")


def get_job(job_id: str) -> dict:
    """Fetch and deserialise a job from Redis by job_id.

    Raises HTTP 404 if job_id is not a valid 32-char hex string or the key does not exist.
    """
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=404, detail=i18n_t("error.job_not_found", "de"))
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail=i18n_t("error.job_not_found", "de"))
    return json.loads(raw)


def save_job(job_id: str, job: dict):
    """Serialise and store a job dict in Redis with a 24-hour TTL."""
    redis_client.setex(f"job:{job_id}", 86400, json.dumps(job))
