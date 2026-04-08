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


async def _replace_stop_job(job_id: str):
    """Replaces a single stop: Google Directions recalc, agent research, DB update."""
    from agents.activities_agent import ActivitiesAgent
    from agents.restaurants_agent import RestaurantsAgent
    from agents.accommodation_researcher import AccommodationResearcherAgent
    from agents.travel_guide_agent import TravelGuideAgent
    from agents.day_planner import DayPlannerAgent
    from models.travel_request import TravelRequest
    from utils.debug_logger import debug_logger, LogLevel
    from utils.image_fetcher import fetch_unsplash_images
    from utils.maps_helper import geocode_google, google_directions_with_ferry
    from utils.travel_db import get_travel, update_plan_json
    from utils.settings_store import get_setting
    from utils.route_edit_lock import release_edit_lock

    store = _get_store()
    raw = store.get(f"job:{job_id}")
    if not raw:
        return
    job = json.loads(raw)
    user_id: int = job.get("user_id", 1)  # fallback to 1 (admin) for pre-auth trips

    travel_id: int = job["travel_id"]
    stop_index: int = job["stop_index"]
    new_region: str = job["new_region"]
    new_country: str = job.get("new_country", "XX")
    new_lat: float = job["new_lat"]
    new_lng: float = job["new_lng"]
    new_nights: int = job["new_nights"]

    try:
        await debug_logger.log(
            LogLevel.INFO, f"Stopp-Ersetzung gestartet: Index {stop_index} -> {new_region}",
            job_id=job_id, agent="ReplaceStop",
        )

        plan = await get_travel(travel_id, user_id)
        if not plan:
            await debug_logger.log(LogLevel.ERROR, f"Reise {travel_id} nicht gefunden", job_id=job_id, agent="ReplaceStop")
            await debug_logger.push_event(job_id, "job_error", None, {"error": f"Reise {travel_id} nicht gefunden"})
            return

        stops = plan.get("stops", [])
        if stop_index < 0 or stop_index >= len(stops):
            await debug_logger.log(LogLevel.ERROR, f"Ungueltiger Stop-Index {stop_index}", job_id=job_id, agent="ReplaceStop")
            await debug_logger.push_event(job_id, "job_error", None, {"error": "Ungueltiger Stop-Index"})
            return

        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)

        old_stop = stops[stop_index]
        stop_id = old_stop["id"]

        # Build new stop, preserving id
        new_stop = {
            **old_stop,
            "region": new_region,
            "country": new_country,
            "lat": new_lat,
            "lon": new_lng,
            "nights": new_nights,
            # Clear old research data
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

        await debug_logger.push_event(job_id, "replace_stop_progress", None, {
            "stop_id": stop_id, "phase": "directions", "message": "Fahrzeiten werden berechnet...",
        })

        # --- Google Directions recalculation ---
        new_place = f"{new_region}, {new_country}"

        # Previous stop or start_location
        if stop_index > 0:
            prev = stops[stop_index - 1]
            prev_place = f"{prev['region']}, {prev.get('country', '')}"
        else:
            prev_place = plan.get("start_location", "")

        if prev_place:
            hours, km, _, is_ferry = await google_directions_with_ferry(prev_place, new_place)
            if hours > 0:
                new_stop["drive_hours_from_prev"] = round(hours, 1)
                new_stop["drive_km_from_prev"] = round(km)
            if is_ferry:
                new_stop["is_ferry"] = True
                new_stop["ferry_hours"] = round(hours, 1)
                new_stop["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
            else:
                new_stop["is_ferry"] = False
                new_stop["ferry_hours"] = None
                new_stop["ferry_cost_chf"] = None

        # Next stop recalc
        if stop_index < len(stops) - 1:
            nxt = stops[stop_index + 1]
            nxt_place = f"{nxt['region']}, {nxt.get('country', '')}"
            hours, km, _, is_ferry = await google_directions_with_ferry(new_place, nxt_place)
            if hours > 0:
                nxt["drive_hours_from_prev"] = round(hours, 1)
                nxt["drive_km_from_prev"] = round(km)
            if is_ferry:
                nxt["is_ferry"] = True
                nxt["ferry_hours"] = round(hours, 1)
                nxt["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
            else:
                nxt["is_ferry"] = False
                nxt["ferry_hours"] = None
                nxt["ferry_cost_chf"] = None

        # Recalculate arrival_day for this and all following stops
        if stop_index == 0:
            new_stop["arrival_day"] = 1
        day = new_stop.get("arrival_day", old_stop.get("arrival_day", 1))
        day += new_nights + 1  # +1 for drive day
        for s in stops[stop_index + 1:]:
            s["arrival_day"] = day
            day += s.get("nights", 1) + 1

        # Replace stop in list
        stops[stop_index] = new_stop

        # --- Parallel research ---
        await debug_logger.push_event(job_id, "replace_stop_progress", None, {
            "stop_id": stop_id, "phase": "research", "message": "Aktivitaeten, Restaurants & Bilder werden recherchiert...",
        })

        act_result = {}
        rest_result = {}
        img_result = {}

        async def _research_activities():
            nonlocal act_result
            act_result = await ActivitiesAgent(request, job_id).run_stop(new_stop)

        async def _research_restaurants():
            nonlocal rest_result
            rest_result = await RestaurantsAgent(request, job_id).run_stop(new_stop)

        async def _research_images():
            nonlocal img_result
            img_result = await fetch_unsplash_images(
                f"{new_region} {new_country}", "location travel"
            )

        await asyncio.gather(
            _research_activities(),
            _research_restaurants(),
            _research_images(),
        )

        new_stop.update(img_result)
        new_stop["top_activities"] = act_result.get("top_activities", [])
        new_stop["restaurants"] = rest_result.get("restaurants", [])

        # --- Travel Guide ---
        await debug_logger.push_event(job_id, "replace_stop_progress", None, {
            "stop_id": stop_id, "phase": "guide", "message": "Reisefuehrer wird erstellt...",
        })

        existing_acts = [a["name"] for a in new_stop.get("top_activities", [])]
        guide_result = await TravelGuideAgent(request, job_id).run_stop(new_stop, existing_acts)
        new_stop["travel_guide"] = guide_result.get("travel_guide")
        new_stop["further_activities"] = guide_result.get("further_activities", [])

        # Fetch images for further activities
        for act in new_stop["further_activities"]:
            act_images = await fetch_unsplash_images(
                f"{act.get('name', '')} {new_region}", "activity"
            )
            act.update(act_images)

        # --- Accommodation ---
        await debug_logger.push_event(job_id, "replace_stop_progress", None, {
            "stop_id": stop_id, "phase": "accommodation", "message": "Unterkuenfte werden gesucht...",
        })

        acc_pct = get_setting("budget.accommodation_pct") / 100.0
        acc_budget = request.budget_chf * acc_pct
        total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in stops)
        budget_per_night = acc_budget / total_nights if total_nights > 0 else 150.0

        acc_agent = AccommodationResearcherAgent(request, job_id)
        acc_result = await acc_agent.find_options(new_stop, budget_per_night)
        acc_options = acc_result.get("options", [])
        new_stop["all_accommodation_options"] = acc_options
        if acc_options:
            new_stop["accommodation"] = acc_options[0]  # Auto-select first

        # --- Day Planner (full plan re-run) ---
        await debug_logger.push_event(job_id, "replace_stop_progress", None, {
            "stop_id": stop_id, "phase": "day_planner", "message": "Tagesplaene werden neu berechnet...",
        })

        # Rebuild accommodations list for day planner
        all_accommodations = []
        for s in stops:
            if s.get("accommodation"):
                all_accommodations.append({"stop_id": s["id"], "option": s["accommodation"]})

        all_research = []
        for s in stops:
            sid = s.get("id")
            merged = {}
            merged["top_activities"] = s.get("top_activities", [])
            merged["restaurants"] = s.get("restaurants", [])
            all_research.append(merged)

        route_for_planner = {"stops": stops}
        try:
            updated_plan = await DayPlannerAgent(request, job_id).run(
                route=route_for_planner,
                accommodations=all_accommodations,
                activities=all_research,
            )
            plan["day_plans"] = updated_plan.get("day_plans", plan.get("day_plans", []))
            plan["cost_estimate"] = updated_plan.get("cost_estimate", plan.get("cost_estimate", {}))
            plan["google_maps_overview_url"] = updated_plan.get("google_maps_overview_url", plan.get("google_maps_overview_url", ""))
        except Exception as exc:
            await debug_logger.log(
                LogLevel.WARNING, f"DayPlanner fehlgeschlagen (nicht kritisch): {exc}",
                job_id=job_id, agent="ReplaceStop",
            )

        # Update stops in plan
        plan["stops"] = stops

        # --- Save to DB ---
        await update_plan_json(travel_id, user_id, plan)

        await debug_logger.log(
            LogLevel.SUCCESS, f"Stopp {stop_id} erfolgreich durch {new_region} ersetzt",
            job_id=job_id, agent="ReplaceStop",
        )

        # Send completion event with full plan
        await debug_logger.push_event(job_id, "replace_stop_complete", None, plan)

        # Update job status in Redis
        job["status"] = "complete"
        job["result"] = plan
        store.setex(f"job:{job_id}", 86400, json.dumps(job))
    finally:
        release_edit_lock(travel_id)


@celery_app.task(name="tasks.replace_stop_job.replace_stop_job_task")
def replace_stop_job_task(job_id: str):
    """Runs _replace_stop_job() in asyncio event loop."""
    asyncio.run(_replace_stop_job(job_id))
