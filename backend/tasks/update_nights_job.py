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


async def _update_nights_job(job_id: str) -> None:
    """Aktualisiert die Nächte eines Stopps und berechnet Ankunftstage neu."""
    from utils.route_edit_helpers import recalc_arrival_days, run_day_planner_refresh
    from utils.route_edit_lock import release_edit_lock
    from utils.debug_logger import debug_logger, LogLevel
    from utils.travel_db import get_travel, update_plan_json

    store = _get_store()
    raw = store.get(f"job:{job_id}")
    if not raw:
        return
    job = json.loads(raw)
    travel_id: int = job["travel_id"]
    user_id: int = job.get("user_id", 1)
    stop_id: int = job["stop_id"]
    new_nights: int = job["nights"]
    stop_index: int = job["stop_index"]

    try:
        await debug_logger.log(
            LogLevel.INFO,
            f"Naechte-Aktualisierung gestartet: Stop {stop_id}, {new_nights} Naechte",
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
        if stop_index >= len(stops):
            await debug_logger.push_event(
                job_id, "job_error", None,
                {"error": f"Ungueltiger Stop-Index {stop_index}"},
            )
            return

        # Update nights on target stop
        stops[stop_index]["nights"] = new_nights

        await debug_logger.push_event(job_id, "update_nights_progress", None, {
            "phase": "recalc",
            "message": "Naechte aktualisiert, Tagesplaene werden neu berechnet...",
        })

        # Rechain arrival days from stop_index onward
        await recalc_arrival_days(stops, from_index=stop_index)

        # Re-run DayPlanner on the full plan
        request = plan.get("request", {})
        plan["stops"] = stops
        await run_day_planner_refresh(plan, stops, request, job_id)

        # Save
        await update_plan_json(travel_id, user_id, plan)

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"Naechte-Aktualisierung erfolgreich: Stop {stop_id} hat jetzt {new_nights} Naechte",
            job_id=job_id, agent="RouteEdit",
        )

        await debug_logger.push_event(job_id, "update_nights_complete", None, plan)

        job["status"] = "complete"
        job["result"] = plan
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    except Exception as exc:
        await debug_logger.log(
            LogLevel.ERROR,
            f"Fehler bei Naechte-Aktualisierung: {exc}\n{traceback.format_exc()}",
            job_id=job_id, agent="RouteEdit",
        )
        await debug_logger.push_event(
            job_id, "job_error", None,
            {"error": f"Naechte-Aktualisierung fehlgeschlagen: {exc}"},
        )
        job["status"] = "error"
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    finally:
        release_edit_lock(travel_id)


@celery_app.task(name="tasks.update_nights_job.update_nights_job_task")
def update_nights_job_task(job_id: str) -> None:
    """Runs _update_nights_job() in asyncio event loop."""
    asyncio.run(_update_nights_job(job_id))
