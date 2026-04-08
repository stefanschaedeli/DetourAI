"""Brave Search integration — local business search and web search fallback."""
import os
import aiohttp
from typing import Optional

from utils.http_session import get_session


async def search_local(query: str, count: int = 5) -> list[dict]:
    """Query the Brave Local Search API for structured business data.

    Returns a list of dicts with name, address, rating, rating_count, phone,
    and price_range fields. Returns an empty list if BRAVE_API_KEY is not set
    or the request fails.
    """
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []
    try:
        session = await get_session()
        async with session.get(
            "https://api.search.brave.com/res/v1/local/search",
            params={"q": query, "count": str(count)},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            results = []
            for loc in (data.get("results") or [])[:count]:
                results.append({
                    "name": loc.get("title", ""),
                    "address": loc.get("address", {}).get("streetAddress", ""),
                    "rating": loc.get("rating", {}).get("ratingValue"),
                    "rating_count": loc.get("rating", {}).get("ratingCount"),
                    "phone": loc.get("phone"),
                    "price_range": loc.get("priceRange"),
                })
            return results
    except Exception:
        return []


async def search_web(query: str, count: int = 5) -> list[dict]:
    """Query the Brave Web Search API — used as fallback when local search yields no results.

    Returns a list of dicts with name, url, and description fields.
    Returns an empty list if BRAVE_API_KEY is not set or the request fails.
    """
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []
    try:
        session = await get_session()
        async with session.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": str(count)},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            results = []
            for item in (data.get("web", {}).get("results") or [])[:count]:
                results.append({
                    "name": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                })
            return results
    except Exception:
        return []


async def search_places(query: str, count: int = 5) -> list[dict]:
    """Search for places using local search first, falling back to web search.

    Returns an empty list on error or when BRAVE_API_KEY is not configured.
    """
    results = await search_local(query, count)
    if results:
        return results
    return await search_web(query, count)
