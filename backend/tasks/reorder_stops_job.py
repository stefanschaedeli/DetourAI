import asyncio
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app


def _get_store():
    """Return the active job store (real Redis or in-memory fallback)."""
    from services.redis_store import redis_client
    return redis_client


async def _reorder_stops_job(job_id: str) -> None:
    """Move a stop from old_index to new_index, recalc all segments."""
    from utils.route_edit_helpers import (
        recalc_all_segments, recalc_arrival_days, run_day_planner_refresh,
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
    old_index: int = job["old_index"]
    new_index: int = job["new_index"]
    user_id: int = job.get("user_id", 1)

    try:
        await debug_logger.log(
            LogLevel.INFO,
            f"Stopp-Neuordnung gestartet: {old_index} -> {new_index}",
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
        if (old_index < 0 or old_index >= len(stops) or
                new_index < 0 or new_index >= len(stops)):
            await debug_logger.push_event(
                job_id, "job_error", None,
                {"error": f"Ungueltige Indizes: {old_index} -> {new_index}"},
            )
            return

        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)
        start_location = plan.get("start_location", "")

        await debug_logger.push_event(job_id, "reorder_stops_progress", None, {
            "phase": "reordering", "message": "Stopps werden neu geordnet...",
        })

        # Move stop
        moved = stops.pop(old_index)
        stops.insert(new_index, moved)

        # Reassign sequential IDs
        for i, s in enumerate(stops):
            s["id"] = i + 1

        # Recalc ALL segments
        await debug_logger.push_event(job_id, "reorder_stops_progress", None, {
            "phase": "directions", "message": "Alle Fahrzeiten werden neu berechnet...",
        })
        await recalc_all_segments(stops, start_location)

        # Rechain ALL arrival days
        await recalc_arrival_days(stops, from_index=0)

        # Re-run DayPlanner
        await debug_logger.push_event(job_id, "reorder_stops_progress", None, {
            "phase": "day_planner", "message": "Tagesplaene werden aktualisiert...",
        })
        plan["stops"] = stops
        await run_day_planner_refresh(plan, stops, request, job_id)

        # Save
        await update_plan_json(travel_id, user_id, plan)

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"Stopps erfolgreich neu geordnet ({old_index} -> {new_index})",
            job_id=job_id, agent="RouteEdit",
        )

        await debug_logger.push_event(job_id, "reorder_stops_complete", None, plan)

        job["status"] = "complete"
        job["result"] = plan
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    except Exception as exc:
        await debug_logger.log(
            LogLevel.ERROR,
            f"Fehler bei Stopp-Neuordnung: {exc}\n{traceback.format_exc()}",
            job_id=job_id, agent="RouteEdit",
        )
        await debug_logger.push_event(
            job_id, "job_error", None,
            {"error": f"Stopp-Neuordnung fehlgeschlagen: {exc}"},
        )
        job["status"] = "error"
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    finally:
        release_edit_lock(travel_id)


@celery_app.task(name="tasks.reorder_stops_job.reorder_stops_job_task")
def reorder_stops_job_task(job_id: str) -> None:
    """Runs _reorder_stops_job() in asyncio event loop."""
    asyncio.run(_reorder_stops_job(job_id))
