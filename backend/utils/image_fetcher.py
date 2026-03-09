from __future__ import annotations

import asyncio
import os
import aiohttp
from utils.debug_logger import debug_logger, LogLevel

_VALID_PREFIXES = (
    "https://images.unsplash.com/",
    "https://plus.unsplash.com/",
)

_ROLES = [
    ("image_overview", "overview landscape"),
    ("image_mood",     "atmosphere people"),
    ("image_customer", "tourist visitor candid"),
]

# Lazily initialized semaphore (Python 3.9 requires an active event loop at creation time)
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(3)
    return _semaphore


def _validate_unsplash_url(url: str | None) -> str | None:
    if url and any(url.startswith(p) for p in _VALID_PREFIXES):
        return url
    return None


async def fetch_unsplash_images(subject: str, context: str) -> dict:
    """Fetch 3 semantically-distinct Unsplash photos for a given subject.

    Returns dict with keys: image_overview, image_mood, image_customer.
    All values are validated HTTPS URLs or None on failure.
    """
    access_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not access_key:
        await debug_logger.log(
            LogLevel.WARNING,
            "UNSPLASH_ACCESS_KEY nicht gesetzt — Bilder werden übersprungen",
        )
        return {"image_overview": None, "image_mood": None, "image_customer": None}

    result: dict = {}

    async with _get_semaphore():
        async with aiohttp.ClientSession() as session:
            for field, suffix in _ROLES:
                query = f"{subject} {suffix}"
                url = await _fetch_one(session, access_key, query)
                result[field] = url
                await asyncio.sleep(0.1)  # 100ms between requests

    return result


async def _fetch_one(
    session: aiohttp.ClientSession,
    access_key: str,
    query: str,
) -> str | None:
    try:
        async with session.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Unsplash API Fehler {resp.status} für '{query}': {body[:200]}",
                )
                return None
            data = await resp.json()
            results = data.get("results", [])
            if not results:
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Unsplash: keine Ergebnisse für '{query}'",
                )
                return None
            raw_url = results[0].get("urls", {}).get("regular")
            validated = _validate_unsplash_url(raw_url)
            if not validated:
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Unsplash: URL-Validierung fehlgeschlagen für '{raw_url}'",
                )
            return validated
    except Exception as e:
        await debug_logger.log(
            LogLevel.WARNING,
            f"Unsplash: Exception für '{query}': {e}",
        )
        return None
