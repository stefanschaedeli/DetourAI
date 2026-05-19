"""Accommodations router — endpoints for the accommodation selection and planning phase.

Contains 5 endpoints driving the accommodation flow:
start-accommodations, confirm-accommodations, select-accommodation,
research-accommodation, and start-planning.

Shared helpers (_fire_task, _calc_budget_state) live in services.job_helpers
to avoid circular imports with main.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from models.accommodation_option import AccommodationResearchRequest, AccommodationSelectRequest
from models.travel_request import TravelRequest
from services.job_helpers import _calc_budget_state, _fire_task
from services.redis_store import _job_lang, get_job, save_job
from utils.auth import CurrentUser, get_current_user
from utils.i18n import t as i18n_t
from utils.settings_store import get_setting

router = APIRouter(prefix="/api", tags=["accommodations"])


# ---------------------------------------------------------------------------
# POST /api/start-accommodations/{job_id}
# Called by frontend AFTER SSE is open, so no events are lost
# ---------------------------------------------------------------------------

@router.post("/start-accommodations/{job_id}")
async def start_accommodations(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
    job = get_job(job_id)
    if job.get("status") != "loading_accommodations":
        raise HTTPException(status_code=400, detail=i18n_t("error.not_loading_accommodations", _job_lang(job)))

    _fire_task("prefetch_accommodations", job_id)

    return {"job_id": job_id, "status": "prefetch_started"}


# ---------------------------------------------------------------------------
# POST /api/confirm-accommodations/{job_id}
# ---------------------------------------------------------------------------

@router.post("/confirm-accommodations/{job_id}")
async def confirm_accommodations(job_id: str, body: dict, current_user: CurrentUser = Depends(get_current_user)):
    """Bulk-confirm accommodation selections for all stops and advance job to accommodations_confirmed."""
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

@router.post("/select-accommodation/{job_id}")
async def select_accommodation(job_id: str, body: AccommodationSelectRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Sequential fallback: confirm one accommodation at a time and return the next stop's options."""
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

@router.post("/research-accommodation/{job_id}")
async def research_accommodation(job_id: str, body: AccommodationResearchRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Re-research accommodations for a single stop with optional extra instructions."""
    job = get_job(job_id)
    request = TravelRequest(**job["request"])
    selected_stops = job.get("selected_stops", [])

    stop_id_int = int(body.stop_id) if body.stop_id.isdigit() else None
    stop = next((s for s in selected_stops if s.get("id") == stop_id_int), None)
    if stop is None:
        raise HTTPException(status_code=404, detail=i18n_t("error.stop_not_found", _job_lang(job), stop_id=body.stop_id))

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

@router.post("/start-planning/{job_id}")
async def start_planning(job_id: str, current_user: CurrentUser = Depends(get_current_user)):
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
