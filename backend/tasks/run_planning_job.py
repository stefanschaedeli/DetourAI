import asyncio
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app


def _get_store():
    """Return the active job store (real Redis or in-memory fallback)."""
    try:
        from main import redis_client
        return redis_client
    except Exception:
        import redis as redis_lib
        return redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))


async def _run_job(job_id: str, pre_built_stops=None, pre_selected_accommodations=None):
    """Runs TravelPlannerOrchestrator.run() and saves result to Redis."""
    from orchestrator import TravelPlannerOrchestrator
    from models.travel_request import TravelRequest
    from utils.debug_logger import debug_logger, LogLevel

    redis_client = _get_store()
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        return

    job = json.loads(raw)
    user_id: int = job.get("user_id", 1)  # fallback to 1 (admin) for pre-auth trips

    # Skip if paused waiting for region confirmation
    if job.get("status") == "awaiting_region_confirmation":
        return

    job["status"] = "running"
    redis_client.setex(f"job:{job_id}", 86400, json.dumps(job))

    request = TravelRequest(**job["request"])

    try:
        orchestrator = TravelPlannerOrchestrator(request, job_id)
        result = await orchestrator.run(
            pre_built_stops=pre_built_stops or job.get("selected_stops"),
            pre_selected_accommodations=pre_selected_accommodations or job.get("selected_accommodations"),
            pre_all_accommodation_options=job.get("all_accommodation_options", {}),
        )

        result["request"] = job["request"]

        token_counts = result.pop("_token_counts", {
            "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0
        })

        raw2 = redis_client.get(f"job:{job_id}")
        job2 = json.loads(raw2) if raw2 else job
        job2["status"] = "complete"
        job2["result"] = result
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(job2))

        try:
            from utils.travel_db import save_travel as _db_save
            await _db_save(result, user_id, token_counts=token_counts)
        except Exception as db_err:
            await debug_logger.log(
                LogLevel.WARNING, f"DB-Speicherung fehlgeschlagen: {db_err}",
                job_id=job_id, agent="RunPlanningJob",
            )

        await debug_logger.log(
            LogLevel.SUCCESS, "Planungsauftrag abgeschlossen",
            job_id=job_id, agent="RunPlanningJob",
        )

    except Exception as e:
        tb = traceback.format_exc()
        await debug_logger.log(
            LogLevel.ERROR, f"Planungsauftrag fehlgeschlagen: {type(e).__name__}: {e}\n{tb}",
            job_id=job_id, agent="RunPlanningJob",
        )
        raw3 = redis_client.get(f"job:{job_id}")
        job3 = json.loads(raw3) if raw3 else job
        job3["status"] = "error"
        job3["error"] = str(e)
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(job3))
        await debug_logger.push_event(job_id, "job_error", None, {"error": str(e)})


@celery_app.task(name="tasks.run_planning_job.run_planning_job_task")
def run_planning_job_task(job_id: str, pre_built_stops=None, pre_selected_accommodations=None):
    """Runs TravelPlannerOrchestrator.run() in asyncio event loop."""
    asyncio.run(_run_job(job_id, pre_built_stops, pre_selected_accommodations))
