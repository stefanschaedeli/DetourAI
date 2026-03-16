import asyncio
import json
import math
import os
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import redis as redis_lib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from models.travel_request import TravelRequest
from models.stop_option import StopSelectRequest
from models.accommodation_option import AccommodationSelectRequest, BudgetState, AccommodationResearchRequest
from models.trip_leg import ReplaceRegionRequest, RecomputeRegionsRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.maps_helper import (
    geocode_google, google_directions, google_directions_simple,
    reverse_geocode_google, reference_cities_along_route_google,
    build_maps_url, decode_polyline5, point_along_route, corridor_bbox,
)

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


def _fire_task(task_name: str, job_id: str, **kwargs):
    """
    Dispatch a background task.
    - With Redis available: use Celery (.delay)
    - Without Redis: run as asyncio background task in the same process
    """
    if _USE_CELERY:
        if task_name == "prefetch_accommodations":
            from tasks.prefetch_accommodations import prefetch_accommodations_task
            prefetch_accommodations_task.delay(job_id)
        elif task_name == "run_planning_job":
            from tasks.run_planning_job import run_planning_job_task
            run_planning_job_task.delay(job_id, **kwargs)
        elif task_name == "replace_stop_job":
            from tasks.replace_stop_job import replace_stop_job_task
            replace_stop_job_task.delay(job_id)
    else:
        # Run inline as a fire-and-forget asyncio task
        if task_name == "prefetch_accommodations":
            from tasks.prefetch_accommodations import _prefetch_all_accommodations
            asyncio.ensure_future(_prefetch_all_accommodations(job_id))
        elif task_name == "run_planning_job":
            from tasks.run_planning_job import _run_job
            asyncio.ensure_future(_run_job(job_id, **kwargs))
        elif task_name == "replace_stop_job":
            from tasks.replace_stop_job import _replace_stop_job
            asyncio.ensure_future(_replace_stop_job(job_id))


app = FastAPI(title="Travelman2 API", version="1.0.0")

_CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,http://localhost:80,http://127.0.0.1"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging
    logger = logging.getLogger("uvicorn")
    # Log the raw request body for debugging
    try:
        body = await request.body()
        logger.error(f"Request body: {body.decode('utf-8', errors='replace')[:2000]}")
    except Exception:
        pass
    errors = [
        {k: str(v) if not isinstance(v, (str, int, float, bool, list, tuple, type(None))) else v
         for k, v in e.items()}
        for e in exc.errors()
    ]
    logger.error(f"Validation error: {errors}")
    return JSONResponse(status_code=422, content={"detail": errors})

OUTPUTS_DIR = Path(os.environ.get("OUTPUTS_DIR", str(Path(__file__).parent.parent / "outputs")))
OUTPUTS_DIR.mkdir(exist_ok=True)

from utils.travel_db import _init_db, save_travel, list_travels, get_travel, delete_travel, update_travel, update_plan_json
from utils.settings_store import (
    get_setting, async_get_all_settings, async_reset_section,
    validate_setting, set_setting, DEFAULTS, ALLOWED_MODELS,
)
_init_db()

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Serve frontend static files at / (must be mounted after all /api routes are defined)
# We add a root redirect here and mount static at the end of the file.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JOB_ID_RE = re.compile(r'^[a-f0-9]{32}$')


def get_job(job_id: str) -> dict:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail=f"Job {job_id} nicht gefunden")
    return json.loads(raw)


def save_job(job_id: str, job: dict):
    redis_client.setex(f"job:{job_id}", 86400, json.dumps(job))


def _calc_leg_segment_budget(request: TravelRequest, leg_index: int) -> int:
    """Distributes leg days across N segments within the leg."""
    leg = request.legs[leg_index]
    n = max(1, len(leg.via_points) + 1)
    days = [leg.total_days // n] * n
    for i in range(leg.total_days % n):
        days[i] += 1
    min_days = (request.min_nights_per_stop + 1) * 2
    result = days[0]   # start at segment 0 within leg
    return max(min_days, result)


def _calc_route_status(request: TravelRequest, segment_stops: list, segment_budget: int,
                       is_last_segment: bool) -> dict:
    """Determines must_complete and route_could_be_complete for current segment."""
    days_used = sum(1 + s.get("nights", request.min_nights_per_stop) for s in segment_stops)
    days_remaining = max(0, segment_budget - days_used)
    reserve = 1 + request.min_nights_per_stop   # drive day + stay at target
    effective_days = days_remaining - reserve
    one_more_stop = 1 + request.min_nights_per_stop

    must_complete  = effective_days <= 0
    could_complete = 0 < effective_days <= one_more_stop and len(segment_stops) >= 1

    return {
        "days_remaining": days_remaining,
        "must_complete": must_complete,
        "route_could_be_complete": could_complete or must_complete,
    }


def _calc_skip_bonus(days_remaining: int, request: "TravelRequest") -> int:
    """How many extra nights the target gets when skipping all remaining intermediate stops.
    days_remaining - 1 drive day, bounded by max_nights_per_stop."""
    bonus = max(0, days_remaining - 1)
    return min(bonus, request.max_nights_per_stop)



def _advance_to_next_leg(job: dict, request: TravelRequest) -> dict:
    """Advance job to the next leg, resetting per-leg state. Mirrors orchestrator pattern."""
    new_idx = job["leg_index"] + 1
    job["leg_index"] = new_idx
    job["current_leg_mode"] = request.legs[new_idx].mode if new_idx < len(request.legs) else None
    job["segment_index"] = 0
    job["segment_budget"] = _calc_leg_segment_budget(request, new_idx) if new_idx < len(request.legs) else 0
    job["segment_stops"] = []
    job["region_plan"] = None
    job["region_plan_confirmed"] = False
    job["explore_segment_budgets"] = []
    job["explore_regions"] = []
    return job


async def _start_leg_route_building(job: dict, job_id: str, request: TravelRequest, extra_instructions: str = "") -> dict:
    """Start transit-mode route building for the current leg. Returns response dict."""
    from agents.stop_options_finder import StopOptionsFinderAgent

    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    segment_target = (
        leg.via_points[0].location if leg.via_points else leg.end_location
    )
    stops_in_segment = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))
    route_geo = await _calc_route_geometry_cached(
        job, job_id, leg.start_location, segment_target,
        stops_in_segment, request.max_drive_hours_per_day,
        origin_location=leg.start_location,
        proximity_origin_pct=request.proximity_origin_pct,
        proximity_target_pct=request.proximity_target_pct,
    )

    agent = StopOptionsFinderAgent(request, job_id)
    options, map_anchors, estimated_total, route_complete = \
        await _find_and_stream_options(
            agent=agent,
            job_id=job_id,
            selected_stops=job["selected_stops"],
            stop_number=job["stop_counter"] + 1,
            days_remaining=job["segment_budget"],
            route_could_be_complete=False,
            segment_target=segment_target,
            segment_index=0,
            segment_count=len(leg.via_points) + 1,
            prev_location=leg.start_location,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=route_geo,
            extra_instructions=extra_instructions,
        )

    job["current_options"] = options
    job["route_could_be_complete"] = route_complete
    save_job(job_id, job)

    n_segments = len(leg.via_points) + 1
    route_status = _calc_route_status(request, [], job["segment_budget"], n_segments == 1)

    return {
        "options": options,
        "meta": {
            "stop_number": job["stop_counter"] + 1,
            "days_remaining": route_status["days_remaining"],
            "estimated_total_stops": estimated_total,
            "route_could_be_complete": route_status["route_could_be_complete"],
            "must_complete": route_status["must_complete"],
            "segment_index": 0,
            "segment_count": n_segments,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
            "skip_nights_bonus": _calc_skip_bonus(route_status["days_remaining"], request),
            "leg_index": leg_index,
            "total_legs": len(request.legs),
            "leg_mode": leg.mode,
        },
        "leg_advanced": True,
    }


async def _start_explore_leg(job: dict, job_id: str, request: TravelRequest) -> dict:
    """Start explore-mode leg: runs RegionPlannerAgent, returns region plan."""
    from agents.region_planner import RegionPlannerAgent

    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    description = leg.explore_description or "Region erkunden"

    agent = RegionPlannerAgent(request, job_id)
    region_plan = await agent.plan(description=description, leg_index=leg_index)

    job["region_plan"] = region_plan.model_dump()
    job["status"] = "awaiting_region_confirmation"
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_plan_ready", None,
        {"regions": [r.model_dump() for r in region_plan.regions],
         "summary": region_plan.summary,
         "leg_id": leg.leg_id}
    )

    return {
        "options": [],
        "meta": {
            "leg_index": leg_index,
            "total_legs": len(request.legs),
            "leg_mode": leg.mode,
            "leg_id": leg.leg_id,
        },
        "explore_pending": True,
        "region_plan": region_plan.model_dump(),
        "leg_advanced": True,
    }


def _leg_meta(request: TravelRequest, leg_index: int) -> dict:
    """Returns leg_index, total_legs, leg_mode fields for meta responses."""
    return {
        "leg_index": leg_index,
        "total_legs": len(request.legs),
        "leg_mode": request.legs[leg_index].mode if leg_index < len(request.legs) else None,
    }


def _calc_budget_state(request: TravelRequest, selected_stops: list,
                       selected_accommodations: list) -> dict:
    """45% of total budget → accommodation."""
    acc_budget = request.budget_chf * (get_setting("budget.accommodation_pct") / 100.0)
    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
    spent = sum(a.get("option", {}).get("total_price_chf", 0) for a in selected_accommodations)
    remaining = acc_budget - spent
    avg_per_night = spent / max(1, sum(
        s.get("nights", 1) for a in selected_accommodations
        for s in [next((x for x in selected_stops if x.get("id") == a.get("stop_id")), {})]
    ))
    return {
        "total_budget_chf": request.budget_chf,
        "accommodation_budget_chf": acc_budget,
        "spent_chf": spent,
        "remaining_chf": remaining,
        "nights_confirmed": sum(
            s.get("nights", 1) for a in selected_accommodations
            for s in [next((x for x in selected_stops if x.get("id") == a.get("stop_id")), {})]
        ),
        "total_nights": total_nights,
        "avg_per_night_chf": round(avg_per_night, 2) if selected_accommodations else 0,
        "selected_count": len(selected_accommodations),
        "total_stops": len(selected_stops),
    }


def _new_job(job_id: str, request: TravelRequest) -> dict:
    return {
        "status": "building_route",
        "request": request.model_dump(mode="json"),
        "selected_stops": [],
        "current_options": [],
        "route_could_be_complete": False,
        "stop_counter": 0,

        # Leg tracking
        "leg_index": 0,
        "current_leg_mode": request.legs[0].mode,

        # Transit leg state (reset on each leg transition)
        "segment_index": 0,
        "segment_budget": _calc_leg_segment_budget(request, 0),
        "segment_stops": [],

        # Explore/Region leg state (reset on each explore leg transition)
        "region_plan": None,           # RegionPlan dict after planning
        "region_plan_confirmed": False, # True after user confirms
        "explore_segment_budgets": [], # Pro-Region-Budget für Explore-Legs
        "explore_regions": [],         # Region-Metadaten für StopFinder-Kontext

        # Accommodation (unchanged)
        "selected_accommodations": [],
        "current_acc_options": [],
        "accommodation_index": 0,
        "prefetched_accommodations": {},
        "all_accommodation_options": {},
        "all_accommodations_loaded": False,

        # Route geometry cache — keys prefixed "leg{N}_" to scope per leg
        "route_geometry_cache": {},

        "result": None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Request model for recompute endpoint
# ---------------------------------------------------------------------------

class RecomputeRequest(BaseModel):
    extra_instructions: str = ""


# ---------------------------------------------------------------------------
# Haversine distance helper
# ---------------------------------------------------------------------------

def _haversine_km(c1: tuple, c2: tuple) -> float:
    """Great-circle distance in km between two (lat, lon) tuples."""
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Route geometry helper — total distance for a segment
# ---------------------------------------------------------------------------

async def _calc_route_geometry(
    from_location: str,
    to_location: str,
    stops_remaining: int,
    max_drive_hours: float,
    origin_location: str = "",
    proximity_origin_pct: int = 10,
    proximity_target_pct: int = 15,
) -> dict:
    """
    Geocodes from/to in parallel via Google, queries Google Directions for the
    full segment distance, then calculates the ideal per-etappe distance given
    stops_remaining. Returns a dict consumed by StopOptionsFinderAgent.find_options().
    """
    from_result, to_result = await asyncio.gather(
        geocode_google(from_location),
        geocode_google(to_location),
    )

    if not from_result or not to_result:
        return {}

    from_coords = (from_result[0], from_result[1])
    to_coords = (to_result[0], to_result[1])
    from_place_id = from_result[2]
    to_place_id = to_result[2]

    total_hours, total_km, geometry_str = await google_directions(from_location, to_location)
    if total_km <= 0:
        return {}

    n = max(1, stops_remaining)
    # Divide by (n+1) so the stop sits BETWEEN start and target, not AT the target.
    # E.g. 200km with 1 stop → ideal_km = 100km (midpoint), not 200km (target).
    ideal_km = total_km / (n + 1)
    ideal_hours = total_hours / (n + 1)

    result = {
        "segment_total_km": total_km,
        "segment_total_hours": total_hours,
        "stops_remaining": n,
        "ideal_km_from_prev": ideal_km,
        "ideal_hours_from_prev": min(ideal_hours, max_drive_hours),
        "min_km_from_origin": max(50.0, total_km * proximity_origin_pct / 100) if proximity_origin_pct > 0 else 0.0,
        "min_km_from_target": max(50.0, total_km * proximity_target_pct / 100) if proximity_target_pct > 0 else 0.0,
        "origin_location": origin_location or from_location,
        # Cache coords so _find_and_stream_options can skip re-geocoding
        "_from_coords": from_coords,
        "_to_coords": to_coords,
        "_from_place_id": from_place_id,
        "_to_place_id": to_place_id,
    }

    # Corridor data for transit routes (not Rundreise)
    if geometry_str:
        route_points = decode_polyline5(geometry_str)
        if route_points:
            result["_route_decoded"] = route_points
            # Search corridor: from ideal_km*0.5 to ideal_km*1.3
            search_from_km = ideal_km * 0.5
            search_to_km = min(ideal_km * 1.3, total_km * 0.9)
            if search_to_km > search_from_km:
                result["corridor_target"] = point_along_route(route_points, ideal_km)
                result["corridor_box"] = corridor_bbox(route_points, search_from_km, search_to_km)
                ref_cities = await reference_cities_along_route_google(
                    from_location, to_location, num_points=3,
                )
                if ref_cities:
                    result["corridor_reference_cities"] = ref_cities

    return result


async def _calc_route_geometry_cached(
    job: dict,
    job_id: str,
    from_location: str,
    to_location: str,
    stops_remaining: int,
    max_drive_hours: float,
    origin_location: str = "",
    proximity_origin_pct: int = 10,
    proximity_target_pct: int = 15,
) -> dict:
    """Cache wrapper around _calc_route_geometry — keyed by leg + segment + stops count."""
    leg_index = job.get("leg_index", 0)
    cache_key = f"leg{leg_index}_{from_location}|{to_location}|{stops_remaining}"
    cache = job.setdefault("route_geometry_cache", {})
    if cache_key in cache:
        return cache[cache_key]

    result = await _calc_route_geometry(
        from_location, to_location, stops_remaining, max_drive_hours, origin_location,
        proximity_origin_pct, proximity_target_pct,
    )
    if result:
        cache[cache_key] = result
        save_job(job_id, job)
    return result


# ---------------------------------------------------------------------------
# Google Directions enrichment helper
# ---------------------------------------------------------------------------

async def _enrich_options_with_google(
    options: list, prev_location: str, segment_target: str = "",
    max_drive_hours: float = 0.0,
) -> tuple[list, Optional[dict]]:
    """Geocode all places via Google in parallel, then run Google Directions in
    parallel. Agent-supplied lat/lon are used as fallback when geocoding returns
    nothing. Sets place_id on each option. Sets drives_over_limit=True on options
    that exceed max_drive_hours (if given). Returns (enriched_options, map_anchors)."""

    # Build ordered list of places: [prev, (target,) opt0, opt1, opt2]
    opt_places = [f"{o.get('region', '')}, {o.get('country', '')}" for o in options]
    all_places = [prev_location]
    if segment_target:
        all_places.append(segment_target)
    all_places.extend(opt_places)

    # Phase 1: parallel geocoding (no rate limit needed for Google)
    coords_results = await asyncio.gather(
        *[geocode_google(p) for p in all_places]
    )

    prev_result = coords_results[0]
    prev_coords = (prev_result[0], prev_result[1]) if prev_result else None
    prev_place_id = prev_result[2] if prev_result else None

    if segment_target:
        target_result = coords_results[1]
        target_coords = (target_result[0], target_result[1]) if target_result else None
        target_place_id = target_result[2] if target_result else None
        opt_start = 2
    else:
        target_coords = None
        target_place_id = None
        opt_start = 1

    # Phase 2: parallel Google Directions calls
    async def _directions_for_opt(i: int, opt: dict):
        geo_result = coords_results[opt_start + i]
        agent_lat = opt.get("lat")
        agent_lon = opt.get("lon")
        agent_coords = (agent_lat, agent_lon) if agent_lat and agent_lon else None
        coords = (geo_result[0], geo_result[1]) if geo_result else agent_coords
        place_id = geo_result[2] if geo_result else None
        if not coords:
            return i, None, None, None, None
        place = opt_places[i]
        maps_url = build_maps_url([prev_location, place])
        if prev_coords:
            hours, km = await google_directions_simple(prev_location, place)
            return i, coords, maps_url, (hours, km), place_id
        return i, coords, maps_url, None, place_id

    dir_results = await asyncio.gather(*[_directions_for_opt(i, opt) for i, opt in enumerate(options)])

    for i, opt in enumerate(options):
        _, coords, maps_url, route_data, place_id = dir_results[i]
        if coords:
            opt["lat"] = coords[0]
            opt["lon"] = coords[1]
            opt["maps_url"] = maps_url
            if place_id:
                opt["place_id"] = place_id
            if route_data:
                hours, km = route_data
                if hours > 0:
                    opt["drive_hours"] = hours
                    opt["drive_km"] = km
        if max_drive_hours > 0:
            opt["drives_over_limit"] = opt.get("drive_hours", 0) > max_drive_hours

    map_anchors = {
        "prev_lat": prev_coords[0] if prev_coords else None,
        "prev_lon": prev_coords[1] if prev_coords else None,
        "prev_label": prev_location,
        "prev_place_id": prev_place_id,
        "target_lat": target_coords[0] if target_coords else None,
        "target_lon": target_coords[1] if target_coords else None,
        "target_label": segment_target,
        "target_place_id": target_place_id,
    }
    return options, map_anchors


# ---------------------------------------------------------------------------
# Streaming helper: Claude → Google enrichment → SSE events per option
# ---------------------------------------------------------------------------

async def _find_and_stream_options(
    agent,
    job_id: str,
    selected_stops: list,
    stop_number: int,
    days_remaining: int,
    route_could_be_complete: bool,
    segment_target: str,
    segment_index: int,
    segment_count: int,
    prev_location: str,
    max_drive_hours: float,
    route_geometry: dict,
    extra_instructions: str = "",
) -> tuple[list, dict, int, bool]:
    """
    Runs StopOptionsFinder in streaming mode. Each option is individually
    Google-enriched and pushed as a 'route_option_ready' SSE event as soon as
    it's available. Options too close to the trip origin or segment target are
    silently filtered; if < 3 valid options remain, the agent is retried once.
    Returns (enriched_options, map_anchors, estimated_total_stops,
    route_could_be_complete) once all 3 options are done.
    """
    geo = route_geometry or {}
    min_km_from_origin: float = geo.get("min_km_from_origin", 0.0)
    min_km_from_target: float = geo.get("min_km_from_target", 0.0)
    origin_location: str = geo.get("origin_location", "")

    # Reuse coords from route_geometry if available, otherwise geocode
    cached_from = geo.get("_from_coords")
    cached_to = geo.get("_to_coords")
    cached_from_place_id = geo.get("_from_place_id")
    cached_to_place_id = geo.get("_to_place_id")

    async def _none_coro():
        return None

    if cached_from and cached_to:
        # Coords already computed by _calc_route_geometry — skip re-geocoding
        prev_coords = cached_from
        target_coords = cached_to
        origin_coords = cached_from
        prev_place_id = cached_from_place_id
        target_place_id = cached_to_place_id
    elif origin_location and origin_location != prev_location and min_km_from_origin > 0:
        prev_result, target_result, origin_result = await asyncio.gather(
            geocode_google(prev_location),
            geocode_google(segment_target) if segment_target else _none_coro(),
            geocode_google(origin_location),
        )
        prev_coords = (prev_result[0], prev_result[1]) if prev_result else None
        target_coords = (target_result[0], target_result[1]) if target_result else None
        origin_coords = (origin_result[0], origin_result[1]) if origin_result else None
        prev_place_id = prev_result[2] if prev_result else None
        target_place_id = target_result[2] if target_result else None
    else:
        prev_result, target_result = await asyncio.gather(
            geocode_google(prev_location),
            geocode_google(segment_target) if segment_target else _none_coro(),
        )
        prev_coords = (prev_result[0], prev_result[1]) if prev_result else None
        target_coords = (target_result[0], target_result[1]) if target_result else None
        origin_coords = prev_coords  # origin == prev for first stop or no-origin case
        prev_place_id = prev_result[2] if prev_result else None
        target_place_id = target_result[2] if target_result else None

    await debug_logger.log(
        LogLevel.INFO,
        f"Route-Optionen: {prev_location} → {segment_target} (Stop #{stop_number}, {days_remaining} Tage)",
        job_id=job_id, agent="StopOptionsFinder",
    )
    await debug_logger.log(
        LogLevel.DEBUG,
        f"  Geocoding: prev={prev_location} → {prev_coords}, target={segment_target} → {target_coords}",
        job_id=job_id, agent="StopOptionsFinder",
    )

    map_anchors = {
        "prev_lat": prev_coords[0] if prev_coords else None,
        "prev_lon": prev_coords[1] if prev_coords else None,
        "prev_label": prev_location,
        "prev_place_id": prev_place_id,
        "target_lat": target_coords[0] if target_coords else None,
        "target_lon": target_coords[1] if target_coords else None,
        "target_label": segment_target,
        "target_place_id": target_place_id,
    }

    async def _run_one_pass(extra_instr: str) -> tuple[list, int, bool]:
        """Stream one agent call, enrich options, return (valid_options, estimated_total, route_complete)."""
        raw_options: list = []
        estimated: int = 4
        r_complete: bool = route_could_be_complete

        async for item in agent.find_options_streaming(
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=days_remaining,
            route_could_be_complete=route_could_be_complete,
            segment_target=segment_target,
            segment_index=segment_index,
            segment_count=segment_count,
            extra_instructions=extra_instr,
            route_geometry=route_geometry,
        ):
            if "_all_options" in item:
                estimated = item.get("estimated_total_stops", 4)
                r_complete = item.get("route_could_be_complete", False)
                if not raw_options and item.get("_all_options"):
                    raw_options = item["_all_options"]
                continue
            raw_options.append(item)

        # Enrich options in parallel (geocode + Google Directions + proximity filter)
        async def _enrich_one(i: int, opt: dict) -> Optional[dict]:
            place = f"{opt.get('region', '')}, {opt.get('country', '')}"
            geo_result = await geocode_google(place)
            agent_lat = opt.get("lat")
            agent_lon = opt.get("lon")
            agent_coords = (agent_lat, agent_lon) if agent_lat and agent_lon else None
            coords = (geo_result[0], geo_result[1]) if geo_result else agent_coords

            if not coords:
                return None

            opt["lat"] = coords[0]
            opt["lon"] = coords[1]
            if geo_result:
                opt["place_id"] = geo_result[2]
            opt["maps_url"] = build_maps_url([prev_location, place])

            if prev_coords:
                hours, km = await google_directions_simple(prev_location, place)
                if hours > 0:
                    opt["drive_hours"] = hours
                    opt["drive_km"] = km

            if max_drive_hours > 0:
                opt["drives_over_limit"] = opt.get("drive_hours", 0) > max_drive_hours

            # Proximity check: too close to trip origin?
            if origin_coords and min_km_from_origin > 0:
                d_origin = _haversine_km(origin_coords, coords)
                if d_origin < min_km_from_origin:
                    await debug_logger.log(
                        LogLevel.DEBUG,
                        f"  Verworfen (zu nahe am Startpunkt {origin_location}: {d_origin:.0f} km < {min_km_from_origin:.0f} km): {place}",
                        job_id=job_id, agent="StopOptionsFinder",
                    )
                    return None

            # Proximity check: too close to segment target?
            if target_coords and min_km_from_target > 0:
                d_target = _haversine_km(coords, target_coords)
                if d_target < min_km_from_target:
                    await debug_logger.log(
                        LogLevel.DEBUG,
                        f"  Verworfen (zu nahe am Ziel {segment_target}: {d_target:.0f} km < {min_km_from_target:.0f} km): {place}",
                        job_id=job_id, agent="StopOptionsFinder",
                    )
                    return None

            # Overshoot check: stop must not be further from segment start than the target
            segment_start_coords = geo.get("_from_coords")
            if segment_start_coords and target_coords and not geo.get("rundreise_mode", False):
                d_start_to_target = _haversine_km(segment_start_coords, target_coords)
                d_start_to_stop = _haversine_km(segment_start_coords, coords)
                if d_start_to_stop > d_start_to_target * 1.15:  # 15% tolerance
                    await debug_logger.log(
                        LogLevel.DEBUG,
                        f"  Verworfen (Overshoot: {d_start_to_stop:.0f} km > {d_start_to_target:.0f} km): {place}",
                        job_id=job_id, agent="StopOptionsFinder",
                    )
                    return None

            return opt

        results = await asyncio.gather(*[_enrich_one(i, opt) for i, opt in enumerate(raw_options)])
        valid: list = []
        for opt in results:
            if opt is not None:
                limit_flag = " ⚠ LIMIT" if opt.get("drives_over_limit") else ""
                place = f"{opt.get('region', '')}, {opt.get('country', '')}"
                await debug_logger.log(
                    LogLevel.SUCCESS,
                    f"  [{len(valid) + 1}/3] {opt.get('option_type', '?'):8} {place}: "
                    f"{opt.get('drive_hours', '?')}h / {opt.get('drive_km', '?')} km{limit_flag}",
                    job_id=job_id, agent="StopOptionsFinder",
                )
                valid.append(opt)

        return valid, estimated, r_complete

    # First pass
    enriched_options, estimated_total_stops, final_route_could_be_complete = await _run_one_pass(extra_instructions)

    # Retry only if 1–2 valid options (worth filling up)
    if 0 < len(enriched_options) < 3 and min_km_from_origin > 0:
        retry_hint = (
            f"WICHTIG: Letzte Optionen zu nahe am Start/Ziel. "
            f"Wähle Orte die mindestens {min_km_from_origin:.0f} km vom Startpunkt {origin_location} "
            f"und mindestens {min_km_from_target:.0f} km vom Ziel {segment_target} entfernt liegen."
        )
        combined = (extra_instructions + "\n" + retry_hint).strip() if extra_instructions else retry_hint
        await debug_logger.log(
            LogLevel.INFO,
            f"Nur {len(enriched_options)} gültige Option(en) — Retry mit Abstandshinweis",
            job_id=job_id, agent="StopOptionsFinder",
        )
        retry_options, estimated_total_stops, final_route_could_be_complete = await _run_one_pass(combined)
        # Merge: keep original valid options + fill up from retry
        existing_regions = {o.get("region") for o in enriched_options}
        for opt in retry_options:
            if opt.get("region") not in existing_regions:
                enriched_options.append(opt)
                existing_regions.add(opt.get("region"))
            if len(enriched_options) >= 3:
                break

    if len(enriched_options) == 0:
        # Keine gültigen Optionen — Frontend zeigt Korridor + Eingabefeld
        await debug_logger.log(
            LogLevel.WARNING,
            f"0 gültige Optionen — Frontend zeigt Korridor für Benutzerführung",
            job_id=job_id,
        )
        await debug_logger.push_event(
            job_id, "route_options_done", None,
            {
                "options": [],
                "map_anchors": map_anchors,
                "estimated_total_stops": 0,
                "route_could_be_complete": False,
                "no_stops_found": True,
                "corridor": {
                    "start": prev_location,
                    "end": segment_target,
                    "start_coords": prev_coords,
                    "end_coords": target_coords,
                },
            },
        )
        return [], map_anchors, 0, False

    # Emit SSE events for all valid options
    for option_index, opt in enumerate(enriched_options):
        await debug_logger.push_event(
            job_id,
            "route_option_ready",
            agent_id="StopOptionsFinder",
            data={
                "option": opt,
                "option_index": option_index,
                "map_anchors": map_anchors,
            },
        )

    await debug_logger.log(
        LogLevel.SUCCESS,
        f"Alle {len(enriched_options)} Optionen bereit → SSE route_options_done",
        job_id=job_id, agent="StopOptionsFinder",
    )

    # Signal that all options are done
    await debug_logger.push_event(
        job_id,
        "route_options_done",
        agent_id="StopOptionsFinder",
        data={
            "options": enriched_options,
            "map_anchors": map_anchors,
            "estimated_total_stops": estimated_total_stops,
            "route_could_be_complete": final_route_could_be_complete,
        },
    )

    return enriched_options, map_anchors, estimated_total_stops, final_route_could_be_complete


# ---------------------------------------------------------------------------
# POST /api/init-job  — create job_id before SSE is opened
# The frontend calls this first, opens SSE, then calls plan-trip with the id.
# ---------------------------------------------------------------------------

@app.post("/api/init-job")
async def init_job(request: TravelRequest):
    job_id = uuid.uuid4().hex
    job = _new_job(job_id, request)
    save_job(job_id, job)
    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# POST /api/plan-trip
# ---------------------------------------------------------------------------

@app.post("/api/plan-trip")
async def plan_trip(request: TravelRequest, job_id: Optional[str] = None):
    from agents.stop_options_finder import StopOptionsFinderAgent

    if job_id and _JOB_ID_RE.match(job_id):
        # Reuse pre-initialised job (SSE may already be open)
        job = get_job(job_id)
        # Overwrite request in case it changed (shouldn't differ, but be safe)
        job["request"] = request.model_dump(mode="json")
    else:
        job_id = uuid.uuid4().hex
        job = _new_job(job_id, request)
    save_job(job_id, job)

    await debug_logger.log(LogLevel.INFO, f"Neue Reise: {request.start_location} → {request.main_destination}",
                           job_id=job_id)

    # Determine segment target using current leg's via_points and end_location
    leg = request.legs[job["leg_index"]]

    # Explore-Modus: Zone analysieren statt Transit-Route planen
    if leg.mode == "explore":
        result = await _start_explore_leg(job, job_id, request)
        result["job_id"] = job_id
        result["status"] = "awaiting_zone_guidance"
        return result

    segment_target = (
        leg.via_points[0].location if leg.via_points else leg.end_location
    )

    # Estimate how many stops fit in this segment based on days/nights budget
    stops_in_segment = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))
    route_geo = await _calc_route_geometry_cached(
        job, job_id, leg.start_location, segment_target,
        stops_in_segment, request.max_drive_hours_per_day,
        origin_location=leg.start_location,
        proximity_origin_pct=request.proximity_origin_pct,
        proximity_target_pct=request.proximity_target_pct,
    )

    if not route_geo:
        await debug_logger.log(
            LogLevel.WARNING,
            f"route_geo leer — Geocoding/Google Directions fehlgeschlagen für {request.start_location} → {segment_target}",
            job_id=job_id,
        )
    else:
        await debug_logger.log(
            LogLevel.DEBUG,
            f"route_geo: {route_geo.get('segment_total_km', '?')} km / {route_geo.get('segment_total_hours', '?')}h, ideal/etappe: {route_geo.get('ideal_km_from_prev', '?')} km",
            job_id=job_id,
        )

    agent = StopOptionsFinderAgent(request, job_id)
    try:
        options, map_anchors, estimated_total_stops, route_could_be_complete = \
            await _find_and_stream_options(
                agent=agent,
                job_id=job_id,
                selected_stops=[],
                stop_number=1,
                days_remaining=job["segment_budget"],
                route_could_be_complete=False,
                segment_target=segment_target,
                segment_index=0,
                segment_count=len(leg.via_points) + 1,
                prev_location=leg.start_location,
                max_drive_hours=request.max_drive_hours_per_day,
                route_geometry=route_geo,
            )
    except Exception as exc:
        import traceback
        await debug_logger.log(
            LogLevel.ERROR,
            f"Fehler in plan_trip/_find_and_stream_options: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            job_id=job_id,
        )
        raise

    job["current_options"] = options
    job["route_could_be_complete"] = route_could_be_complete
    save_job(job_id, job)

    is_last_segment = len(leg.via_points) == 0
    route_status = _calc_route_status(request, [], job["segment_budget"], is_last_segment)

    return {
        "job_id": job_id,
        "status": "building_route",
        "options": options,
        "meta": {
            "stop_number": 1,
            "days_remaining": route_status["days_remaining"],
            "estimated_total_stops": estimated_total_stops,
            "route_could_be_complete": route_status["route_could_be_complete"],
            "must_complete": route_status["must_complete"],
            "segment_index": 0,
            "segment_count": len(leg.via_points) + 1,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
            "skip_nights_bonus": _calc_skip_bonus(route_status["days_remaining"], request),
            **_leg_meta(request, job["leg_index"]),
        },
    }



# ---------------------------------------------------------------------------
# POST /api/select-stop/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/select-stop/{job_id}")
async def select_stop(job_id: str, body: StopSelectRequest):
    from agents.stop_options_finder import StopOptionsFinderAgent

    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    leg = request.legs[job["leg_index"]]

    options = job.get("current_options", [])
    if body.option_index >= len(options):
        raise HTTPException(status_code=400, detail="Ungültiger option_index")

    selected = options[body.option_index]
    job["stop_counter"] += 1
    selected["id"] = job["stop_counter"]
    job["selected_stops"].append(selected)
    job["segment_stops"].append(selected)

    seg_idx = job["segment_index"]
    n_segments = len(leg.via_points) + 1
    is_last_segment = seg_idx == n_segments - 1
    route_status = _calc_route_status(
        request, job["segment_stops"], job["segment_budget"], is_last_segment
    )

    via_point_added = None
    segment_complete = False

    if route_status["must_complete"] and not is_last_segment:
        via_point = leg.via_points[seg_idx]
        is_explore = bool(job.get("explore_regions"))

        # Explore: gewählter Stop bekommt Region-Nächte
        if is_explore and job.get("explore_segment_budgets"):
            selected["nights"] = job["explore_segment_budgets"][seg_idx] - 1  # budget minus 1 drive day

        if not is_explore:
            # Transit: via-point Stop einfügen (bestehende Logik)
            job["stop_counter"] += 1
            via_stop = {
                "id": job["stop_counter"],
                "option_type": "via_point",
                "region": via_point.location,
                "country": "XX",
                "drive_hours": 1.0,
                "nights": request.min_nights_per_stop,
                "highlights": [],
                "teaser": f"Fixpunkt: {via_point.location}",
                "is_fixed": True,
            }
            job["selected_stops"].append(via_stop)
            via_point_added = via_stop

        segment_complete = True

        # Move to next segment
        job["segment_index"] += 1
        job["segment_stops"] = []

        # Explore: Budget aus explore_segment_budgets, sonst normal berechnen
        if job.get("explore_segment_budgets") and job["segment_index"] < len(job["explore_segment_budgets"]):
            job["segment_budget"] = job["explore_segment_budgets"][job["segment_index"]]
        else:
            job["segment_budget"] = _calc_leg_segment_budget(request, job["leg_index"])

        seg_idx = job["segment_index"]
        is_last_segment = seg_idx == n_segments - 1

        segment_target = (
            leg.via_points[seg_idx].location
            if seg_idx < len(leg.via_points)
            else leg.end_location
        )

        stops_in_new_seg = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))

        # Explore: prev_loc ist der gewählte Stop, nicht der via_point
        if is_explore:
            prev_loc = selected.get("region", via_point.location)
            # Extra-Instructions für nächste Region
            new_seg = job["segment_index"]
            if new_seg < len(job.get("explore_regions", [])):
                er = job["explore_regions"][new_seg]
                extra_instr = f"Suche Städte/Orte IN der Region {er['name']}. Highlights: {', '.join(er.get('highlights', []))}."
            else:
                extra_instr = ""
        else:
            prev_loc = via_point.location
            extra_instr = ""

        next_geo = await _calc_route_geometry_cached(
            job, job_id, prev_loc, segment_target, stops_in_new_seg, request.max_drive_hours_per_day,
            origin_location=leg.start_location,
            proximity_origin_pct=request.proximity_origin_pct,
            proximity_target_pct=request.proximity_target_pct,
        )

        agent = StopOptionsFinderAgent(request, job_id)
        next_options, map_anchors, estimated_total, route_complete = \
            await _find_and_stream_options(
                agent=agent,
                job_id=job_id,
                selected_stops=job["selected_stops"],
                stop_number=job["stop_counter"] + 1,
                days_remaining=job["segment_budget"],
                route_could_be_complete=False,
                segment_target=segment_target,
                segment_index=seg_idx,
                segment_count=n_segments,
                prev_location=prev_loc,
                max_drive_hours=request.max_drive_hours_per_day,
                route_geometry=next_geo,
                extra_instructions=extra_instr,
            )
        job["current_options"] = next_options
        job["route_could_be_complete"] = route_complete
        save_job(job_id, job)

        new_status = _calc_route_status(request, job["segment_stops"], job["segment_budget"], is_last_segment)
        return {
            "job_id": job_id,
            "selected_stop": selected,
            "selected_stops": job["selected_stops"],
            "options": next_options,
            "segment_complete": segment_complete,
            "via_point_added": via_point_added,
            "meta": {
                "stop_number": job["stop_counter"] + 1,
                "days_remaining": new_status["days_remaining"],
                "estimated_total_stops": estimated_total,
                "route_could_be_complete": new_status["route_could_be_complete"],
                "must_complete": new_status["must_complete"],
                "segment_index": job["segment_index"],
                "segment_count": n_segments,
                "segment_target": segment_target,
                "map_anchors": map_anchors,
                "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
                **_leg_meta(request, job["leg_index"]),
            },
        }

    elif route_status["must_complete"] and is_last_segment:
        # Current leg's last segment is complete
        leg_index = job["leg_index"]
        total_legs = len(request.legs)

        # Emit leg_complete SSE event
        await debug_logger.push_event(
            job_id, "leg_complete", None,
            {"leg_id": leg.leg_id, "leg_index": leg_index, "mode": leg.mode}
        )

        if leg_index < total_legs - 1:
            # More legs remain — advance to next leg
            _advance_to_next_leg(job, request)
            save_job(job_id, job)

            next_leg = request.legs[job["leg_index"]]
            if next_leg.mode == "explore":
                result = await _start_explore_leg(job, job_id, request)
            else:
                result = await _start_leg_route_building(job, job_id, request)

            result["job_id"] = job_id
            result["selected_stop"] = selected
            result["selected_stops"] = job["selected_stops"]
            return result
        else:
            # Last leg — route fully complete
            job["current_options"] = []
            job["route_could_be_complete"] = True
            save_job(job_id, job)
            return {
                "job_id": job_id,
                "selected_stop": selected,
                "selected_stops": job["selected_stops"],
                "options": [],
                "meta": {
                    "stop_number": job["stop_counter"] + 1,
                    "days_remaining": 0,
                    "estimated_total_stops": len(job["selected_stops"]),
                    "route_could_be_complete": True,
                    "must_complete": True,
                    "segment_index": seg_idx,
                    "segment_count": n_segments,
                    "segment_target": leg.end_location,
                    **_leg_meta(request, leg_index),
                },
            }

    else:
        # Continue building route
        segment_target = (
            leg.via_points[seg_idx].location
            if seg_idx < len(leg.via_points)
            else leg.end_location
        )
        prev_loc_else = selected.get("region", leg.start_location)
        stops_left = max(1, route_status["days_remaining"] // (1 + request.min_nights_per_stop))
        next_geo = await _calc_route_geometry_cached(
            job, job_id, prev_loc_else, segment_target, stops_left, request.max_drive_hours_per_day,
            origin_location=leg.start_location,
            proximity_origin_pct=request.proximity_origin_pct,
            proximity_target_pct=request.proximity_target_pct,
        )

        agent = StopOptionsFinderAgent(request, job_id)
        next_options, map_anchors, estimated_total, route_complete = \
            await _find_and_stream_options(
                agent=agent,
                job_id=job_id,
                selected_stops=job["selected_stops"],
                stop_number=job["stop_counter"] + 1,
                days_remaining=route_status["days_remaining"],
                route_could_be_complete=route_status["route_could_be_complete"],
                segment_target=segment_target,
                segment_index=seg_idx,
                segment_count=n_segments,
                prev_location=prev_loc_else,
                max_drive_hours=request.max_drive_hours_per_day,
                route_geometry=next_geo,
            )
        job["current_options"] = next_options
        job["route_could_be_complete"] = route_complete
        save_job(job_id, job)

        new_status = _calc_route_status(request, job["segment_stops"], job["segment_budget"], is_last_segment)
        return {
            "job_id": job_id,
            "selected_stop": selected,
            "selected_stops": job["selected_stops"],
            "options": next_options,
            "meta": {
                "stop_number": job["stop_counter"] + 1,
                "days_remaining": new_status["days_remaining"],
                "estimated_total_stops": estimated_total,
                "route_could_be_complete": new_status["route_could_be_complete"],
                "must_complete": new_status["must_complete"],
                "segment_index": seg_idx,
                "segment_count": n_segments,
                "segment_target": segment_target,
                "map_anchors": map_anchors,
                "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
                **_leg_meta(request, job["leg_index"]),
            },
        }


# ---------------------------------------------------------------------------
# POST /api/recompute-options/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/recompute-options/{job_id}")
async def recompute_options(job_id: str, body: RecomputeRequest):
    from agents.stop_options_finder import StopOptionsFinderAgent

    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    leg = request.legs[job.get("leg_index", 0)]

    seg_idx = job.get("segment_index", 0)
    n_segments = len(leg.via_points) + 1
    segment_target = (
        leg.via_points[seg_idx].location
        if seg_idx < len(leg.via_points)
        else leg.end_location
    )

    selected_stops = job.get("selected_stops", [])
    stop_number = job.get("stop_counter", 0) + 1
    route_status = _calc_route_status(
        request, job.get("segment_stops", []), job.get("segment_budget", request.total_days),
        seg_idx == n_segments - 1
    )

    prev_location = selected_stops[-1]["region"] if selected_stops else leg.start_location
    stops_left_rc = max(1, route_status["days_remaining"] // (1 + request.min_nights_per_stop))
    recompute_geo = await _calc_route_geometry_cached(
        job, job_id, prev_location, segment_target, stops_left_rc, request.max_drive_hours_per_day,
        origin_location=leg.start_location,
        proximity_origin_pct=request.proximity_origin_pct,
        proximity_target_pct=request.proximity_target_pct,
    )

    agent = StopOptionsFinderAgent(request, job_id)
    options, map_anchors, estimated_total_stops, route_complete = \
        await _find_and_stream_options(
            agent=agent,
            job_id=job_id,
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=route_status["days_remaining"],
            route_could_be_complete=route_status["route_could_be_complete"],
            segment_target=segment_target,
            segment_index=seg_idx,
            segment_count=n_segments,
            prev_location=prev_location,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=recompute_geo,
            extra_instructions=body.extra_instructions,
        )

    job["current_options"] = options
    job["route_could_be_complete"] = route_complete
    save_job(job_id, job)

    return {
        "job_id": job_id,
        "status": "building_route",
        "options": options,
        "meta": {
            "stop_number": stop_number,
            "days_remaining": route_status["days_remaining"],
            "estimated_total_stops": estimated_total_stops,
            "route_could_be_complete": route_status["route_could_be_complete"],
            "must_complete": route_status["must_complete"],
            "segment_index": seg_idx,
            "segment_count": n_segments,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
            "skip_nights_bonus": _calc_skip_bonus(route_status["days_remaining"], request),
            **_leg_meta(request, job["leg_index"]),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/patch-job/{job_id}
# Adjusts job when all options exceed drive limit.
# action="add_days"      → extra_days added to total_days + segment_budget
# action="add_via_point" → inserts a new via-point before current segment target,
#                          splits the segment and recomputes options
# ---------------------------------------------------------------------------

class PatchJobRequest(BaseModel):
    action: str                  # "add_days" | "add_via_point"
    extra_days: int = 2          # used by "add_days"
    via_point_location: str = "" # used by "add_via_point"


@app.post("/api/patch-job/{job_id}")
async def patch_job(job_id: str, body: PatchJobRequest):
    from agents.stop_options_finder import StopOptionsFinderAgent

    job = get_job(job_id)
    req_data = job["request"]

    leg_index = job.get("leg_index", 0)

    if body.action == "add_days":
        # Add days to the current leg's end_date
        legs_list = req_data.get("legs", [])
        if leg_index < len(legs_list):
            leg_data = legs_list[leg_index]
            leg_data["end_date"] = str(
                date.fromisoformat(str(leg_data["end_date"])) +
                timedelta(days=body.extra_days)
            )
            legs_list[leg_index] = leg_data
            req_data["legs"] = legs_list
        job["request"] = req_data
        job["segment_budget"] += body.extra_days

    elif body.action == "add_via_point":
        if not body.via_point_location.strip():
            raise HTTPException(status_code=400, detail="via_point_location darf nicht leer sein")
        seg_idx = job.get("segment_index", 0)
        # Insert the new via-point before the current segment target in the current leg
        legs_list = req_data.get("legs", [])
        if leg_index < len(legs_list):
            leg_data = legs_list[leg_index]
            vp_list = leg_data.get("via_points", [])
            new_vp = {"location": body.via_point_location.strip(), "fixed_date": None, "notes": None}
            vp_list.insert(seg_idx, new_vp)
            leg_data["via_points"] = vp_list
            # Add a day to the leg end_date for the extra stop
            leg_data["end_date"] = str(
                date.fromisoformat(str(leg_data["end_date"])) +
                timedelta(days=1)
            )
            legs_list[leg_index] = leg_data
            req_data["legs"] = legs_list
        job["request"] = req_data
        # Recalculate segment budget for the (now shorter) current segment
        request_tmp = TravelRequest(**req_data)
        job["segment_budget"] = _calc_leg_segment_budget(request_tmp, leg_index)

    else:
        raise HTTPException(status_code=400, detail=f"Unbekannte Aktion: {body.action}")

    save_job(job_id, job)

    # Recompute options with updated job state
    request = TravelRequest(**job["request"])
    leg = request.legs[leg_index]
    seg_idx = job.get("segment_index", 0)
    n_segments = len(leg.via_points) + 1
    segment_target = (
        leg.via_points[seg_idx].location
        if seg_idx < len(leg.via_points)
        else leg.end_location
    )

    selected_stops = job.get("selected_stops", [])
    stop_number = job.get("stop_counter", 0) + 1
    route_status = _calc_route_status(
        request, job.get("segment_stops", []), job["segment_budget"],
        seg_idx == n_segments - 1
    )

    prev_location = selected_stops[-1]["region"] if selected_stops else leg.start_location
    stops_left = max(1, route_status["days_remaining"] // (1 + request.min_nights_per_stop))
    geo = await _calc_route_geometry_cached(
        job, job_id, prev_location, segment_target, stops_left, request.max_drive_hours_per_day,
        origin_location=leg.start_location,
        proximity_origin_pct=request.proximity_origin_pct,
        proximity_target_pct=request.proximity_target_pct,
    )

    agent = StopOptionsFinderAgent(request, job_id)
    options, map_anchors, estimated_total_stops, route_complete = \
        await _find_and_stream_options(
            agent=agent,
            job_id=job_id,
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=route_status["days_remaining"],
            route_could_be_complete=route_status["route_could_be_complete"],
            segment_target=segment_target,
            segment_index=seg_idx,
            segment_count=n_segments,
            prev_location=prev_location,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=geo,
        )
    job["current_options"] = options
    job["route_could_be_complete"] = route_complete
    save_job(job_id, job)

    new_status = _calc_route_status(
        request, job.get("segment_stops", []), job["segment_budget"],
        seg_idx == n_segments - 1
    )
    return {
        "job_id": job_id,
        "status": "building_route",
        "options": options,
        "meta": {
            "stop_number": stop_number,
            "days_remaining": new_status["days_remaining"],
            "estimated_total_stops": estimated_total_stops,
            "route_could_be_complete": new_status["route_could_be_complete"],
            "must_complete": new_status["must_complete"],
            "segment_index": seg_idx,
            "segment_count": n_segments,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
            "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
            "total_days": request.total_days,
            **_leg_meta(request, leg_index),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/confirm-route/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/confirm-route/{job_id}")
async def confirm_route(job_id: str):
    from tasks.prefetch_accommodations import prefetch_accommodations_task

    job = get_job(job_id)
    request = TravelRequest(**job["request"])

    # Guard: all legs must be complete before confirming route
    if job["leg_index"] < len(request.legs) - 1:
        raise HTTPException(status_code=409,
            detail="Nicht alle Etappen abgeschlossen — Route kann noch nicht bestätigt werden")

    selected_stops = job["selected_stops"]

    # Append missing via-points and main destination
    existing_regions = {s.get("region", "").lower() for s in selected_stops}

    for vp in request.via_points:
        if vp.location.lower() not in existing_regions:
            job["stop_counter"] += 1
            selected_stops.append({
                "id": job["stop_counter"],
                "option_type": "via_point",
                "region": vp.location,
                "country": "XX",
                "drive_hours": 1.0,
                "nights": request.min_nights_per_stop,
                "highlights": [],
                "teaser": f"Fixpunkt: {vp.location}",
                "is_fixed": True,
            })
            existing_regions.add(vp.location.lower())

    # Append destination (end_location of last leg) if missing
    last_leg = request.legs[-1]
    dest = last_leg.end_location
    if dest and dest.lower() not in existing_regions:
        total_nights_used = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
        days_left = max(request.min_nights_per_stop, request.total_days - total_nights_used - len(selected_stops))
        job["stop_counter"] += 1
        selected_stops.append({
            "id": job["stop_counter"],
            "option_type": "destination",
            "region": dest,
            "country": "XX",
            "drive_hours": 0,
            "nights": min(days_left, request.max_nights_per_stop),
            "highlights": [],
            "teaser": f"Hauptziel: {dest}",
            "is_fixed": True,
        })
        existing_regions.add(dest.lower())

    # Assign 1-based IDs
    for i, stop in enumerate(selected_stops):
        stop["id"] = i + 1

    job["selected_stops"] = selected_stops
    job["status"] = "loading_accommodations"
    save_job(job_id, job)

    budget_state = _calc_budget_state(request, selected_stops, [])

    return {
        "job_id": job_id,
        "status": "loading_accommodations",
        "selected_stops": selected_stops,
        "budget_state": budget_state,
        "total_stops": len(selected_stops),
    }


# ---------------------------------------------------------------------------
# POST /api/start-accommodations/{job_id}
# Called by frontend AFTER SSE is open, so no events are lost
# ---------------------------------------------------------------------------

@app.post("/api/start-accommodations/{job_id}")
async def start_accommodations(job_id: str):
    job = get_job(job_id)
    if job.get("status") != "loading_accommodations":
        raise HTTPException(status_code=400, detail="Job nicht im Status loading_accommodations")

    _fire_task("prefetch_accommodations", job_id)

    return {"job_id": job_id, "status": "prefetch_started"}


# ---------------------------------------------------------------------------
# POST /api/confirm-accommodations/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/confirm-accommodations/{job_id}")
async def confirm_accommodations(job_id: str, body: dict):
    job = get_job(job_id)
    request = TravelRequest(**job["request"])

    selections = body.get("selections", {})  # {stop_id_str: option_index}
    prefetched = job.get("prefetched_accommodations", {})
    selected_stops = job["selected_stops"]

    selected_accommodations = []
    for stop_id_str, option_idx in selections.items():
        options = prefetched.get(str(stop_id_str), [])
        if options and 0 <= option_idx < len(options):
            selected_accommodations.append({
                "stop_id": int(stop_id_str),
                "option": options[option_idx],
            })

    all_options_by_stop = {
        str(sid): prefetched.get(str(sid), [])
        for sid in selections.keys()
    }

    job["selected_accommodations"] = selected_accommodations
    job["all_accommodation_options"] = all_options_by_stop
    job["status"] = "accommodations_confirmed"
    save_job(job_id, job)

    budget_state = _calc_budget_state(request, selected_stops, selected_accommodations)

    return {
        "job_id": job_id,
        "status": "accommodations_confirmed",
        "budget_state": budget_state,
        "selected_count": len(selected_accommodations),
        "total_stops": len(selected_stops),
    }


# ---------------------------------------------------------------------------
# POST /api/select-accommodation/{job_id} (sequential fallback)
# ---------------------------------------------------------------------------

@app.post("/api/select-accommodation/{job_id}")
async def select_accommodation(job_id: str, body: AccommodationSelectRequest):
    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    selected_stops = job["selected_stops"]
    selected_accommodations = job.get("selected_accommodations", [])

    acc_idx = job.get("accommodation_index", 0)
    prefetched = job.get("prefetched_accommodations", {})

    stop_id = body.stop_id
    options = prefetched.get(str(stop_id), [])

    if options and 0 <= body.option_index < len(options):
        # Remove existing selection for this stop
        selected_accommodations = [a for a in selected_accommodations if a.get("stop_id") != stop_id]
        selected_accommodations.append({
            "stop_id": stop_id,
            "option": options[body.option_index],
        })

    all_options_by_stop = job.get("all_accommodation_options", {})
    all_options_by_stop[str(stop_id)] = prefetched.get(str(stop_id), [])

    job["selected_accommodations"] = selected_accommodations
    job["all_accommodation_options"] = all_options_by_stop
    job["accommodation_index"] = acc_idx + 1
    all_complete = len(selected_accommodations) >= len(selected_stops)

    if all_complete:
        job["status"] = "accommodations_confirmed"

    save_job(job_id, job)

    budget_state = _calc_budget_state(request, selected_stops, selected_accommodations)

    # Next stop to select
    next_stop = None
    next_options = None
    if not all_complete:
        confirmed_ids = {a["stop_id"] for a in selected_accommodations}
        for stop in selected_stops:
            if stop["id"] not in confirmed_ids:
                next_stop = stop
                next_options = prefetched.get(str(stop["id"]), [])
                break

    return {
        "job_id": job_id,
        "selected": options[body.option_index] if options else None,
        "budget_state": budget_state,
        "all_complete": all_complete,
        "stop": next_stop,
        "options": next_options,
        "stop_number": acc_idx + 2,
        "total_stops": len(selected_stops),
    }


# ---------------------------------------------------------------------------
# POST /api/research-accommodation/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/research-accommodation/{job_id}")
async def research_accommodation(job_id: str, body: AccommodationResearchRequest):
    """Re-research accommodations for a single stop with optional extra instructions."""
    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    selected_stops = job.get("selected_stops", [])

    stop_id_int = int(body.stop_id) if body.stop_id.isdigit() else None
    stop = next((s for s in selected_stops if s.get("id") == stop_id_int), None)
    if stop is None:
        raise HTTPException(status_code=404, detail=f"Stop {body.stop_id} nicht gefunden")

    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
    acc_budget = request.budget_chf * (get_setting("budget.accommodation_pct") / 100.0)
    budget_per_night = acc_budget / max(1, total_nights)

    from agents.accommodation_researcher import AccommodationResearcherAgent
    agent = AccommodationResearcherAgent(request, job_id, extra_instructions=body.extra_instructions)
    result = await agent.find_options(stop, budget_per_night)

    new_options = result.get("options", [])
    prefetched = job.get("prefetched_accommodations", {})
    prefetched[str(stop_id_int)] = new_options
    job["prefetched_accommodations"] = prefetched
    save_job(job_id, job)

    return {
        "job_id": job_id,
        "stop_id": body.stop_id,
        "stop": stop,
        "options": new_options,
    }


# ---------------------------------------------------------------------------
# POST /api/start-planning/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/start-planning/{job_id}")
async def start_planning(job_id: str):
    from tasks.run_planning_job import run_planning_job_task

    job = get_job(job_id)
    selected_stops = job.get("selected_stops", [])
    selected_accommodations = job.get("selected_accommodations", [])

    job["status"] = "pending"
    save_job(job_id, job)

    _fire_task("run_planning_job", job_id,
               pre_built_stops=selected_stops,
               pre_selected_accommodations=selected_accommodations)

    return {
        "job_id": job_id,
        "status": "planning_started",
        "stop_count": len(selected_stops),
    }


# ---------------------------------------------------------------------------
# GET /api/progress/{job_id} — SSE stream
# ---------------------------------------------------------------------------

@app.get("/api/progress/{job_id}")
async def progress(job_id: str):
    # Verify job exists
    get_job(job_id)

    queue = debug_logger.subscribe(job_id)
    redis_key = f"sse:{job_id}"

    async def _drain_redis():
        """Move any events queued in Redis (by Celery workers) into the local queue."""
        r = debug_logger._r()
        if not r:
            return
        try:
            while True:
                raw = await asyncio.to_thread(r.lpop, redis_key)
                if raw is None:
                    break
                event = json.loads(raw)
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    break
        except Exception:
            pass

    async def event_generator():
        try:
            while True:
                # First drain any events published by Celery workers via Redis
                await _drain_redis()
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    event_type = event.pop("type", "debug_log")
                    if event_type != "debug_log" and "data" in event:
                        payload = event["data"] or {}
                    else:
                        payload = event
                    yield {
                        "event": event_type,
                        "data": json.dumps(payload),
                    }
                    if event_type in ("job_complete", "job_error"):
                        break
                except asyncio.TimeoutError:
                    # Drain Redis again before sending ping
                    await _drain_redis()
                    if queue.empty():
                        yield {"event": "ping", "data": "{}"}
        finally:
            debug_logger.unsubscribe(job_id, queue)
            # Clean up Redis list
            r = debug_logger._r()
            if r:
                try:
                    await asyncio.to_thread(r.delete, redis_key)
                except Exception:
                    pass

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET /api/result/{job_id}
# ---------------------------------------------------------------------------

@app.get("/api/result/{job_id}")
async def get_result(job_id: str):
    job = get_job(job_id)
    return job


# ---------------------------------------------------------------------------
# POST /api/generate-output/{job_id}/{file_type}
# ---------------------------------------------------------------------------

@app.post("/api/generate-output/{job_id}/{file_type}")
async def generate_output(job_id: str, file_type: str):
    from agents.output_generator import OutputGeneratorAgent

    if file_type not in ("pdf", "pptx"):
        raise HTTPException(status_code=400, detail="file_type muss 'pdf' oder 'pptx' sein")

    job = get_job(job_id)
    result = job.get("result")
    if not result:
        raise HTTPException(status_code=400, detail="Keine Ergebnisse vorhanden")

    agent = OutputGeneratorAgent()
    if file_type == "pdf":
        output_path = await asyncio.to_thread(agent._create_pdf, result, OUTPUTS_DIR)
    else:
        output_path = await asyncio.to_thread(agent._create_pptx, result, OUTPUTS_DIR)

    # Save path in job
    job["result"]["outputs"] = job.get("result", {}).get("outputs", {})
    job["result"]["outputs"][file_type] = str(output_path)
    save_job(job_id, job)

    media_type = "application/pdf" if file_type == "pdf" else \
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return FileResponse(
        path=str(output_path),
        media_type=media_type,
        filename=output_path.name,
    )


# ---------------------------------------------------------------------------
# Settings endpoints (SQLite key-value store)
# ---------------------------------------------------------------------------

class SettingsUpdateRequest(BaseModel):
    settings: dict[str, object]

class SettingsResetRequest(BaseModel):
    section: str = Field(pattern="^(agent|budget|api|geo|system|all)$")


@app.get("/api/settings")
async def api_get_settings():
    all_settings = await async_get_all_settings()
    api_keys = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google_maps": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "brave": bool(os.getenv("BRAVE_API_KEY")),
    }
    return {"settings": all_settings, "defaults": DEFAULTS, "api_keys": api_keys}


@app.put("/api/settings")
async def api_update_settings(body: SettingsUpdateRequest):
    errors = []
    for key, value in body.settings.items():
        err = validate_setting(key, value)
        if err:
            errors.append(err)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    for key, value in body.settings.items():
        # Coerce types to match defaults
        default = DEFAULTS[key]
        if isinstance(default, int) and not isinstance(default, bool):
            value = int(value)
        elif isinstance(default, float):
            value = float(value)
        set_setting(key, value)
    return {"saved": True, "count": len(body.settings)}


@app.post("/api/settings/reset")
async def api_reset_settings(body: SettingsResetRequest):
    count = await async_reset_section(body.section)
    return {"reset": True, "section": body.section, "deleted": count}


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/api/maps-config")
async def get_maps_config():
    return {"api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")}


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools():
    return {}


@app.get("/health")
async def health():
    try:
        keys = redis_client.keys("job:*")
        active = len([k for k in keys if json.loads(redis_client.get(k) or "{}").get("status") in
                      ("building_route", "loading_accommodations", "selecting_accommodations",
                       "accommodations_confirmed", "pending", "running")])
    except Exception:
        active = 0
    return {"status": "ok", "active_jobs": active}


# ---------------------------------------------------------------------------
# Travel history endpoints (SQLite)
# ---------------------------------------------------------------------------

class SaveTravelRequest(BaseModel):
    plan: dict


class UpdateTravelRequest(BaseModel):
    custom_name: Optional[str] = None
    rating: Optional[int] = None


def _slugify(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-')[:50]


@app.get("/api/travels")
async def api_list_travels():
    travels = await list_travels()
    for t in travels:
        name = t.get("custom_name") or t.get("title") or ""
        t["slug"] = _slugify(name)
    return {"travels": travels}


@app.post("/api/travels", status_code=201)
async def api_save_travel(body: SaveTravelRequest):
    travel_id = await save_travel(body.plan)
    if travel_id is None:
        return {"saved": False, "id": None}
    return {"saved": True, "id": travel_id}


@app.patch("/api/travels/{travel_id}")
async def api_update_travel(travel_id: int, body: UpdateTravelRequest):
    updated = await update_travel(travel_id, body.custom_name, body.rating)
    if not updated:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")
    return {"updated": True, "id": travel_id}


@app.get("/api/travels/{travel_id}")
async def api_get_travel(travel_id: int):
    plan = await get_travel(travel_id)
    if plan is None:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")
    return plan


@app.delete("/api/travels/{travel_id}")
async def api_delete_travel(travel_id: int):
    if not await delete_travel(travel_id):
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")
    return {"deleted": True, "id": travel_id}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replan
# Re-runs the full orchestrator (all agents, incl. TravelGuide + stündliche
# Tagespläne) for a saved trip, reusing the existing route + accommodations.
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/replan")
async def api_replan_travel(travel_id: int):
    plan = await get_travel(travel_id)
    if plan is None:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")

    # Reconstruct TravelRequest from the saved plan
    # The plan must contain a "request" snapshot; fall back to deriving minimal fields.
    req_data = plan.get("request")
    if not req_data:
        # Build a minimal request from the plan itself
        stops = plan.get("stops", [])
        first_stop = stops[0] if stops else {}
        last_stop  = stops[-1] if stops else {}
        day_plans  = plan.get("day_plans", [])
        req_data = {
            "start_location":  plan.get("start_location", "Unbekannt"),
            "main_destination": last_stop.get("region", "Unbekannt"),
            "start_date":      "2026-01-01",
            "end_date":        "2026-01-10",
            "total_days":      len(day_plans) or 10,
            "adults":          2,
            "budget_chf":      plan.get("cost_estimate", {}).get("total_chf", 3000),
        }

    request_obj = TravelRequest(**req_data)

    # Rebuild pre_built_stops and pre_selected_accommodations from the saved plan
    pre_built_stops = []
    for stop in plan.get("stops", []):
        s = {k: v for k, v in stop.items()
             if k not in ("travel_guide", "further_activities", "top_activities",
                          "restaurants", "accommodation", "image_overview",
                          "image_mood", "image_customer")}
        pre_built_stops.append(s)

    pre_selected_accommodations = []
    for stop in plan.get("stops", []):
        if stop.get("accommodation"):
            pre_selected_accommodations.append({
                "stop_id": stop["id"],
                "option": stop["accommodation"],
            })

    # Create a new ephemeral job
    job_id = uuid.uuid4().hex
    job = {
        "status": "pending",
        "request": request_obj.model_dump(mode="json"),
        "selected_stops": pre_built_stops,
        "selected_accommodations": pre_selected_accommodations,
        "replan_source_id": travel_id,
    }
    save_job(job_id, job)

    _fire_task("run_planning_job", job_id,
               pre_built_stops=pre_built_stops,
               pre_selected_accommodations=pre_selected_accommodations)

    return {"job_id": job_id, "status": "planning_started", "source_travel_id": travel_id}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replace-stop
# Replace a stop in a finished travel plan (manual location or search mode)
# ---------------------------------------------------------------------------

class ReplaceStopRequest(BaseModel):
    stop_id: int
    mode: str  # "manual" | "search"
    manual_location: Optional[str] = None
    manual_nights: Optional[int] = None


@app.post("/api/travels/{travel_id}/replace-stop")
async def api_replace_stop(travel_id: int, body: ReplaceStopRequest):
    from agents.stop_options_finder import StopOptionsFinderAgent

    plan = await get_travel(travel_id)
    if plan is None:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")

    stops = plan.get("stops", [])
    stop_index = next((i for i, s in enumerate(stops) if s.get("id") == body.stop_id), None)
    if stop_index is None:
        raise HTTPException(400, detail=f"Stop {body.stop_id} nicht gefunden")

    old_stop = stops[stop_index]

    if body.mode == "manual":
        if not body.manual_location or not body.manual_location.strip():
            raise HTTPException(400, detail="Ortsname darf nicht leer sein")

        geo_result = await geocode_google(body.manual_location.strip())
        if not geo_result:
            raise HTTPException(400, detail=f"Ort '{body.manual_location}' konnte nicht gefunden werden")

        nights = body.manual_nights if body.manual_nights and body.manual_nights > 0 else old_stop.get("nights", 1)

        job_id = uuid.uuid4().hex
        job = {
            "status": "replacing",
            "travel_id": travel_id,
            "stop_index": stop_index,
            "new_region": body.manual_location.strip(),
            "new_country": "XX",
            "new_lat": geo_result[0],
            "new_lng": geo_result[1],
            "new_nights": nights,
            "request": plan.get("request", {}),
        }
        save_job(job_id, job)
        _fire_task("replace_stop_job", job_id)

        return {"job_id": job_id, "status": "replacing"}

    elif body.mode == "search":
        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)

        # Determine prev/next locations
        if stop_index > 0:
            prev_stop = stops[stop_index - 1]
            prev_location = f"{prev_stop['region']}, {prev_stop.get('country', '')}"
        else:
            prev_location = plan.get("start_location", "")

        if stop_index < len(stops) - 1:
            next_stop = stops[stop_index + 1]
            segment_target = f"{next_stop['region']}, {next_stop.get('country', '')}"
        else:
            segment_target = ""

        # Calc route geometry for the segment
        route_geo = {}
        if prev_location and segment_target:
            route_geo = await _calc_route_geometry(
                prev_location, segment_target, 1,
                request.max_drive_hours_per_day,
            )

        agent = StopOptionsFinderAgent(request, "search_" + uuid.uuid4().hex[:8])
        options, map_anchors, _, _ = await _find_and_stream_options(
            agent=agent,
            job_id="search_" + uuid.uuid4().hex[:8],
            selected_stops=[],
            stop_number=1,
            days_remaining=old_stop.get("nights", 2) + 2,
            route_could_be_complete=False,
            segment_target=segment_target,
            segment_index=0,
            segment_count=1,
            prev_location=prev_location,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=route_geo,
        )

        # Enrich options with Google Directions
        for opt in options:
            opt["nights"] = old_stop.get("nights", 1)

        job_id = uuid.uuid4().hex
        job = {
            "status": "awaiting_selection",
            "travel_id": travel_id,
            "stop_index": stop_index,
            "options": options,
            "request": req_data,
        }
        save_job(job_id, job)

        return {"job_id": job_id, "options": options, "map_anchors": map_anchors}

    else:
        raise HTTPException(400, detail=f"Unbekannter Modus: {body.mode}")


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replace-stop-select
# Select one of the search options for stop replacement
# ---------------------------------------------------------------------------

class ReplaceStopSelectRequest(BaseModel):
    job_id: str
    option_index: int


@app.post("/api/travels/{travel_id}/replace-stop-select")
async def api_replace_stop_select(travel_id: int, body: ReplaceStopSelectRequest):
    job = get_job(body.job_id)
    if job.get("travel_id") != travel_id:
        raise HTTPException(400, detail="Job gehört nicht zu dieser Reise")

    options = job.get("options", [])
    if body.option_index < 0 or body.option_index >= len(options):
        raise HTTPException(400, detail="Ungültiger option_index")

    selected = options[body.option_index]
    plan = await get_travel(travel_id)
    if plan is None:
        raise HTTPException(404, detail=f"Reise {travel_id} nicht gefunden")

    stops = plan.get("stops", [])
    stop_index = job["stop_index"]
    old_stop = stops[stop_index] if stop_index < len(stops) else {}
    nights = selected.get("nights", old_stop.get("nights", 1))

    new_job_id = uuid.uuid4().hex
    new_job = {
        "status": "replacing",
        "travel_id": travel_id,
        "stop_index": stop_index,
        "new_region": selected.get("region", ""),
        "new_country": selected.get("country", "XX"),
        "new_lat": selected.get("lat", 0),
        "new_lng": selected.get("lon", 0),
        "new_nights": nights,
        "request": job.get("request", plan.get("request", {})),
    }
    save_job(new_job_id, new_job)
    _fire_task("replace_stop_job", new_job_id)

    return {"job_id": new_job_id, "status": "replacing", "selected": selected}


# ---------------------------------------------------------------------------
# Answer explore zone questions
# ---------------------------------------------------------------------------

@app.post("/api/skip-to-leg-end/{job_id}")
async def skip_to_leg_end(job_id: str):
    """Skip remaining stops in current leg — add end_location as stop and advance to next leg."""
    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    total_legs = len(request.legs)

    # Add current leg's end_location as a stop
    days_used = sum(1 + s.get("nights", request.min_nights_per_stop) for s in job["segment_stops"])
    days_remaining = max(0, job["segment_budget"] - days_used)
    dest_nights = max(request.min_nights_per_stop,
                      min(request.max_nights_per_stop, days_remaining - 1))

    job["stop_counter"] += 1
    end_stop = {
        "id": job["stop_counter"],
        "option_type": "direct",
        "region": leg.end_location,
        "country": "XX",
        "drive_hours": 1.0,
        "nights": dest_nights,
        "highlights": [],
        "teaser": f"Ziel Etappe {leg_index + 1}: {leg.end_location}",
        "is_fixed": False,
    }
    job["selected_stops"].append(end_stop)

    # Emit leg_complete
    await debug_logger.push_event(
        job_id, "leg_complete", None,
        {"leg_id": leg.leg_id, "leg_index": leg_index, "mode": leg.mode}
    )

    if leg_index < total_legs - 1:
        _advance_to_next_leg(job, request)
        save_job(job_id, job)

        next_leg = request.legs[job["leg_index"]]
        if next_leg.mode == "explore":
            result = await _start_explore_leg(job, job_id, request)
        else:
            result = await _start_leg_route_building(job, job_id, request)

        result["job_id"] = job_id
        result["selected_stop"] = end_stop
        result["selected_stops"] = job["selected_stops"]
        return result
    else:
        job["current_options"] = []
        job["route_could_be_complete"] = True
        save_job(job_id, job)
        return {
            "job_id": job_id,
            "selected_stop": end_stop,
            "selected_stops": job["selected_stops"],
            "options": [],
            "meta": {
                "route_could_be_complete": True,
                **_leg_meta(request, leg_index),
            },
        }


# ---------------------------------------------------------------------------
# POST /api/replace-region/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/replace-region/{job_id}")
async def replace_region(job_id: str, body: ReplaceRegionRequest):
    from agents.region_planner import RegionPlannerAgent
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    current_plan = RegionPlan(**job["region_plan"])
    if body.index >= len(current_plan.regions):
        raise HTTPException(status_code=400, detail="Ungültiger Region-Index")

    request = TravelRequest(**job["request"])
    agent = RegionPlannerAgent(request, job_id)
    new_plan = await agent.replace_region(
        index=body.index,
        instruction=body.instruction,
        current_plan=current_plan,
        leg_index=job["leg_index"],
    )

    job["region_plan"] = new_plan.model_dump()
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_updated", None,
        {"regions": [r.model_dump() for r in new_plan.regions],
         "summary": new_plan.summary}
    )

    return {"status": "ok", "region_plan": new_plan.model_dump()}


# ---------------------------------------------------------------------------
# POST /api/recompute-regions/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/recompute-regions/{job_id}")
async def recompute_regions(job_id: str, body: RecomputeRegionsRequest):
    from agents.region_planner import RegionPlannerAgent
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    current_plan = RegionPlan(**job["region_plan"])
    request = TravelRequest(**job["request"])
    agent = RegionPlannerAgent(request, job_id)
    new_plan = await agent.recalculate(
        instruction=body.instruction,
        current_plan=current_plan,
        leg_index=job["leg_index"],
    )

    job["region_plan"] = new_plan.model_dump()
    save_job(job_id, job)

    await debug_logger.push_event(
        job_id, "region_updated", None,
        {"regions": [r.model_dump() for r in new_plan.regions],
         "summary": new_plan.summary}
    )

    return {"status": "ok", "region_plan": new_plan.model_dump()}


# ---------------------------------------------------------------------------
# POST /api/confirm-regions/{job_id}
# ---------------------------------------------------------------------------

@app.post("/api/confirm-regions/{job_id}")
async def confirm_regions(job_id: str):
    from models.trip_leg import RegionPlan

    job = get_job(job_id)
    if not job.get("region_plan"):
        raise HTTPException(status_code=409, detail="Kein Regionen-Plan vorhanden")

    region_plan = RegionPlan(**job["region_plan"])
    request = TravelRequest(**job["request"])
    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    total_days = leg.total_days
    num_regions = len(region_plan.regions)

    # --- Nächte pro Region berechnen ---
    base_nights = total_days // num_regions
    remainder = total_days % num_regions
    per_region_nights = []
    for i in range(num_regions):
        n = base_nights + (1 if i < remainder else 0)
        n = max(n, request.min_nights_per_stop)
        per_region_nights.append(n)

    # --- Regionen als via_points injizieren ---
    req_data = job["request"]
    leg_data = req_data["legs"][leg_index]
    leg_data["via_points"] = [
        {"location": r.name, "fixed_date": None, "notes": f"Region: {r.reason}"}
        for r in region_plan.regions[:-1]   # alle ausser letzte
    ]
    leg_data["mode"] = "transit"
    if not leg_data.get("start_location"):
        leg_data["start_location"] = request.start_location
    if not leg_data.get("end_location"):
        leg_data["end_location"] = region_plan.regions[-1].name
    job["request"] = req_data

    # --- Explore-spezifische Job-Felder ---
    job["explore_segment_budgets"] = [n + 1 for n in per_region_nights]  # nights + 1 drive day
    job["explore_regions"] = [
        {"name": r.name, "lat": r.lat, "lon": r.lon,
         "highlights": r.highlights or [], "teaser": r.teaser or r.reason}
        for r in region_plan.regions
    ]
    job["region_plan_confirmed"] = True
    job["current_leg_mode"] = "transit"
    job["segment_index"] = 0
    job["segment_stops"] = []
    job["segment_budget"] = job["explore_segment_budgets"][0]

    request = TravelRequest(**req_data)
    save_job(job_id, job)

    # Extra-Instructions für StopFinder: "Suche in Region X"
    region = region_plan.regions[0]
    extra = (f"Suche Städte/Orte IN der Region {region.name}. "
             f"Highlights der Region: {', '.join(region.highlights or [])}.")

    result = await _start_leg_route_building(job, job_id, request, extra_instructions=extra)
    result["job_id"] = job_id
    return result


# ---------------------------------------------------------------------------
# Frontend error logging
# ---------------------------------------------------------------------------

class FrontendLogEntry(BaseModel):
    level: str = Field(pattern="^(error|warning|info)$")
    message: str = Field(max_length=5000)
    source: str = Field(default="", max_length=200)
    stack: str = Field(default="", max_length=10000)

@app.post("/api/log")
async def frontend_log(entry: FrontendLogEntry):
    debug_logger.log_frontend(entry.level, entry.message, entry.source, entry.stack)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Serve frontend static files
# Must be registered AFTER all /api/* routes so they take priority.
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
