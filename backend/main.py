import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

import redis as redis_lib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from models.travel_request import TravelRequest
from models.stop_option import StopSelectRequest
from models.accommodation_option import AccommodationSelectRequest, BudgetState
from utils.debug_logger import debug_logger, LogLevel
from utils.maps_helper import geocode_nominatim, osrm_route, build_maps_url

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
    else:
        # Run inline as a fire-and-forget asyncio task
        if task_name == "prefetch_accommodations":
            from tasks.prefetch_accommodations import _prefetch_all_accommodations
            asyncio.ensure_future(_prefetch_all_accommodations(job_id))
        elif task_name == "run_planning_job":
            from tasks.run_planning_job import _run_job
            asyncio.ensure_future(_run_job(job_id, **kwargs))


app = FastAPI(title="Travelman2 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Serve frontend static files at / (must be mounted after all /api routes are defined)
# We add a root redirect here and mount static at the end of the file.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_job(job_id: str) -> dict:
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail=f"Job {job_id} nicht gefunden")
    return json.loads(raw)


def save_job(job_id: str, job: dict):
    redis_client.setex(f"job:{job_id}", 86400, json.dumps(job))


def _calc_segment_budget(request: TravelRequest, seg_idx: int) -> int:
    """Distributes total_days across N segments (N = len(via_points)+1)."""
    n = len(request.via_points) + 1
    days = [request.total_days // n] * n
    for i in range(request.total_days % n):
        days[i] += 1
    min_days = (request.min_nights_per_stop + 1) * 2
    result = days[seg_idx] if seg_idx < n else days[-1]
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


def _calc_budget_state(request: TravelRequest, selected_stops: list,
                       selected_accommodations: list) -> dict:
    """45% of total budget → accommodation."""
    acc_budget = request.budget_chf * 0.45
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


def _new_job(request: TravelRequest) -> dict:
    return {
        "status": "building_route",
        "request": request.model_dump(mode="json"),
        "selected_stops": [],
        "current_options": [],
        "route_could_be_complete": False,
        "stop_counter": 0,
        "segment_index": 0,
        "segment_budget": _calc_segment_budget(request, 0),
        "segment_stops": [],
        "selected_accommodations": [],
        "current_acc_options": [],
        "accommodation_index": 0,
        "prefetched_accommodations": {},
        "all_accommodations_loaded": False,
        "result": None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Request model for recompute endpoint
# ---------------------------------------------------------------------------

class RecomputeRequest(BaseModel):
    extra_instructions: str = ""


# ---------------------------------------------------------------------------
# Route geometry helper — total distance for a segment
# ---------------------------------------------------------------------------

async def _calc_route_geometry(
    from_location: str,
    to_location: str,
    stops_remaining: int,
    max_drive_hours: float,
) -> dict:
    """
    Geocodes from/to, queries OSRM for the full segment distance, then
    calculates the ideal per-etappe distance given stops_remaining.
    Returns a dict consumed by StopOptionsFinderAgent.find_options().
    """
    from_coords = await geocode_nominatim(from_location)
    await asyncio.sleep(0.35)
    to_coords = await geocode_nominatim(to_location)
    await asyncio.sleep(0.35)

    if not from_coords or not to_coords:
        return {}

    total_hours, total_km = await osrm_route([from_coords, to_coords])
    if total_km <= 0:
        return {}

    n = max(1, stops_remaining)
    ideal_km = total_km / n
    ideal_hours = total_hours / n

    return {
        "segment_total_km": total_km,
        "segment_total_hours": total_hours,
        "stops_remaining": n,
        "ideal_km_from_prev": ideal_km,
        "ideal_hours_from_prev": min(ideal_hours, max_drive_hours),
    }


# ---------------------------------------------------------------------------
# OSRM enrichment helper
# ---------------------------------------------------------------------------

async def _enrich_options_with_osrm(
    options: list, prev_location: str, segment_target: str = "",
    max_drive_hours: float = 0.0,
) -> tuple[list, Optional[dict]]:
    """Geocode each option with Nominatim, then compute real drive time via OSRM.
    Agent-supplied lat/lon are used as fallback when Nominatim returns nothing.
    Sets drives_over_limit=True on options that exceed max_drive_hours (if given).
    Returns (enriched_options, map_anchors) with coords for start and target pins."""
    prev_coords = await geocode_nominatim(prev_location)
    await asyncio.sleep(0.35)
    target_coords = None
    if segment_target:
        target_coords = await geocode_nominatim(segment_target)
        await asyncio.sleep(0.35)
    for opt in options:
        place = f"{opt.get('region', '')}, {opt.get('country', '')}"
        nom_coords = await geocode_nominatim(place)
        await asyncio.sleep(0.35)
        # Prefer Nominatim; fall back to agent-provided lat/lon
        agent_lat = opt.get("lat")
        agent_lon = opt.get("lon")
        agent_coords = (agent_lat, agent_lon) if agent_lat and agent_lon else None
        coords = nom_coords or agent_coords
        if coords:
            opt["lat"] = coords[0]
            opt["lon"] = coords[1]
            opt["maps_url"] = build_maps_url([prev_location, place])
            if prev_coords:
                hours, km = await osrm_route([prev_coords, coords])
                if hours > 0:
                    opt["drive_hours"] = hours
                    opt["drive_km"] = km
        # Flag options that exceed the user's max drive time limit
        if max_drive_hours > 0:
            opt["drives_over_limit"] = opt.get("drive_hours", 0) > max_drive_hours
    map_anchors = {
        "prev_lat": prev_coords[0] if prev_coords else None,
        "prev_lon": prev_coords[1] if prev_coords else None,
        "prev_label": prev_location,
        "target_lat": target_coords[0] if target_coords else None,
        "target_lon": target_coords[1] if target_coords else None,
        "target_label": segment_target,
    }
    return options, map_anchors


# ---------------------------------------------------------------------------
# POST /api/plan-trip
# ---------------------------------------------------------------------------

@app.post("/api/plan-trip")
async def plan_trip(request: TravelRequest):
    from agents.stop_options_finder import StopOptionsFinderAgent

    job_id = uuid.uuid4().hex[:8]
    job = _new_job(request)
    save_job(job_id, job)

    await debug_logger.log(LogLevel.INFO, f"Neue Reise: {request.start_location} → {request.main_destination}",
                           job_id=job_id)

    # Determine segment target (first via_point or main_destination)
    segment_target = (
        request.via_points[0].location if request.via_points else request.main_destination
    )

    # Estimate how many stops fit in this segment based on days/nights budget
    stops_in_segment = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))
    route_geo = await _calc_route_geometry(
        request.start_location, segment_target, stops_in_segment, request.max_drive_hours_per_day
    )

    agent = StopOptionsFinderAgent(request, job_id)
    result = await agent.find_options(
        selected_stops=[],
        stop_number=1,
        days_remaining=job["segment_budget"],
        route_could_be_complete=False,
        segment_target=segment_target,
        segment_index=0,
        segment_count=len(request.via_points) + 1,
        route_geometry=route_geo,
    )

    options = result.get("options", [])
    estimated_total_stops = result.get("estimated_total_stops", 4)
    route_could_be_complete = result.get("route_could_be_complete", False)

    options, map_anchors = await _enrich_options_with_osrm(
        options, request.start_location, segment_target, request.max_drive_hours_per_day
    )

    job["current_options"] = options
    job["route_could_be_complete"] = route_could_be_complete
    save_job(job_id, job)

    is_last_segment = len(request.via_points) == 0
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
            "segment_count": len(request.via_points) + 1,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
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

    options = job.get("current_options", [])
    if body.option_index >= len(options):
        raise HTTPException(status_code=400, detail="Ungültiger option_index")

    selected = options[body.option_index]
    job["stop_counter"] += 1
    selected["id"] = job["stop_counter"]
    job["selected_stops"].append(selected)
    job["segment_stops"].append(selected)

    seg_idx = job["segment_index"]
    n_segments = len(request.via_points) + 1
    is_last_segment = seg_idx == n_segments - 1
    route_status = _calc_route_status(
        request, job["segment_stops"], job["segment_budget"], is_last_segment
    )

    via_point_added = None
    segment_complete = False

    if route_status["must_complete"] and not is_last_segment:
        # Insert via-point stop
        via_point = request.via_points[seg_idx]
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
        job["segment_budget"] = _calc_segment_budget(request, job["segment_index"])
        job["segment_stops"] = []

        seg_idx = job["segment_index"]
        is_last_segment = seg_idx == n_segments - 1

        segment_target = (
            request.via_points[seg_idx].location
            if seg_idx < len(request.via_points)
            else request.main_destination
        )

        stops_in_new_seg = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))
        prev_loc = via_point.location
        next_geo = await _calc_route_geometry(
            prev_loc, segment_target, stops_in_new_seg, request.max_drive_hours_per_day
        )

        agent = StopOptionsFinderAgent(request, job_id)
        next_result = await agent.find_options(
            selected_stops=job["selected_stops"],
            stop_number=job["stop_counter"] + 1,
            days_remaining=job["segment_budget"],
            route_could_be_complete=False,
            segment_target=segment_target,
            segment_index=seg_idx,
            segment_count=n_segments,
            route_geometry=next_geo,
        )
        next_options = next_result.get("options", [])
        estimated_total = next_result.get("estimated_total_stops", 4)
        next_options, map_anchors = await _enrich_options_with_osrm(
            next_options, prev_loc, segment_target, request.max_drive_hours_per_day
        )
        job["current_options"] = next_options
        job["route_could_be_complete"] = next_result.get("route_could_be_complete", False)
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
            },
        }

    elif route_status["must_complete"] and is_last_segment:
        # Route complete
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
                "segment_target": request.main_destination,
            },
        }

    else:
        # Continue building route
        segment_target = (
            request.via_points[seg_idx].location
            if seg_idx < len(request.via_points)
            else request.main_destination
        )
        prev_loc_else = selected.get("region", request.start_location)
        stops_left = max(1, route_status["days_remaining"] // (1 + request.min_nights_per_stop))
        next_geo = await _calc_route_geometry(
            prev_loc_else, segment_target, stops_left, request.max_drive_hours_per_day
        )

        agent = StopOptionsFinderAgent(request, job_id)
        next_result = await agent.find_options(
            selected_stops=job["selected_stops"],
            stop_number=job["stop_counter"] + 1,
            days_remaining=route_status["days_remaining"],
            route_could_be_complete=route_status["route_could_be_complete"],
            segment_target=segment_target,
            segment_index=seg_idx,
            segment_count=n_segments,
            route_geometry=next_geo,
        )
        next_options = next_result.get("options", [])
        estimated_total = next_result.get("estimated_total_stops", 4)
        next_options, map_anchors = await _enrich_options_with_osrm(
            next_options, prev_loc_else, segment_target, request.max_drive_hours_per_day
        )
        job["current_options"] = next_options
        job["route_could_be_complete"] = next_result.get("route_could_be_complete", False)
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

    seg_idx = job.get("segment_index", 0)
    n_segments = len(request.via_points) + 1
    segment_target = (
        request.via_points[seg_idx].location
        if seg_idx < len(request.via_points)
        else request.main_destination
    )

    selected_stops = job.get("selected_stops", [])
    stop_number = job.get("stop_counter", 0) + 1
    route_status = _calc_route_status(
        request, job.get("segment_stops", []), job.get("segment_budget", request.total_days),
        seg_idx == n_segments - 1
    )

    prev_location = selected_stops[-1]["region"] if selected_stops else request.start_location
    stops_left_rc = max(1, route_status["days_remaining"] // (1 + request.min_nights_per_stop))
    recompute_geo = await _calc_route_geometry(
        prev_location, segment_target, stops_left_rc, request.max_drive_hours_per_day
    )

    agent = StopOptionsFinderAgent(request, job_id)
    result = await agent.find_options(
        selected_stops=selected_stops,
        stop_number=stop_number,
        days_remaining=route_status["days_remaining"],
        route_could_be_complete=route_status["route_could_be_complete"],
        segment_target=segment_target,
        segment_index=seg_idx,
        segment_count=n_segments,
        extra_instructions=body.extra_instructions,
        route_geometry=recompute_geo,
    )

    options = result.get("options", [])
    options, map_anchors = await _enrich_options_with_osrm(
        options, prev_location, segment_target, request.max_drive_hours_per_day
    )

    job["current_options"] = options
    job["route_could_be_complete"] = result.get("route_could_be_complete", False)
    save_job(job_id, job)

    return {
        "job_id": job_id,
        "status": "building_route",
        "options": options,
        "meta": {
            "stop_number": stop_number,
            "days_remaining": route_status["days_remaining"],
            "estimated_total_stops": result.get("estimated_total_stops", 4),
            "route_could_be_complete": route_status["route_could_be_complete"],
            "must_complete": route_status["must_complete"],
            "segment_index": seg_idx,
            "segment_count": n_segments,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
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

    if request.main_destination.lower() not in existing_regions:
        total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
        days_remaining = request.total_days - total_nights - len(selected_stops)
        dest_nights = max(request.min_nights_per_stop,
                          min(request.max_nights_per_stop, days_remaining - 1))
        avg_drive = (sum(s.get("drive_hours", 2.0) for s in selected_stops) /
                     max(1, len(selected_stops)))
        job["stop_counter"] += 1
        selected_stops.append({
            "id": job["stop_counter"],
            "option_type": "direct",
            "region": request.main_destination,
            "country": "XX",
            "drive_hours": round(avg_drive, 1),
            "nights": dest_nights,
            "highlights": [],
            "teaser": f"Endziel: {request.main_destination}",
            "is_fixed": False,
        })

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

    job["selected_accommodations"] = selected_accommodations
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

    job["selected_accommodations"] = selected_accommodations
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

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=45.0)
                    event_type = event.pop("type", "debug_log")
                    # push_event() wraps the payload under "data"; debug_logger.log() puts
                    # fields (level, message, agent, ts) at the top level.  Flatten only
                    # events that came through push_event so the frontend receives plain dicts.
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
                    yield {"event": "ping", "data": "{}"}
        finally:
            debug_logger.unsubscribe(job_id)

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
# GET /health
# ---------------------------------------------------------------------------

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
# Serve frontend static files
# Must be registered AFTER all /api/* routes so they take priority.
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
