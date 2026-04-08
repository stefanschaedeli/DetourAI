"""Wikipedia and Wikidata enrichment — city summaries and factual data for stops."""
import aiohttp
from typing import Optional

from utils.http_session import get_session


async def get_city_summary(city: str, language: str = "de") -> Optional[dict]:
    """Fetch a Wikipedia page summary for a city (free, no API key required).

    Returns a dict with title, extract, thumbnail_url, lat, and lon.
    Returns None on any HTTP error or exception.
    """
    try:
        url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{city}"
        session = await get_session()
        async with session.get(
            url,
            headers={"User-Agent": "DetourAI/1.0"},
            timeout=aiohttp.ClientTimeout(total=6),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            thumbnail = data.get("thumbnail", {})
            coordinates = data.get("coordinates", {})
            return {
                "title": data.get("title", city),
                "extract": data.get("extract", ""),
                "thumbnail_url": thumbnail.get("source") if thumbnail else None,
                "lat": coordinates.get("lat") if coordinates else None,
                "lon": coordinates.get("lon") if coordinates else None,
            }
    except Exception:
        return None


async def get_city_facts(city: str, country: str) -> Optional[dict]:
    """Fetch factual data for a city from Wikidata: population, elevation, and area.

    Performs a two-step query: first searches for the Wikidata entity by city+country name,
    then fetches property claims (P1082 population, P2044 elevation, P2046 area).
    Returns None on any error or if the entity is not found.
    """
    try:
        # Search for Wikidata entity via city and country name
        search_url = f"https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": f"{city} {country}",
            "language": "de",
            "limit": "1",
            "format": "json",
        }
        session = await get_session()
        async with session.get(
            search_url, params=params,
            headers={"User-Agent": "DetourAI/1.0"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return None
            search_data = await resp.json()
            results = search_data.get("search", [])
            if not results:
                return None
            entity_id = results[0]["id"]

        # Fetch entity claims
        entity_params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "claims",
            "format": "json",
        }
        async with session.get(
            search_url, params=entity_params,
            headers={"User-Agent": "DetourAI/1.0"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            entity = data.get("entities", {}).get(entity_id, {})
            claims = entity.get("claims", {})

            def _get_amount(prop: str) -> Optional[float]:
                vals = claims.get(prop, [])
                if vals:
                    amount = vals[-1].get("mainclaim", {}).get("datavalue", {}).get("value", {}).get("amount")
                    if amount is None:
                        ms = vals[-1].get("mainsnak", {})
                        dv = ms.get("datavalue", {}).get("value", {})
                        amount = dv.get("amount")
                    if amount:
                        return float(str(amount).lstrip("+"))
                return None

            population = _get_amount("P1082")
            elevation = _get_amount("P2044")
            area = _get_amount("P2046")

            return {
                "population": int(population) if population else None,
                "elevation_m": round(elevation, 0) if elevation else None,
                "area_km2": round(area, 1) if area else None,
            }
    except Exception:
        return None
