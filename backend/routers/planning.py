"""Planning router — trip-planning endpoints (job init, stop selection, SSE, etc.).

Contains the 12 endpoints driving the interactive route-building flow:
init-job, plan-trip, plan-location, select-stop, recompute-options, patch-job,
confirm-route, skip-to-leg-end, skip-segment, progress (SSE), result, and the
public frontend-error log endpoint.

All shared helpers (_find_and_stream_options, _fire_task, quota checks, etc.)
live in services.job_helpers to avoid circular imports with main.py.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from models.accommodation_option import BudgetState  # noqa: F401  (re-export hint)
from models.stop_option import StopSelectRequest
from models.travel_request import TravelRequest
from services.job_helpers import (
    FrontendLogEntry,
    PatchJobRequest,
    RecomputeRequest,
    _advance_to_next_leg,
    _calc_budget_state,
    _calc_leg_segment_budget,
    _calc_route_geometry_cached,
    _calc_route_status,
    _calc_skip_bonus,
    _check_user_quota,
    _find_and_stream_options,
    _leg_meta,
    _new_job,
    _start_explore_leg,
    _start_leg_route_building,
    estimate_trip_tokens,
)
from services.redis_store import (
    _JOB_ID_RE,
    _job_lang,
    get_job,
    redis_client,
    save_job,
)
from utils.auth import CurrentUser, get_current_user, get_current_user_sse
from utils.debug_logger import LogLevel, debug_logger
from utils.i18n import t as i18n_t
from utils.maps_helper import geocode_google

router = APIRouter(tags=["planning"])


# ---------------------------------------------------------------------------
# POST /api/init-job  — create job_id before SSE is opened
# The frontend calls this first, opens SSE, then calls plan-trip with the id.
# ---------------------------------------------------------------------------

@router.post("/api/init-job")
async def init_job(request: TravelRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Pre-create a job id so the frontend can open the SSE channel before /plan-trip kicks off work."""
    await _check_user_quota(current_user.id, estimate_trip_tokens(request))
    job_id = uuid.uuid4().hex
    job = _new_job(job_id, request)
    job["user_id"] = current_user.id
    save_job(job_id, job)
    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# POST /api/plan-trip
# ---------------------------------------------------------------------------

@router.post("/api/plan-trip")
async def plan_trip(request: TravelRequest, job_id: Optional[str] = None,
                    current_user: CurrentUser = Depends(get_current_user)):
    """Start a new trip-planning session: initialise job state and return the first set of stop options."""
    await _check_user_quota(current_user.id, estimate_trip_tokens(request))
    from agents.stop_options_finder import StopOptionsFinderAgent

    if job_id and _JOB_ID_RE.match(job_id):
        # Reuse pre-initialised job (SSE may already be open)
        job = get_job(job_id)
        # Overwrite request in case it changed (shouldn't differ, but be safe)
        job["request"] = request.model_dump(mode="json")
    else:
        job_id = uuid.uuid4().hex
        job = _new_job(job_id, request)
    job["user_id"] = current_user.id
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
            **_leg_meta(request, job["leg_index"], is_explore=bool(job.get("explore_regions"))),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/plan-location/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/plan-location/{job_id}")
async def plan_location(
    job_id: str,
    request: TravelRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Ortsreise shortcut: geocode single location leg and jump to accommodation phase."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.")
    lang = _job_lang(job)

    if len(request.legs) != 1 or request.legs[0].mode != "location":
        raise HTTPException(
            status_code=400,
            detail=i18n_t("error.location_mode_required", lang),
        )

    leg = request.legs[0]
    location = leg.start_location.strip()
    nights = (leg.end_date - leg.start_date).days

    geo = await geocode_google(location)
    if geo is None:
        raise HTTPException(
            status_code=422,
            detail=i18n_t("error.geocoding_failed", lang),
        )

    lat, lon, place_id = geo
    stop = {
        "id": 1,
        "option_type": "city",
        "region": location,
        "country": "XX",  # placeholder — country is not used in single-stop Ortsreise flow
        "lat": lat,
        "lon": lon,
        "place_id": place_id,
        "drive_hours": 0,
        "drive_km": 0,
        "nights": nights,
        "arrival_day": 1,
        "highlights": [],
        "teaser": location,
        "is_fixed": True,
    }

    # Scale activities/restaurants for location mode: at least 3 per day / 2 per day
    request.max_activities_per_stop = max(request.max_activities_per_stop, nights * 3)
    request.max_restaurants_per_stop = max(request.max_restaurants_per_stop, nights * 2)

    job["request"] = request.model_dump(mode="json")
    job["user_id"] = current_user.id
    job["selected_stops"] = [stop]
    job["stop_counter"] = 1
    job["status"] = "loading_accommodations"
    save_job(job_id, job)

    return {"job_id": job_id, "status": "loading_accommodations", "selected_stops": [stop]}


# ---------------------------------------------------------------------------
# POST /api/select-stop/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/select-stop/{job_id}")
async def select_stop(job_id: str, body: StopSelectRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Record the user's chosen stop option and return the next set of options (or signal route completion)."""
    from agents.stop_options_finder import StopOptionsFinderAgent

    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    leg = request.legs[job["leg_index"]]

    options = job.get("current_options", [])
    if body.option_index >= len(options):
        raise HTTPException(status_code=400, detail=i18n_t("error.invalid_option_index", _job_lang(job)))

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
                architect_context=job.get("architect_plan"),
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
                "nights_remaining": new_status["nights_remaining"],
                "estimated_total_stops": estimated_total,
                "route_could_be_complete": new_status["route_could_be_complete"],
                "must_complete": new_status["must_complete"],
                "segment_index": job["segment_index"],
                "segment_count": n_segments,
                "segment_target": segment_target,
                "map_anchors": map_anchors,
                "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
                **_leg_meta(request, job["leg_index"], is_explore=bool(job.get("explore_regions"))),
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
                    **_leg_meta(request, leg_index, is_explore=bool(job.get("explore_regions"))),
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
                architect_context=job.get("architect_plan"),
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
                "nights_remaining": new_status["nights_remaining"],
                "estimated_total_stops": estimated_total,
                "route_could_be_complete": new_status["route_could_be_complete"],
                "must_complete": new_status["must_complete"],
                "segment_index": seg_idx,
                "segment_count": n_segments,
                "segment_target": segment_target,
                "map_anchors": map_anchors,
                "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
                **_leg_meta(request, job["leg_index"], is_explore=bool(job.get("explore_regions"))),
            },
        }


# ---------------------------------------------------------------------------
# POST /api/recompute-options/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/recompute-options/{job_id}")
async def recompute_options(job_id: str, body: RecomputeRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Re-run StopOptionsFinder for the current position, optionally guided by extra_instructions."""
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
            architect_context=job.get("architect_plan"),
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
            "nights_remaining": route_status["nights_remaining"],
            "estimated_total_stops": estimated_total_stops,
            "route_could_be_complete": route_status["route_could_be_complete"],
            "must_complete": route_status["must_complete"],
            "segment_index": seg_idx,
            "segment_count": n_segments,
            "segment_target": segment_target,
            "map_anchors": map_anchors,
            "skip_nights_bonus": _calc_skip_bonus(route_status["days_remaining"], request),
            **_leg_meta(request, job["leg_index"], is_explore=bool(job.get("explore_regions"))),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/patch-job/{job_id}
# Adjusts job when all options exceed drive limit.
# action="add_days"      → extra_days added to total_days + segment_budget
# action="add_via_point" → inserts a new via-point before current segment target,
#                          splits the segment and recomputes options
# ---------------------------------------------------------------------------

@router.post("/api/patch-job/{job_id}")
async def patch_job(job_id: str, body: PatchJobRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Adjust job when all options exceed the drive limit: add days or insert a via-point, then recompute options."""
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
            raise HTTPException(status_code=400, detail=i18n_t("error.location_empty", _job_lang(job)))
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
        raise HTTPException(status_code=400, detail=i18n_t("error.unknown_mode", _job_lang(job)))

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
            **_leg_meta(request, leg_index, is_explore=bool(job.get("explore_regions"))),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/confirm-route/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/confirm-route/{job_id}")
async def confirm_route(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Lock in the chosen route: append remaining via-points + destination and switch into accommodation phase."""
    job = get_job(job_id)
    request = TravelRequest(**job["request"])

    # Guard: all legs must be complete before confirming route
    if job["leg_index"] < len(request.legs) - 1:
        raise HTTPException(status_code=409,
            detail=i18n_t("error.not_all_legs_complete", _job_lang(job)))

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
# POST /api/skip-to-leg-end/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/skip-to-leg-end/{job_id}")
async def skip_to_leg_end(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
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
                **_leg_meta(request, leg_index, is_explore=bool(job.get("explore_regions"))),
            },
        }


# ---------------------------------------------------------------------------
# POST /api/skip-segment/{job_id}
# ---------------------------------------------------------------------------

@router.post("/api/skip-segment/{job_id}")
async def skip_segment(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Skip current explore region — create one stop with region name and advance to next region."""
    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    leg_index = job["leg_index"]
    leg = request.legs[leg_index]

    explore_regions = job.get("explore_regions")
    explore_budgets = job.get("explore_segment_budgets")
    if not explore_regions or not explore_budgets:
        raise HTTPException(409, i18n_t("error.explore_mode_only", _job_lang(job)))

    seg_idx = job["segment_index"]
    n_segments = len(leg.via_points) + 1
    is_last_segment = seg_idx == n_segments - 1

    if seg_idx >= len(explore_regions):
        raise HTTPException(409, i18n_t("error.no_segment_to_skip", _job_lang(job)))

    region = explore_regions[seg_idx]
    region_name = region["name"]
    region_nights = max(request.min_nights_per_stop, explore_budgets[seg_idx] - 1)

    # Create a single stop for the skipped region
    job["stop_counter"] += 1
    skip_stop = {
        "id": job["stop_counter"],
        "option_type": "direct",
        "region": region_name,
        "country": "XX",
        "drive_hours": 1.0,
        "nights": region_nights,
        "highlights": region.get("highlights", []),
        "teaser": f"Region übersprungen: {region_name}",
        "is_fixed": False,
    }
    if region.get("lat") and region.get("lon"):
        skip_stop["lat"] = region["lat"]
        skip_stop["lon"] = region["lon"]

    job["selected_stops"].append(skip_stop)

    if not is_last_segment:
        # Advance to next region
        job["segment_index"] += 1
        job["segment_stops"] = []
        new_seg = job["segment_index"]

        if new_seg < len(explore_budgets):
            job["segment_budget"] = explore_budgets[new_seg]
        else:
            job["segment_budget"] = _calc_leg_segment_budget(request, leg_index)

        new_is_last = new_seg == n_segments - 1
        segment_target = (
            leg.via_points[new_seg].location
            if new_seg < len(leg.via_points)
            else leg.end_location
        )

        # Region-specific instructions for next region
        if new_seg < len(explore_regions):
            er = explore_regions[new_seg]
            extra_instr = f"Suche Städte/Orte IN der Region {er['name']}. Highlights: {', '.join(er.get('highlights', []))}."
        else:
            extra_instr = ""

        prev_loc = region_name
        stops_in_new_seg = max(1, (job["segment_budget"] - 1) // (1 + request.min_nights_per_stop))

        next_geo = await _calc_route_geometry_cached(
            job, job_id, prev_loc, segment_target,
            stops_in_new_seg, request.max_drive_hours_per_day,
            origin_location=leg.start_location,
            proximity_origin_pct=request.proximity_origin_pct,
            proximity_target_pct=request.proximity_target_pct,
        )

        from agents.stop_options_finder import StopOptionsFinderAgent
        agent = StopOptionsFinderAgent(job_id=job_id)
        next_options, map_anchors, estimated_total, _ = await _find_and_stream_options(
            agent=agent,
            job_id=job_id,
            selected_stops=job["selected_stops"],
            stop_number=job["stop_counter"] + 1,
            days_remaining=job["segment_budget"],
            route_could_be_complete=False,
            segment_target=segment_target,
            segment_index=new_seg,
            segment_count=n_segments,
            prev_location=prev_loc,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=next_geo,
            extra_instructions=extra_instr,
        )

        job["current_options"] = next_options
        save_job(job_id, job)

        new_status = _calc_route_status(request, job["segment_stops"], job["segment_budget"], new_is_last)

        return {
            "job_id": job_id,
            "selected_stop": skip_stop,
            "selected_stops": job["selected_stops"],
            "options": next_options,
            "meta": {
                "stop_number": job["stop_counter"] + 1,
                "days_remaining": new_status["days_remaining"],
                "estimated_total_stops": estimated_total,
                "route_could_be_complete": new_status["route_could_be_complete"],
                "must_complete": new_status["must_complete"],
                "segment_index": new_seg,
                "segment_count": n_segments,
                "segment_target": segment_target,
                "map_anchors": map_anchors,
                "skip_nights_bonus": _calc_skip_bonus(new_status["days_remaining"], request),
                **_leg_meta(request, leg_index, is_explore=True),
            },
        }

    else:
        # Last segment in explore leg
        total_legs = len(request.legs)

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
            result["selected_stop"] = skip_stop
            result["selected_stops"] = job["selected_stops"]
            return result
        else:
            job["current_options"] = []
            job["route_could_be_complete"] = True
            save_job(job_id, job)
            return {
                "job_id": job_id,
                "selected_stop": skip_stop,
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
                    **_leg_meta(request, leg_index, is_explore=True),
                },
            }


# ---------------------------------------------------------------------------
# GET /api/progress/{job_id} — SSE stream
# ---------------------------------------------------------------------------

@router.get("/api/progress/{job_id}")
async def progress(job_id: str, request: Request, token: Optional[str] = None,
                   current_user: CurrentUser = Depends(get_current_user_sse)):
    """SSE stream: drain Redis-queued events and forward them to the client until analysis_complete or job_error."""
    # Verify job exists and ownership
    raw = redis_client.get(f"job:{job_id}")
    if raw:
        _job_check = json.loads(raw)
        _job_user_id = _job_check.get("user_id")
        if _job_user_id is not None and _job_user_id != current_user.id:
            raise HTTPException(status_code=403,
                                detail=i18n_t("error.no_access",
                                              _job_check.get("request", {}).get("language", "de")))
    get_job(job_id)

    queue = debug_logger.subscribe(job_id)
    redis_key = f"sse:{job_id}"

    async def _drain_redis():
        """Move any events queued in Redis (by Celery workers) into the local queue."""
        import logging as _logging
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
        except Exception as _drain_exc:
            _logging.getLogger("travelman").warning("Redis drain fehlgeschlagen: %s", _drain_exc)

    async def event_generator():
        import logging as _logging
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
                    if event_type in ("analysis_complete", "job_error"):
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
                except Exception as _del_exc:
                    _logging.getLogger("travelman").warning("Redis cleanup fehlgeschlagen: %s", _del_exc)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET /api/result/{job_id}
# ---------------------------------------------------------------------------

@router.get("/api/result/{job_id}")
async def get_result(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Return the full stored job dict (used by the frontend to resume / poll state)."""
    job = get_job(job_id)
    return job


# ---------------------------------------------------------------------------
# POST /api/log — frontend error logging (no auth)
# ---------------------------------------------------------------------------

@router.post("/api/log")
async def frontend_log(entry: FrontendLogEntry):
    """Record an entry from the frontend in the API log file (public, no auth)."""
    debug_logger.log_frontend(entry.level, entry.message, entry.source, entry.stack)
    return {"ok": True}
