import asyncio
import math
import aiohttp
from typing import Optional
from urllib.parse import quote


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
                timeout=aiohttp.ClientTimeout(total=4),
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
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                data = await r.json()
                if data.get("routes"):
                    route = data["routes"][0]
                    hours = round(route["duration"] / 3600, 1)
                    km    = round(route["distance"] / 1000, 0)
                    return hours, km
    except Exception:
        pass
    return 0.0, 0.0


async def osrm_route_with_geometry(coords: list[tuple[float, float]]) -> tuple[float, float, str]:
    """Like osrm_route() but returns (hours, km, polyline5_geometry)."""
    points = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = f"http://router.project-osrm.org/route/v1/driving/{points}?overview=simplified&geometries=polyline"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                data = await r.json()
                if data.get("routes"):
                    route = data["routes"][0]
                    hours = round(route["duration"] / 3600, 1)
                    km = round(route["distance"] / 1000, 0)
                    geometry = route.get("geometry", "")
                    return hours, km, geometry
    except Exception:
        pass
    return 0.0, 0.0, ""


def decode_polyline5(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google-encoded polyline (precision 5) into [(lat, lon), ...]."""
    points: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift = 0
            result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            diff = (~(result >> 1)) if (result & 1) else (result >> 1)
            if is_lng:
                lng += diff
            else:
                lat += diff
        points.append((lat / 1e5, lng / 1e5))
    return points


def _haversine_km_points(c1: tuple[float, float], c2: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lon) tuples."""
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def point_along_route(points: list[tuple[float, float]], target_km: float) -> tuple[float, float]:
    """Returns the (lat, lon) at target_km along the decoded polyline."""
    if not points:
        return (0.0, 0.0)
    accumulated = 0.0
    for i in range(1, len(points)):
        seg_km = _haversine_km_points(points[i - 1], points[i])
        if accumulated + seg_km >= target_km:
            # Interpolate on this segment
            remaining = target_km - accumulated
            ratio = remaining / seg_km if seg_km > 0 else 0.0
            lat = points[i - 1][0] + ratio * (points[i][0] - points[i - 1][0])
            lon = points[i - 1][1] + ratio * (points[i][1] - points[i - 1][1])
            return (lat, lon)
        accumulated += seg_km
    return points[-1]


async def reverse_geocode_nominatim(lat: float, lon: float) -> Optional[str]:
    """Returns city/town name for a coordinate, or None."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
                headers={"User-Agent": "Travelman2/1.0"},
                timeout=aiohttp.ClientTimeout(total=4),
            ) as r:
                data = await r.json()
                addr = data.get("address", {})
                return addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or data.get("name")
    except Exception:
        pass
    return None


async def reference_cities_along_route(
    points: list[tuple[float, float]], total_km: float, from_km: float, to_km: float, num_points: int = 3,
) -> list[str]:
    """Sample points in [from_km, to_km] along the route, reverse-geocode them."""
    if not points or total_km <= 0 or to_km <= from_km:
        return []
    step = (to_km - from_km) / (num_points + 1)
    cities: list[str] = []
    for i in range(1, num_points + 1):
        km = from_km + step * i
        lat, lon = point_along_route(points, km)
        await asyncio.sleep(0.35)  # Nominatim rate limit
        name = await reverse_geocode_nominatim(lat, lon)
        if name and name not in cities:
            cities.append(name)
    return cities


def corridor_bbox(
    points: list[tuple[float, float]], from_km: float, to_km: float, buffer_km: float = 30.0,
) -> dict:
    """Bounding box for the route section between from_km and to_km, plus buffer."""
    if not points:
        return {}
    # Collect all points in the range
    accumulated = 0.0
    in_range: list[tuple[float, float]] = []
    prev = points[0]
    if from_km == 0:
        in_range.append(prev)
    for i in range(1, len(points)):
        seg_km = _haversine_km_points(points[i - 1], points[i])
        new_acc = accumulated + seg_km
        if new_acc >= from_km and accumulated <= to_km:
            in_range.append(points[i])
        accumulated = new_acc
    if not in_range:
        # Fallback: use endpoints
        p1 = point_along_route(points, from_km)
        p2 = point_along_route(points, to_km)
        in_range = [p1, p2]
    lats = [p[0] for p in in_range]
    lons = [p[1] for p in in_range]
    # Buffer in degrees (~1° lat ≈ 111 km, ~1° lon ≈ 111*cos(lat) km)
    avg_lat = sum(lats) / len(lats)
    lat_buf = buffer_km / 111.0
    lon_buf = buffer_km / (111.0 * max(math.cos(math.radians(avg_lat)), 0.01))
    return {
        "min_lat": round(min(lats) - lat_buf, 4),
        "max_lat": round(max(lats) + lat_buf, 4),
        "min_lon": round(min(lons) - lon_buf, 4),
        "max_lon": round(max(lons) + lon_buf, 4),
    }


def build_maps_url(locations: list[str]) -> Optional[str]:
    """Builds Google Maps Directions URL."""
    locs = [l for l in locations if l]
    if not locs:
        return None
    if len(locs) == 1:
        return f"https://maps.google.com/?q={quote(locs[0])}"
    origin = quote(locs[0])
    dest   = quote(locs[-1])
    wp     = '|'.join(quote(l) for l in locs[1:-1])
    url    = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}"
    if wp:
        url += f"&waypoints={wp}"
    return url
