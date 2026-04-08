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


async def _remove_stop_job(job_id: str) -> None:
    """Remove a stop from a saved travel, reconnect segments, rechain days."""
    from utils.route_edit_helpers import (
        recalc_segment_directions, recalc_arrival_days, run_day_planner_refresh,
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
    stop_index: int = job["stop_index"]
    user_id: int = job.get("user_id", 1)

    try:
        await debug_logger.log(
            LogLevel.INFO,
            f"Stopp-Entfernung gestartet: Index {stop_index}",
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
        if stop_index < 0 or stop_index >= len(stops):
            await debug_logger.push_event(
                job_id, "job_error", None,
                {"error": f"Ungueltiger Stop-Index {stop_index}"},
            )
            return

        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)
        start_location = plan.get("start_location", "")

        await debug_logger.push_event(job_id, "remove_stop_progress", None, {
            "phase": "removing", "message": "Stopp wird entfernt...",
        })

        # Remove the stop
        removed = stops.pop(stop_index)

        # Reconnect: recalc directions for the stop now at stop_index (successor)
        if stop_index < len(stops):
            await debug_logger.push_event(job_id, "remove_stop_progress", None, {
                "phase": "directions", "message": "Fahrzeiten werden neu berechnet...",
            })
            await recalc_segment_directions(stops, stop_index, start_location)

        # Rechain arrival days from removal point
        await recalc_arrival_days(stops, from_index=max(0, stop_index))

        # Re-run DayPlanner
        await debug_logger.push_event(job_id, "remove_stop_progress", None, {
            "phase": "day_planner", "message": "Tagesplaene werden aktualisiert...",
        })
        plan["stops"] = stops
        await run_day_planner_refresh(plan, stops, request, job_id)

        # Save
        await update_plan_json(travel_id, user_id, plan)

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"Stopp erfolgreich entfernt (Index {stop_index})",
            job_id=job_id, agent="RouteEdit",
        )

        await debug_logger.push_event(job_id, "remove_stop_complete", None, plan)

        job["status"] = "complete"
        job["result"] = plan
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    except Exception as exc:
        await debug_logger.log(
            LogLevel.ERROR,
            f"Fehler bei Stopp-Entfernung: {exc}\n{traceback.format_exc()}",
            job_id=job_id, agent="RouteEdit",
        )
        await debug_logger.push_event(
            job_id, "job_error", None,
            {"error": f"Stopp-Entfernung fehlgeschlagen: {exc}"},
        )
        job["status"] = "error"
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    finally:
        release_edit_lock(travel_id)


@celery_app.task(name="tasks.remove_stop_job.remove_stop_job_task")
def remove_stop_job_task(job_id: str) -> None:
    """Runs _remove_stop_job() in asyncio event loop."""
    asyncio.run(_remove_stop_job(job_id))
