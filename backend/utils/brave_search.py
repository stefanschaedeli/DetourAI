import os
import aiohttp
from typing import Optional


async def search_local(query: str, count: int = 5) -> list[dict]:
    """Brave Local Search — strukturierte Business-Daten. Gibt [] zurück wenn kein API-Key."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []
    try:
        async with aiohttp.ClientSession() as session:
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
    """Brave Web Search — Fallback wenn Local keine Ergebnisse liefert."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []
    try:
        async with aiohttp.ClientSession() as session:
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
    """Local Search zuerst, Fallback auf Web Search. Gibt [] bei Fehler/kein Key."""
    results = await search_local(query, count)
    if results:
        return results
    return await search_web(query, count)
