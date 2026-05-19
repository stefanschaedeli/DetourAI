"""Shared job-state helpers used by main.py and planning router.

Contains the core route-planning loop (_find_and_stream_options), leg/segment
transition logic, route-geometry caching, budget/quota helpers, the background
task dispatcher (_fire_task), and Pydantic request models for planning endpoints.

Lives in services/ so that both main.py and routers/planning.py can import the
helpers without creating a circular dependency.
"""
from __future__ import annotations

import asyncio
import math
import time as _time
from datetime import date
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from models.travel_request import TravelRequest
from services.redis_store import save_job, _job_lang
from utils.debug_logger import debug_logger, LogLevel
from utils.ferry_ports import is_island_destination
from utils.google_places import validate_stop_quality
from utils.i18n import t as i18n_t
from utils.maps_helper import (
    bearing_degrees,
    bearing_deviation,
    build_maps_url,
    corridor_bbox,
    decode_polyline5,
    geocode_google,
    google_directions,
    google_directions_simple,
    google_directions_with_ferry,
    point_along_route,
    proportional_corridor_buffer,
    reference_cities_along_route_google,
)


# ---------------------------------------------------------------------------
# Background-task tracking (used by /health to detect stuck jobs)
# ---------------------------------------------------------------------------

# job_id → start timestamp
_running_tasks: dict = {}

# Maximum wall-clock time (seconds) a background task is allowed to run before
# it is forcibly cancelled and marked as failed.
_TASK_TIMEOUT_SECONDS = 1800  # 30 minutes


def _fire_task(task_name: str, job_id: str, **kwargs) -> None:
    """Dispatch a background task as a fire-and-forget asyncio coroutine."""
    import logging as _logging

    _coros = {
        "prefetch_accommodations": lambda: __import__(
            "tasks.prefetch_accommodations", fromlist=["_prefetch_all_accommodations"]
        )._prefetch_all_accommodations(job_id),
        "run_planning_job": lambda: __import__(
            "tasks.run_planning_job", fromlist=["_run_job"]
        )._run_job(job_id, **kwargs),
        "replace_stop_job": lambda: __import__(
            "tasks.replace_stop_job", fromlist=["_replace_stop_job"]
        )._replace_stop_job(job_id),
        "remove_stop_job": lambda: __import__(
            "tasks.remove_stop_job", fromlist=["_remove_stop_job"]
        )._remove_stop_job(job_id),
        "add_stop_job": lambda: __import__(
            "tasks.add_stop_job", fromlist=["_add_stop_job"]
        )._add_stop_job(job_id),
        "reorder_stops_job": lambda: __import__(
            "tasks.reorder_stops_job", fromlist=["_reorder_stops_job"]
        )._reorder_stops_job(job_id),
        "update_nights_job": lambda: __import__(
            "tasks.update_nights_job", fromlist=["_update_nights_job"]
        )._update_nights_job(job_id),
    }

    if task_name not in _coros:
        return

    async def _run_with_logging():
        _running_tasks[job_id] = _time.time()
        try:
            await asyncio.wait_for(_coros[task_name](), timeout=_TASK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            _logging.getLogger("travelman").error(
                "Background task %s timed out after %ds for job %s",
                task_name, _TASK_TIMEOUT_SECONDS, job_id,
            )
            try:
                await debug_logger.push_event(
                    job_id, "job_error", None,
                    {"message": "Job-Timeout: Die Verarbeitung hat zu lange gedauert."},
                )
            except Exception as _push_exc:
                _logging.getLogger("travelman").warning("SSE push fehlgeschlagen nach Timeout: %s", _push_exc)
        except Exception as exc:
            _logging.getLogger("travelman").error(
                "Background task %s failed for job %s: %s", task_name, job_id, exc, exc_info=True,
            )
            try:
                await debug_logger.push_event(job_id, "job_error", None, {"message": str(exc)})
            except Exception as _push_exc:
                _logging.getLogger("travelman").warning("SSE push fehlgeschlagen nach Fehler: %s", _push_exc)
        finally:
            _running_tasks.pop(job_id, None)

    asyncio.ensure_future(_run_with_logging())


# ---------------------------------------------------------------------------
# Pydantic request models for planning endpoints
# ---------------------------------------------------------------------------

class RecomputeRequest(BaseModel):
    extra_instructions: str = ""


class PatchJobRequest(BaseModel):
    action: str                  # "add_days" | "add_via_point"
    extra_days: int = 2          # used by "add_days"
    via_point_location: str = "" # used by "add_via_point"


class FrontendLogEntry(BaseModel):
    level: str = Field(pattern="^(error|warning|info)$")
    message: str = Field(max_length=5000)
    source: str = Field(default="", max_length=200)
    stack: str = Field(default="", max_length=10000)


# ---------------------------------------------------------------------------
# Leg / segment budgeting and status helpers
# ---------------------------------------------------------------------------

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
        "nights_remaining": max(0, days_remaining - 1),
        "must_complete": must_complete,
        "route_could_be_complete": could_complete or must_complete,
    }


def _calc_skip_bonus(days_remaining: int, request: TravelRequest) -> int:
    """How many extra nights the target gets when skipping all remaining intermediate stops.

    days_remaining - 1 drive day, bounded by max_nights_per_stop.
    """
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
    job["explore_segment_budgets"] = []
    job["explore_regions"] = []
    return job


def _leg_meta(request: TravelRequest, leg_index: int, *, is_explore: bool = False) -> dict:
    """Returns leg_index, total_legs, leg_mode fields for meta responses."""
    return {
        "leg_index": leg_index,
        "total_legs": len(request.legs),
        "leg_mode": request.legs[leg_index].mode if leg_index < len(request.legs) else None,
        "is_explore": is_explore,
    }


def _calc_budget_state(request: TravelRequest, selected_stops: list,
                       selected_accommodations: list) -> dict:
    """45% of total budget → accommodation."""
    from utils.settings_store import get_setting
    acc_budget = request.budget_chf * (get_setting("budget.accommodation_pct") / 100.0)
    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
    spent = sum(a.get("option", {}).get("total_price_chf", 0) for a in selected_accommodations)
    remaining = acc_budget - spent

    def _stop_for_acc(a: dict) -> dict:
        return next((x for x in selected_stops if x.get("id") == a.get("stop_id")), {})  # type: ignore[return-value]

    avg_per_night = spent / max(1, sum(
        _stop_for_acc(a).get("nights", 1) for a in selected_accommodations
    ))
    return {
        "total_budget_chf": request.budget_chf,
        "accommodation_budget_chf": acc_budget,
        "spent_chf": spent,
        "remaining_chf": remaining,
        "nights_confirmed": sum(
            _stop_for_acc(a).get("nights", 1) for a in selected_accommodations
        ),
        "total_nights": total_nights,
        "avg_per_night_chf": round(avg_per_night, 2) if selected_accommodations else 0,
        "selected_count": len(selected_accommodations),
        "total_stops": len(selected_stops),
    }


def _new_job(job_id: str, request: TravelRequest) -> dict:
    """Initial job state dict for a freshly created planning session."""
    return {
        "status": "building_route",
        "created_at": _time.time(),
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

        # Architect pre-plan (per-trip, not reset per leg — covers whole trip)
        "architect_plan": None,              # ArchitectPrePlan result
        "architect_plan_attempted": False,   # True after first attempt (success or failure)

        # Explore/Region leg state (reset on each explore leg transition)
        "region_plan": None,           # RegionPlan dict after planning
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
# Geometry helpers
# ---------------------------------------------------------------------------

def _haversine_km(c1: tuple, c2: tuple) -> float:
    """Great-circle distance in km between two (lat, lon) tuples."""
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


async def _calc_route_geometry(
    from_location: str,
    to_location: str,
    stops_remaining: int,
    max_drive_hours: float,
    origin_location: str = "",
    proximity_origin_pct: int = 10,
    proximity_target_pct: int = 15,
) -> dict:
    """Geocode from/to via Google in parallel, query Directions for the full
    segment distance, then calculate ideal per-etappe distance given stops_remaining.

    Returns a dict consumed by StopOptionsFinderAgent.find_options().
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
        "min_km_from_origin": round(total_km * proximity_origin_pct / 100, 1) if proximity_origin_pct > 0 else 0.0,
        "min_km_from_target": round(total_km * proximity_target_pct / 100, 1) if proximity_target_pct > 0 else 0.0,
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


async def _enrich_options_with_google(
    options: list, prev_location: str, segment_target: str = "",
    max_drive_hours: float = 0.0,
) -> tuple[list, Optional[dict]]:
    """Geocode all places via Google in parallel, then run Google Directions in
    parallel. Agent-supplied lat/lon are used as fallback when geocoding returns
    nothing. Sets place_id on each option. Sets drives_over_limit=True on options
    that exceed max_drive_hours (if given). Returns (enriched_options, map_anchors).
    """
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
    architect_context: dict = None,
) -> tuple[list, dict, int, bool]:
    """Run StopOptionsFinder in streaming mode.

    Each option is individually Google-enriched and pushed as a 'route_option_ready'
    SSE event as soon as it's available. Options too close to the trip origin or
    segment target are silently filtered; if < 3 valid options remain, the agent
    is retried once.

    Returns (enriched_options, map_anchors, estimated_total_stops, route_could_be_complete)
    once all 3 options are done.
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
            architect_context=architect_context,
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

            # Dedup check: reject options whose region matches a selected stop (D-03, D-04, D-05)
            opt_region = opt.get("region", "").lower()
            already_selected = {s.get("region", "").lower() for s in selected_stops}
            if opt_region in already_selected:
                await debug_logger.log(
                    LogLevel.DEBUG,
                    f"  Verworfen (Duplikat bereits ausgewählt: {opt.get('region')})",
                    job_id=job_id, agent="StopOptionsFinder",
                    message_key="progress.duplicate_discarded",
                    data={"place": opt.get("region", "")},
                )
                return None

            opt["lat"] = coords[0]
            opt["lon"] = coords[1]
            if geo_result:
                opt["place_id"] = geo_result[2]
            opt["maps_url"] = build_maps_url([prev_location, place])

            if prev_coords:
                hours, km, _, is_ferry = await google_directions_with_ferry(prev_location, place)
                if hours > 0:
                    opt["drive_hours"] = hours
                    opt["drive_km"] = km
                    if is_ferry:
                        opt["is_ferry_required"] = True
                        opt["ferry_hours"] = hours
                        await debug_logger.log(
                            LogLevel.INFO,
                            f"  Faehre erkannt: {prev_location} -> {place} ({hours:.1f}h, {km:.0f}km)",
                            job_id=job_id, agent="StopOptionsFinder",
                        )

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
                        message_key="progress.rejected_near_origin",
                        data={"place": place},
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
                        message_key="progress.rejected_near_target",
                        data={"place": place},
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

            # Island destination bypass (D-09): skip corridor + bearing for island targets
            target_is_island = is_island_destination(target_coords) if target_coords else None

            if not target_is_island:
                # ------ Corridor check: proportional buffer (D-02, D-03, D-04) ------
                segment_total_km = geo.get("segment_total_km", 0)
                route_points = geo.get("_route_decoded", [])
                if segment_total_km > 0 and route_points and not geo.get("rundreise_mode", False):
                    buffer_km = proportional_corridor_buffer(segment_total_km)
                    search_from = geo.get("search_from_km", 0)
                    search_to = geo.get("search_to_km", segment_total_km)
                    prop_box = corridor_bbox(route_points, search_from, search_to, buffer_km=buffer_km)
                    if prop_box:
                        is_inside = (
                            prop_box["min_lat"] <= coords[0] <= prop_box["max_lat"]
                            and prop_box["min_lon"] <= coords[1] <= prop_box["max_lon"]
                        )
                        if not is_inside:
                            # D-04: FLAG but do NOT reject -- user may have reasons for off-route stops
                            opt["outside_corridor"] = True
                            # Calculate approximate distance outside corridor
                            clamp_lat = max(prop_box["min_lat"], min(coords[0], prop_box["max_lat"]))
                            clamp_lon = max(prop_box["min_lon"], min(coords[1], prop_box["max_lon"]))
                            opt["corridor_distance_km"] = round(
                                _haversine_km(coords, (clamp_lat, clamp_lon)), 1
                            )
                            await debug_logger.log(
                                LogLevel.INFO,
                                f"  Ausserhalb Korridor ({opt['corridor_distance_km']:.0f} km): {place}",
                                job_id=job_id, agent="StopOptionsFinder",
                            )

                # ------ Bearing check: detect backtracking (D-09, D-10) ------
                if prev_coords and target_coords and not geo.get("rundreise_mode", False):
                    d_prev_to_stop = _haversine_km(prev_coords, coords)
                    if d_prev_to_stop > 20:  # Skip bearing check for very short distances (unreliable)
                        route_bearing = bearing_degrees(prev_coords, target_coords)
                        stop_bearing = bearing_degrees(prev_coords, coords)
                        deviation = bearing_deviation(route_bearing, stop_bearing)
                        if deviation > 90:
                            await debug_logger.log(
                                LogLevel.DEBUG,
                                f"  Verworfen (Backtracking: {deviation:.0f} Grad Abweichung): {place}",
                                job_id=job_id, agent="StopOptionsFinder",
                            )
                            return None
            else:
                await debug_logger.log(
                    LogLevel.DEBUG,
                    f"  Korridor-Check uebersprungen (Insel-Ziel: {target_is_island}): {place}",
                    job_id=job_id, agent="StopOptionsFinder",
                )

            # ------ Quality check: Google Places validation (D-07, D-08) ------
            try:
                is_quality, reason = await validate_stop_quality(
                    opt.get("region", ""), opt.get("country", ""),
                    coords[0], coords[1]
                )
                if not is_quality:
                    await debug_logger.log(
                        LogLevel.DEBUG,
                        f"  Verworfen (Qualitaet: {reason}): {place}",
                        job_id=job_id, agent="StopOptionsFinder",
                    )
                    return None  # Silent rejection -- triggers re-ask in the existing retry logic
            except Exception as e:
                # Quality check failure should not block the pipeline
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"  Qualitaetspruefung fehlgeschlagen ({e}): {place} -- wird akzeptiert",
                    job_id=job_id, agent="StopOptionsFinder",
                )

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
            message_key="progress.retry_with_hint",
            data={"count": len(enriched_options)},
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
# Leg start / explore-leg helpers (used during leg transitions)
# ---------------------------------------------------------------------------

async def _start_leg_route_building(job: dict, job_id: str, request: TravelRequest,
                                    extra_instructions: str = "") -> dict:
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

    # Architect Pre-Plan: run once before first stop selection (D-09, D-12, D-13, D-14)
    architect_plan = job.get("architect_plan")
    if not job.get("architect_plan_attempted") and job["leg_index"] == 0 and job["stop_counter"] == 0:
        from agents.architect_pre_plan import ArchitectPrePlanAgent
        try:
            pre_plan_agent = ArchitectPrePlanAgent(request, job_id)
            architect_plan = await asyncio.wait_for(pre_plan_agent.run(), timeout=5.0)
            job["architect_plan"] = architect_plan
            await debug_logger.log(LogLevel.AGENT, "Architect Pre-Plan erstellt", job_id=job_id, agent="ArchitectPrePlan")
        except Exception as exc:
            await debug_logger.log(
                LogLevel.WARNING,
                f"Architect Pre-Plan fehlgeschlagen ({type(exc).__name__}) — StopOptionsFinder läuft ohne Kontext",
                job_id=job_id, agent="ArchitectPrePlan",
            )
            job["architect_plan"] = None
        job["architect_plan_attempted"] = True
        save_job(job_id, job)

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
            architect_context=architect_plan,
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


async def _auto_confirm_regions(job: dict, job_id: str, region_plan) -> TravelRequest:
    """Inject region plan as via_points and set explore job fields. Returns updated TravelRequest."""
    leg_index = job["leg_index"]
    req_data = job["request"]
    leg_data = req_data["legs"][leg_index]
    total_days = (date.fromisoformat(leg_data["end_date"]) - date.fromisoformat(leg_data["start_date"])).days
    num_regions = len(region_plan.regions)
    request_obj = TravelRequest(**req_data)

    base_nights = total_days // num_regions
    remainder = total_days % num_regions
    per_region_nights = []
    for i in range(num_regions):
        n = base_nights + (1 if i < remainder else 0)
        n = max(n, request_obj.min_nights_per_stop)
        per_region_nights.append(n)

    leg_data["via_points"] = [
        {"location": r.name, "fixed_date": None, "notes": f"Region: {r.reason}"}
        for r in region_plan.regions[:-1]
    ]
    leg_data["mode"] = "transit"
    if not leg_data.get("start_location"):
        first_leg_start = req_data["legs"][0].get("start_location", "").strip()
        if first_leg_start and not first_leg_start.startswith("[Erkunden]"):
            leg_data["start_location"] = first_leg_start
        else:
            raise HTTPException(status_code=400, detail=i18n_t("error.start_location_required", _job_lang(job)))
    if not leg_data.get("end_location"):
        leg_data["end_location"] = region_plan.regions[-1].name
    job["request"] = req_data

    job["explore_segment_budgets"] = [n + 1 for n in per_region_nights]
    job["explore_regions"] = [
        {"name": r.name, "lat": r.lat, "lon": r.lon,
         "highlights": r.highlights or [], "teaser": r.teaser or r.reason}
        for r in region_plan.regions
    ]
    job["current_leg_mode"] = "transit"
    job["segment_index"] = 0
    job["segment_stops"] = []
    job["segment_budget"] = job["explore_segment_budgets"][0]

    updated_request = TravelRequest(**req_data)
    save_job(job_id, job)
    return updated_request


async def _start_explore_leg(job: dict, job_id: str, request: TravelRequest) -> dict:
    """Start explore-mode leg: runs RegionPlannerAgent and auto-confirms into stop selection."""
    from agents.region_planner import RegionPlannerAgent

    leg_index = job["leg_index"]
    leg = request.legs[leg_index]
    description = leg.explore_description or "Region erkunden"

    agent = RegionPlannerAgent(request, job_id)
    region_plan = await agent.plan(description=description, leg_index=leg_index)

    job["region_plan"] = region_plan.model_dump()
    save_job(job_id, job)

    # Auto-confirm: inject regions as via_points and start route building immediately
    request = await _auto_confirm_regions(job, job_id, region_plan)

    region = region_plan.regions[0]
    extra = (f"Suche Städte/Orte IN der Region {region.name}. "
             f"Highlights der Region: {', '.join(region.highlights or [])}.")

    result = await _start_leg_route_building(job, job_id, request, extra_instructions=extra)
    result["job_id"] = job_id
    return result


# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------

def estimate_trip_tokens(request: TravelRequest) -> int:
    """Conservative upper-bound token estimate for a trip before it starts."""
    avg_nights = (request.min_nights_per_stop + request.max_nights_per_stop) / 2
    num_stops = max(1, round(request.total_days / avg_nights))
    num_legs = len(request.legs)

    route_cost   = num_legs * 6_000
    per_stop     = num_stops * 8_000
    planner_cost = 10_000
    analysis     = 5_000
    raw = route_cost + per_stop + planner_cost + analysis
    return int(raw * 1.25)  # 25% safety buffer


async def _check_user_quota(user_id: int, estimated_cost: int = 0) -> None:
    """Reject the request if the user's accumulated token usage would exceed their quota."""
    from utils.auth_db import get_quota
    from utils.travel_db import get_user_token_total
    quota = await asyncio.to_thread(get_quota, user_id)
    if quota is None:
        return
    used = await get_user_token_total(user_id)
    if used >= quota:
        raise HTTPException(
            status_code=402,
            detail=i18n_t("error.quota_exhausted", "de", total=f"{used:,}", quota=f"{quota:,}"),
        )
    if estimated_cost > 0 and used + estimated_cost > quota:
        raise HTTPException(
            status_code=402,
            detail=i18n_t("error.quota_exhausted", "de", total=f"{used:,}", quota=f"{quota:,}"),
        )
