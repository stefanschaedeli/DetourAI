"""Google Places API client — nearby search, place details, photo URLs, and stop quality checks."""
import os
import aiohttp
from typing import Optional

from utils.http_session import get_session


def _api_key() -> Optional[str]:
    return os.getenv("GOOGLE_MAPS_API_KEY")


async def nearby_search(
    lat: float, lon: float, place_type: str,
    radius_m: int = 10000, keyword: str = "",
) -> list[dict]:
    """Query the Google Places Nearby Search API for places of a given type near a coordinate.

    Returns a list of place dicts with place_id, name, rating, user_ratings_total,
    price_level, address, lat, lon, photo_reference, and opening_hours.
    Returns an empty list if GOOGLE_MAPS_API_KEY is not set or the request fails.
    """
    key = _api_key()
    if not key:
        return []
    try:
        params = {
            "location": f"{lat},{lon}",
            "radius": str(radius_m),
            "type": place_type,
            "key": key,
            "language": "de",
        }
        if keyword:
            params["keyword"] = keyword
        session = await get_session()
        async with session.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                return []
            results = []
            for place in data.get("results", []):
                photos = place.get("photos", [])
                results.append({
                    "place_id": place.get("place_id"),
                    "name": place.get("name", ""),
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "price_level": place.get("price_level"),
                    "address": place.get("vicinity", ""),
                    "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                    "lon": place.get("geometry", {}).get("location", {}).get("lng"),
                    "photo_reference": photos[0].get("photo_reference") if photos else None,
                    "opening_hours": place.get("opening_hours", {}).get("open_now"),
                })
            return results
    except Exception:
        return []


async def place_details(place_id: str) -> dict:
    """Fetch detailed info for a place from the Google Places Details API.

    Returns a dict with name, formatted_address, formatted_phone_number, website,
    rating, reviews, opening_hours, and photos. Returns an empty dict on failure.
    """
    key = _api_key()
    if not key:
        return {}
    try:
        params = {
            "place_id": place_id,
            "fields": "name,formatted_address,formatted_phone_number,website,rating,reviews,opening_hours,photos",
            "key": key,
            "language": "de",
        }
        session = await get_session()
        async with session.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            return data.get("result", {})
    except Exception:
        return {}


def place_photo_url(photo_reference: str, max_width: int = 400) -> Optional[str]:
    """Build a Google Places Photo URL for the given photo reference. Returns None if no API key."""
    key = _api_key()
    if not key or not photo_reference:
        return None
    return (
        f"https://maps.googleapis.com/maps/api/place/photo"
        f"?photoreference={photo_reference}"
        f"&maxwidth={max_width}"
        f"&key={key}"
    )


async def find_place_from_text(input_text: str) -> Optional[dict]:
    """Google Find Place API — returns place_id, name, lat, lon for best match.
    Uses Find Place From Text ($17/1000) — cheaper than Text Search ($32/1000)."""
    key = _api_key()
    if not key:
        return None
    try:
        params = {
            "input": input_text,
            "inputtype": "textquery",
            "fields": "place_id,name,geometry,formatted_address",
            "key": key,
            "language": "de",
        }
        session = await get_session()
        async with session.get(
            "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None
            place = candidates[0]
            loc = place.get("geometry", {}).get("location", {})
            return {
                "place_id": place.get("place_id"),
                "name": place.get("name", ""),
                "lat": loc.get("lat"),
                "lon": loc.get("lng"),
                "address": place.get("formatted_address", ""),
            }
    except Exception:
        return None


async def text_search(query: str, location_bias: tuple[float, float] = None) -> list[dict]:
    """Google Places Text Search — returns place_id, name, lat, lon, rating, address."""
    key = _api_key()
    if not key:
        return []
    try:
        params = {
            "query": query,
            "key": key,
            "language": "de",
        }
        if location_bias:
            params["location"] = f"{location_bias[0]},{location_bias[1]}"
            params["radius"] = "50000"
        session = await get_session()
        async with session.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                return []
            results = []
            for place in data.get("results", []):
                photos = place.get("photos", [])
                loc = place.get("geometry", {}).get("location", {})
                results.append({
                    "place_id": place.get("place_id"),
                    "name": place.get("name", ""),
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total", 0),
                    "address": place.get("formatted_address", ""),
                    "lat": loc.get("lat"),
                    "lon": loc.get("lng"),
                    "photo_reference": photos[0].get("photo_reference") if photos else None,
                })
            return results
    except Exception:
        return []


async def validate_stop_quality(region: str, country: str, lat: float, lon: float) -> tuple[bool, str]:
    """Check stop quality via Google Places. Returns (is_quality, reason).
    Uses find_place_from_text as first pass (cheapest API call).
    Only calls nearby_search if first check passes -- controls API cost."""
    # Strategy 1: Does this place exist in Google Places?
    result = await find_place_from_text(f"{region}, {country}")
    if not result:
        return False, "Kein Google Places Ergebnis"

    # Strategy 2: Check nearby tourist attractions (does this place have interesting things?)
    attractions = await nearby_search(lat, lon, "tourist_attraction", radius_m=5000)
    if len(attractions) < 2:
        return False, f"Zu wenige Sehenswuerdigkeiten ({len(attractions)})"

    # Strategy 3: Check average rating of nearby attractions
    rated = [a for a in attractions if a.get("rating")]
    if rated:
        avg_rating = sum(a["rating"] for a in rated) / len(rated)
        if avg_rating < 3.0:
            return False, f"Niedrige durchschnittliche Bewertung: {avg_rating:.1f}"

    return True, "OK"


async def search_restaurants(lat: float, lon: float, radius_m: int = 10000) -> list[dict]:
    """Convenience wrapper: search for restaurants near a coordinate."""
    return await nearby_search(lat, lon, "restaurant", radius_m)


async def search_hotels(lat: float, lon: float, radius_m: int = 10000) -> list[dict]:
    """Convenience wrapper: search for hotels and lodging near a coordinate."""
    return await nearby_search(lat, lon, "lodging", radius_m)


async def search_attractions(lat: float, lon: float, radius_m: int = 10000) -> list[dict]:
    """Convenience wrapper: search for tourist attractions near a coordinate."""
    return await nearby_search(lat, lon, "tourist_attraction", radius_m)
