import asyncio
from models.travel_request import TravelRequest
from agents.route_architect import RouteArchitectAgent
from agents.activities_agent import ActivitiesAgent
from agents.restaurants_agent import RestaurantsAgent
from agents.day_planner import DayPlannerAgent
from agents.travel_guide_agent import TravelGuideAgent
from utils.debug_logger import debug_logger, LogLevel
from utils.image_fetcher import fetch_unsplash_images


class TravelPlannerOrchestrator:

    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id

    async def progress(self, event_type: str, agent_id, data: dict, percent: int = 0):
        await debug_logger.push_event(self.job_id, event_type, agent_id, data, percent)

    async def run(self, pre_built_stops=None, pre_selected_accommodations=None) -> dict:
        req = self.request
        job_id = self.job_id

        await debug_logger.log(LogLevel.INFO, "Orchestrator startet", job_id=job_id)

        # Phase 1: Route
        if pre_built_stops:
            stops = pre_built_stops
            # Assign arrival_day if missing
            day = 1
            for stop in stops:
                if not stop.get("arrival_day"):
                    stop["arrival_day"] = day
                day += 1 + stop.get("nights", req.min_nights_per_stop)
        else:
            await debug_logger.log(LogLevel.AGENT, "RouteArchitect wird gestartet", job_id=job_id)
            route = await RouteArchitectAgent(req, job_id).run()
            stops = route.get("stops", [])

        await self.progress("route_ready", "route_architect", {"stops": stops}, 10)

        # Phase 2: Research
        if pre_selected_accommodations:
            all_accommodations = pre_selected_accommodations
        else:
            all_accommodations = []

        act_map: dict = {}
        rest_map: dict = {}
        loc_img_map: dict = {}
        all_research: list = []

        await debug_logger.log(LogLevel.INFO, f"Forschungsphase: {len(stops)} Stops", job_id=job_id)

        async def research_activities(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None, {
                "stop_id": sid, "region": region, "section": "activities"
            })
            result = await ActivitiesAgent(req, job_id).run_stop(stop)
            act_map[sid] = result
            await debug_logger.push_event(job_id, "activities_loaded", None, {
                "stop_id": sid,
                "region": region,
                "activities": result.get("top_activities", []),
            })

        async def research_restaurants(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None, {
                "stop_id": sid, "region": region, "section": "restaurants"
            })
            result = await RestaurantsAgent(req, job_id).run_stop(stop)
            rest_map[sid] = result
            await debug_logger.push_event(job_id, "restaurants_loaded", None, {
                "stop_id": sid,
                "region": region,
                "restaurants": result.get("restaurants", []),
            })

        async def research_location_images(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            country = stop.get("country", "")
            images = await fetch_unsplash_images(f"{region} {country}", "location travel")
            loc_img_map[sid] = images

        tasks = []
        for stop in stops:
            tasks.append(research_activities(stop))
            tasks.append(research_restaurants(stop))
            tasks.append(research_location_images(stop))
        await asyncio.gather(*tasks)

        # Merge research results
        for stop in stops:
            sid = stop.get("id")
            stop.update(loc_img_map.get(sid, {}))
            merged = {}
            merged.update(act_map.get(sid, {}))
            merged.update(rest_map.get(sid, {}))
            all_research.append(merged)

            # Send stop_done event
            acc = next((a["option"] for a in all_accommodations if a.get("stop_id") == sid), None)
            await debug_logger.push_event(job_id, "stop_done", None, {
                "stop_id": sid,
                "region": stop.get("region"),
                "accommodation": acc,
                "top_activities": act_map.get(sid, {}).get("top_activities", [])[:3],
                "restaurants": rest_map.get(sid, {}).get("restaurants", [])[:3],
            })

        # Phase 2b: Travel Guide pro Stop (parallel)
        await debug_logger.log(LogLevel.INFO, f"Reiseführer-Recherche für {len(stops)} Stops gestartet", job_id=job_id)
        guide_map: dict = {}

        async def research_travel_guide(stop):
            sid = stop.get("id")
            existing_acts = [a["name"] for a in act_map.get(sid, {}).get("top_activities", [])]
            result = await TravelGuideAgent(req, job_id).run_stop(stop, existing_acts)
            guide_map[sid] = result

        await asyncio.gather(*[research_travel_guide(s) for s in stops])

        # Merge travel guide results into stops
        for stop in stops:
            sid = stop.get("id")
            guide_result = guide_map.get(sid, {})
            stop["travel_guide"] = guide_result.get("travel_guide")
            stop["further_activities"] = guide_result.get("further_activities", [])

        await debug_logger.log(LogLevel.INFO, "Tagesplaner startet", job_id=job_id)

        # Phase 3: Day Planner
        route_for_planner = {"stops": stops}
        plan = await DayPlannerAgent(req, job_id).run(
            route=route_for_planner,
            accommodations=all_accommodations,
            activities=all_research,
        )

        await debug_logger.log(LogLevel.SUCCESS, "Reiseplan fertig!", job_id=job_id)

        # Send job_complete
        await self.progress("job_complete", None, plan, 100)

        return plan
