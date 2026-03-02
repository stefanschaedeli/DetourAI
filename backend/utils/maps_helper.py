import asyncio
import aiohttp
from typing import Optional


async def geocode_nominatim(place: str, country_code: str = "") -> Optional[tuple[float, float]]:
    """Returns (lat, lon) or None. Max 1 req/s — caller must sleep."""
    params = {"q": place, "format": "json", "limit": 1}
    if country_code:
        params["countrycodes"] = country_code.lower()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": "Travelman2/1.0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


async def osrm_route(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Returns (hours, km). coords = [(lat,lon), ...]"""
    points = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"http://router.project-osrm.org/route/v1/driving/{points}?overview=false"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                if data.get("routes"):
                    route = data["routes"][0]
                    hours = round(route["duration"] / 3600, 1)
                    km    = round(route["distance"] / 1000, 0)
                    return hours, km
    except Exception:
        pass
    return 0.0, 0.0


def build_maps_url(locations: list[str]) -> Optional[str]:
    """Builds Google Maps Directions URL."""
    locs = [l for l in locations if l]
    if not locs:
        return None
    if len(locs) == 1:
        return f"https://maps.google.com/?q={locs[0].replace(' ', '+')}"
    origin = locs[0].replace(' ', '+')
    dest   = locs[-1].replace(' ', '+')
    wp     = '|'.join(l.replace(' ', '+') for l in locs[1:-1])
    url    = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}"
    if wp:
        url += f"&waypoints={wp}"
    return url
