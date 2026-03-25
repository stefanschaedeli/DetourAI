import os
import asyncio
import math
import aiohttp
from collections import OrderedDict
from typing import Optional
from urllib.parse import quote

from utils.http_session import get_session


# Bounded geocode cache (max 2000 entries, FIFO eviction)
_GEOCODE_CACHE_MAX = 2000
_geocode_cache: OrderedDict[str, tuple[float, float, str]] = OrderedDict()


def _google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_MAPS_API_KEY")


async def geocode_google(place: str, country_code: str = "") -> Optional[tuple[float, float, str]]:
    """Google Geocoding API: place → (lat, lon, place_id) or None.
    No rate-limit sleep needed (Google allows 50 QPS).
    Uses in-memory cache to avoid duplicate calls."""
    cache_key = f"{place}|{country_code}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]
    key = _google_api_key()
    if not key:
        return None
    params = {"address": place, "key": key, "language": "de"}
    if country_code:
        params["components"] = f"country:{country_code.upper()}"
    try:
        s = await get_session()
        async with s.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            data = await r.json()
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                loc = result["geometry"]["location"]
                place_id = result.get("place_id", "")
                entry = (float(loc["lat"]), float(loc["lng"]), place_id)
                _geocode_cache[cache_key] = entry
                if len(_geocode_cache) > _GEOCODE_CACHE_MAX:
                    _geocode_cache.popitem(last=False)
                return entry
    except Exception:
        pass
    return None


async def reverse_geocode_google(lat: float, lon: float) -> Optional[tuple[str, str]]:
    """Google Reverse Geocoding: (lat, lon) → (place_name, place_id) or None."""
    key = _google_api_key()
    if not key:
        return None
    try:
        s = await get_session()
        async with s.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"latlng": f"{lat},{lon}", "key": key, "language": "de"},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            data = await r.json()
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                # Extract city-level name from address components
                name = None
                for comp in result.get("address_components", []):
                    if "locality" in comp.get("types", []):
                        name = comp["long_name"]
                        break
                    if "administrative_area_level_2" in comp.get("types", []) and not name:
                        name = comp["long_name"]
                if not name:
                    name = result.get("formatted_address", "").split(",")[0]
                place_id = result.get("place_id", "")
                return (name, place_id)
    except Exception:
        pass
    return None


async def google_directions(origin: str, destination: str, waypoints: list[str] = None) -> tuple[float, float, str]:
    """Google Directions API: → (hours, km, encoded_polyline).
    Accepts place_ids (prefix 'place_id:ChIJ...') or addresses."""
    key = _google_api_key()
    if not key:
        return (0.0, 0.0, "")
    params = {
        "origin": origin,
        "destination": destination,
        "key": key,
        "mode": "driving",
        "language": "de",
    }
    if waypoints:
        params["waypoints"] = "|".join(waypoints)
    try:
        s = await get_session()
        async with s.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
            if data.get("status") == "OK" and data.get("routes"):
                route = data["routes"][0]
                total_seconds = sum(leg["duration"]["value"] for leg in route["legs"])
                total_meters = sum(leg["distance"]["value"] for leg in route["legs"])
                hours = round(total_seconds / 3600, 1)
                km = round(total_meters / 1000, 0)
                polyline = route.get("overview_polyline", {}).get("points", "")
                return (hours, km, polyline)
    except Exception:
        pass
    return (0.0, 0.0, "")


async def google_directions_simple(origin: str, destination: str) -> tuple[float, float]:
    """Convenience: only (hours, km) — no polyline needed."""
    hours, km, _ = await google_directions(origin, destination)
    return (hours, km)


async def reference_cities_along_route_google(
    origin: str, destination: str, num_points: int = 3,
) -> list[str]:
    """Find cities along route via Google Directions + Reverse Geocoding."""
    hours, km, polyline = await google_directions(origin, destination)
    if not polyline or km <= 0:
        return []
    points = decode_polyline5(polyline)
    if not points:
        return []
    step = km / (num_points + 1)
    cities: list[str] = []
    for i in range(1, num_points + 1):
        target_km = step * i
        lat, lon = point_along_route(points, target_km)
        result = await reverse_geocode_google(lat, lon)
        if result:
            name, _ = result
            if name and name not in cities:
                cities.append(name)
    return cities


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


def haversine_km(c1: tuple[float, float], c2: tuple[float, float]) -> float:
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
        seg_km = haversine_km(points[i - 1], points[i])
        if accumulated + seg_km >= target_km:
            # Interpolate on this segment
            remaining = target_km - accumulated
            ratio = remaining / seg_km if seg_km > 0 else 0.0
            lat = points[i - 1][0] + ratio * (points[i][0] - points[i - 1][0])
            lon = points[i - 1][1] + ratio * (points[i][1] - points[i - 1][1])
            return (lat, lon)
        accumulated += seg_km
    return points[-1]


def corridor_bbox(
    points: list[tuple[float, float]], from_km: float, to_km: float, buffer_km: float = 50.0,
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
        seg_km = haversine_km(points[i - 1], points[i])
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


def bearing_degrees(from_coord: tuple[float, float], to_coord: tuple[float, float]) -> float:
    """Calculate initial bearing from from_coord to to_coord in degrees (0-360)."""
    lat1, lon1 = math.radians(from_coord[0]), math.radians(from_coord[1])
    lat2, lon2 = math.radians(to_coord[0]), math.radians(to_coord[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def bearing_deviation(bearing1: float, bearing2: float) -> float:
    """Absolute angular difference between two bearings (0-180)."""
    diff = abs(bearing1 - bearing2) % 360
    return min(diff, 360 - diff)


def proportional_corridor_buffer(leg_distance_km: float) -> float:
    """Buffer in km = 20% of leg distance, clamped to [15, 100] km."""
    buffer = leg_distance_km * 0.20
    return max(15.0, min(buffer, 100.0))


def build_maps_url(locations: list[str], place_ids: list[str] = None) -> Optional[str]:
    """Builds Google Maps Directions URL. Uses Place IDs when available."""
    locs = [l for l in locations if l]
    if not locs:
        return None
    if len(locs) == 1:
        pid = place_ids[0] if place_ids and place_ids[0] else None
        if pid:
            return f"https://www.google.com/maps/place/?q=place_id:{pid}"
        return f"https://maps.google.com/?q={quote(locs[0])}"
    # Helper: prefer place_id over text name for precision
    def loc_str(idx: int) -> str:
        if place_ids and idx < len(place_ids) and place_ids[idx]:
            return quote(f"place_id:{place_ids[idx]}")
        return quote(locs[idx])

    origin = loc_str(0)
    dest = loc_str(len(locs) - 1)
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}"

    # Also add place_id params for origin/dest (belt-and-suspenders)
    if place_ids:
        if len(place_ids) > 0 and place_ids[0]:
            url += f"&origin_place_id={place_ids[0]}"
        if len(place_ids) > len(locs) - 1 and place_ids[-1]:
            url += f"&destination_place_id={place_ids[-1]}"

    # Waypoints with place_ids where available
    if len(locs) > 2:
        wp_parts = [loc_str(i) for i in range(1, len(locs) - 1)]
        url += f"&waypoints={'|'.join(wp_parts)}"

    return url
