"""Async task that inserts a new stop into a saved travel plan, runs full research, and refreshes day plans."""

import asyncio
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_store():
    """Return the active job store (real Redis or in-memory fallback)."""
    from services.redis_store import redis_client
    return redis_client


async def _add_stop_job(job_id: str) -> None:
    """Add a custom stop at a given position, run full research, recalc plan."""
    from utils.route_edit_helpers import (
        recalc_segment_directions, recalc_arrival_days,
        run_day_planner_refresh, run_research_pipeline,
    )
    from utils.route_edit_lock import release_edit_lock
    from utils.debug_logger import debug_logger, LogLevel
    from utils.travel_db import get_travel, update_plan_json
    from models.travel_request import TravelRequest

    store = _get_store()
    raw = store.get(f"job:{job_id}")
    if not raw:
        return
    job = json.loads(raw)
    travel_id: int = job["travel_id"]
    insert_after_index: int = job["insert_after_index"]
    location_name: str = job["location_name"]
    lat: float = job["lat"]
    lng: float = job["lng"]
    nights: int = job.get("nights", 1)
    user_id: int = job.get("user_id", 1)

    try:
        await debug_logger.log(
            LogLevel.INFO,
            f"Stopp-Hinzufuegung gestartet: {location_name} nach Index {insert_after_index}",
            job_id=job_id, agent="RouteEdit",
        )

        plan = await get_travel(travel_id, user_id)
        if not plan:
            await debug_logger.push_event(
                job_id, "job_error", None,
                {"error": f"Reise {travel_id} nicht gefunden"},
            )
            return

        stops = plan.get("stops", [])
        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)
        start_location = plan.get("start_location", "")

        # Build new stop
        max_id = max((s["id"] for s in stops), default=0)
        new_stop = {
            "id": max_id + 1,
            "region": location_name,
            "country": "XX",
            "lat": lat,
            "lon": lng,
            "nights": nights,
            "arrival_day": 1,
            "drive_hours_from_prev": 0,
            "drive_km_from_prev": 0,
            "top_activities": [],
            "restaurants": [],
            "travel_guide": None,
            "further_activities": [],
            "accommodation": None,
            "all_accommodation_options": [],
            "image_overview": None,
            "image_mood": None,
            "image_customer": None,
        }

        # Insert at position
        insert_pos = insert_after_index + 1
        stops.insert(insert_pos, new_stop)
        plan["stops"] = stops

        # Recalc directions for new stop and the next stop
        await debug_logger.push_event(job_id, "add_stop_progress", None, {
            "phase": "directions", "message": "Fahrzeiten werden berechnet...",
        })
        await recalc_segment_directions(stops, insert_pos, start_location)
        if insert_pos + 1 < len(stops):
            await recalc_segment_directions(stops, insert_pos + 1, start_location)

        # Rechain arrival days
        await recalc_arrival_days(stops, from_index=insert_pos)

        # Run full research pipeline
        await debug_logger.push_event(job_id, "add_stop_progress", None, {
            "phase": "research", "message": "Aktivitaeten & Restaurants werden recherchiert...",
        })
        await run_research_pipeline(new_stop, request, job_id, plan)

        # Re-run DayPlanner
        await debug_logger.push_event(job_id, "add_stop_progress", None, {
            "phase": "day_planner", "message": "Tagesplaene werden aktualisiert...",
        })
        await run_day_planner_refresh(plan, stops, request, job_id)

        # Save
        await update_plan_json(travel_id, user_id, plan)

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"Stopp {location_name} erfolgreich hinzugefuegt",
            job_id=job_id, agent="RouteEdit",
        )

        await debug_logger.push_event(job_id, "add_stop_complete", None, plan)

        job["status"] = "complete"
        job["result"] = plan
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    except Exception as exc:
        await debug_logger.log(
            LogLevel.ERROR,
            f"Fehler bei Stopp-Hinzufuegung: {exc}\n{traceback.format_exc()}",
            job_id=job_id, agent="RouteEdit",
        )
        await debug_logger.push_event(
            job_id, "job_error", None,
            {"error": f"Stopp-Hinzufuegung fehlgeschlagen: {exc}"},
        )
        job["status"] = "error"
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    finally:
        release_edit_lock(travel_id)
