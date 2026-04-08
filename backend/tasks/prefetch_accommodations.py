import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app


def _get_store():
    """Return the active job store (real Redis or in-memory fallback)."""
    from services.redis_store import redis_client
    return redis_client


async def _prefetch_all_accommodations(job_id: str):
    """Fetches 3 accommodation options per stop in parallel (Semaphore 2)."""
    from agents.accommodation_researcher import AccommodationResearcherAgent
    from utils.debug_logger import debug_logger, LogLevel
    from models.travel_request import TravelRequest

    redis_client = _get_store()
    raw = redis_client.get(f"job:{job_id}")
    if not raw:
        return
    job = json.loads(raw)

    request_data = job.get("request", {})
    request = TravelRequest(**request_data)
    selected_stops = job.get("selected_stops", [])

    if not selected_stops:
        return

    from utils.settings_store import get_setting
    acc_pct = get_setting("budget.accommodation_pct") / 100.0
    acc_budget = request.budget_chf * acc_pct
    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in selected_stops)
    budget_per_night = acc_budget / total_nights if total_nights > 0 else 150.0

    parallelism = get_setting("api.accommodation_parallelism")
    semaphore = asyncio.Semaphore(parallelism)
    prefetched = {}

    async def fetch_stop(stop):
        stop_id = stop["id"]
        await debug_logger.log(
            LogLevel.INFO,
            f"Lade Unterkunftsoptionen für Stop {stop_id}: {stop.get('region')}",
            job_id=job_id, agent="AccommodationPrefetch",
        )
        # SSE: accommodation_loading
        await debug_logger.push_event(job_id, "accommodation_loading", None, {
            "stop_id": stop_id,
            "region": stop.get("region"),
            "country": stop.get("country"),
        })

        agent = AccommodationResearcherAgent(request, job_id)
        result = await agent.find_options(stop, budget_per_night, semaphore=semaphore)

        prefetched[str(stop_id)] = result.get("options", [])

        # SSE: accommodation_loaded
        await debug_logger.push_event(job_id, "accommodation_loaded", None, {
            "stop_id": stop_id,
            "stop": stop,
            "options": result.get("options", []),
        })

        # Save incrementally to Redis
        raw2 = redis_client.get(f"job:{job_id}")
        if raw2:
            job2 = json.loads(raw2)
            job2["prefetched_accommodations"] = prefetched
            redis_client.setex(f"job:{job_id}", 86400, json.dumps(job2))

    tasks = [fetch_stop(stop) for stop in selected_stops]
    await asyncio.gather(*tasks)

    # Mark all loaded
    raw3 = redis_client.get(f"job:{job_id}")
    if raw3:
        job3 = json.loads(raw3)
        job3["all_accommodations_loaded"] = True
        job3["status"] = "selecting_accommodations"
        redis_client.setex(f"job:{job_id}", 86400, json.dumps(job3))

    await debug_logger.push_event(job_id, "accommodations_all_loaded", None, {
        "total_stops": len(selected_stops),
    })

    await debug_logger.log(
        LogLevel.SUCCESS,
        f"Alle {len(selected_stops)} Unterkünfte geladen",
        job_id=job_id, agent="AccommodationPrefetch",
    )


@celery_app.task(name="tasks.prefetch_accommodations.prefetch_accommodations_task")
def prefetch_accommodations_task(job_id: str):
    """Runs _prefetch_all_accommodations() in asyncio event loop."""
    asyncio.run(_prefetch_all_accommodations(job_id))
