"""Shared helpers for route editing tasks (remove, add, reorder stops).

Extracted from replace_stop_job.py patterns. All functions modify data in-place.
"""

import asyncio
from typing import Optional


async def recalc_segment_directions(stops: list, index: int, start_location: str) -> None:
    """Recalculate Google Directions for the segment arriving at stops[index].

    Uses google_directions_with_ferry for ferry-aware routing. Sets drive_hours_from_prev,
    drive_km_from_prev, and ferry metadata (is_ferry, ferry_hours, ferry_cost_chf) on the target stop.
    """
    from utils.maps_helper import google_directions_with_ferry

    if index < 0 or index >= len(stops):
        return

    target = stops[index]

    # Determine origin
    if index > 0:
        prev = stops[index - 1]
        origin = f"{prev['region']}, {prev.get('country', '')}"
    else:
        origin = start_location

    if not origin:
        return

    destination = f"{target['region']}, {target.get('country', '')}"
    hours, km, _, is_ferry = await google_directions_with_ferry(origin, destination)
    if hours > 0:
        target["drive_hours_from_prev"] = round(hours, 1)
        target["drive_km_from_prev"] = round(km)
    if is_ferry:
        target["is_ferry"] = True
        target["ferry_hours"] = round(hours, 1)
        target["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
    else:
        target["is_ferry"] = False
        target["ferry_hours"] = None
        target["ferry_cost_chf"] = None


async def recalc_all_segments(stops: list, start_location: str) -> None:
    """Recalculate Google Directions for ALL segments (used after reorder)."""
    for i in range(len(stops)):
        await recalc_segment_directions(stops, i, start_location)


async def recalc_arrival_days(stops: list, from_index: int = 0) -> None:
    """Rechain arrival_day values from from_index onward.

    Formula: stops[0].arrival_day = 1
    stops[i].arrival_day = stops[i-1].arrival_day + stops[i-1].nights + 1  (drive day)
    """
    if not stops:
        return

    if from_index == 0:
        stops[0]["arrival_day"] = 1

    start = max(1, from_index)
    for i in range(start, len(stops)):
        prev = stops[i - 1]
        stops[i]["arrival_day"] = prev["arrival_day"] + prev.get("nights", 1) + 1


async def run_day_planner_refresh(plan: dict, stops: list, request, job_id: str) -> None:
    """Re-run DayPlannerAgent on the full plan. Updates plan dict in-place.

    On failure: logs WARNING but does NOT raise (non-critical).
    """
    from agents.day_planner import DayPlannerAgent
    from utils.debug_logger import debug_logger, LogLevel

    # Build accommodations list
    all_accommodations = []
    for s in stops:
        if s.get("accommodation"):
            all_accommodations.append({"stop_id": s["id"], "option": s["accommodation"]})

    # Build research list
    all_research = []
    for s in stops:
        merged = {
            "top_activities": s.get("top_activities", []),
            "restaurants": s.get("restaurants", []),
        }
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
        plan["google_maps_overview_url"] = updated_plan.get(
            "google_maps_overview_url", plan.get("google_maps_overview_url", "")
        )
    except Exception as exc:
        await debug_logger.log(
            LogLevel.WARNING,
            f"DayPlanner fehlgeschlagen (nicht kritisch): {exc}",
            job_id=job_id,
            agent="RouteEdit",
        )


async def run_research_pipeline(stop: dict, request, job_id: str, plan: dict) -> None:
    """Run full research pipeline for a single stop (Activities, Restaurants, Images,
    TravelGuide, Accommodation). Updates stop dict in-place.

    Follows replace_stop_job.py pattern exactly.
    """
    from agents.activities_agent import ActivitiesAgent
    from agents.restaurants_agent import RestaurantsAgent
    from agents.travel_guide_agent import TravelGuideAgent
    from agents.accommodation_researcher import AccommodationResearcherAgent
    from utils.debug_logger import debug_logger, LogLevel
    from utils.image_fetcher import fetch_unsplash_images
    from utils.settings_store import get_setting

    region = stop.get("region", "")
    country = stop.get("country", "XX")

    # --- Parallel: Activities, Restaurants, Images ---
    act_result = {}
    rest_result = {}
    img_result = {}

    async def _research_activities():
        nonlocal act_result
        act_result = await ActivitiesAgent(request, job_id).run_stop(stop)

    async def _research_restaurants():
        nonlocal rest_result
        rest_result = await RestaurantsAgent(request, job_id).run_stop(stop)

    async def _research_images():
        nonlocal img_result
        img_result = await fetch_unsplash_images(
            f"{region} {country}", "location travel"
        )

    await asyncio.gather(
        _research_activities(),
        _research_restaurants(),
        _research_images(),
    )

    stop.update(img_result)
    stop["top_activities"] = act_result.get("top_activities", [])
    stop["restaurants"] = rest_result.get("restaurants", [])

    # --- Travel Guide ---
    existing_acts = [a["name"] for a in stop.get("top_activities", [])]
    guide_result = await TravelGuideAgent(request, job_id).run_stop(stop, existing_acts)
    stop["travel_guide"] = guide_result.get("travel_guide")
    stop["further_activities"] = guide_result.get("further_activities", [])

    # Fetch images for further activities
    for act in stop.get("further_activities", []):
        act_images = await fetch_unsplash_images(
            f"{act.get('name', '')} {region}", "activity"
        )
        act.update(act_images)

    # --- Accommodation ---
    stops = plan.get("stops", [])
    acc_pct = get_setting("budget.accommodation_pct") / 100.0
    acc_budget = request.budget_chf * acc_pct
    total_nights = sum(s.get("nights", request.min_nights_per_stop) for s in stops)
    budget_per_night = acc_budget / total_nights if total_nights > 0 else 150.0

    acc_agent = AccommodationResearcherAgent(request, job_id)
    acc_result = await acc_agent.find_options(stop, budget_per_night)
    acc_options = acc_result.get("options", [])
    stop["all_accommodation_options"] = acc_options
    if acc_options:
        stop["accommodation"] = acc_options[0]  # Auto-select first
