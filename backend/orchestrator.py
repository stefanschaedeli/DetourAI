import asyncio
import json
import os
from typing import Optional
from models.travel_request import TravelRequest
from agents.route_architect import RouteArchitectAgent
from agents.region_planner import RegionPlannerAgent
from agents.activities_agent import ActivitiesAgent
from agents.restaurants_agent import RestaurantsAgent
from agents.day_planner import DayPlannerAgent
from agents.travel_guide_agent import TravelGuideAgent
from agents.trip_analysis_agent import TripAnalysisAgent
from models.trip_leg import RegionPlan
from utils.debug_logger import debug_logger, LogLevel
from utils.image_fetcher import fetch_unsplash_images

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class TravelPlannerOrchestrator:

    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id

    def _get_store(self):
        try:
            from main import redis_client
            return redis_client
        except Exception:
            import redis as redis_lib
            return redis_lib.from_url(REDIS_URL, decode_responses=True)

    def _load_job(self) -> dict:
        store = self._get_store()
        raw = store.get(f"job:{self.job_id}")
        return json.loads(raw) if raw else {}

    def _save_job(self, job: dict):
        store = self._get_store()
        store.setex(f"job:{self.job_id}", 86400, json.dumps(job))

    async def progress(self, event_type: str, agent_id, data: dict, percent: int = 0):
        await debug_logger.push_event(self.job_id, event_type, agent_id, data, percent)

    async def run(self, pre_built_stops=None, pre_selected_accommodations=None,
                  pre_all_accommodation_options=None) -> dict:
        req = self.request
        job_id = self.job_id

        debug_logger.set_verbosity(job_id, req.log_verbosity)

        try:
            await debug_logger.log(LogLevel.INFO, "Orchestrator startet", job_id=job_id)

            # Phase 1: Route (leg-sequential)
            if pre_built_stops and len(pre_built_stops) > 0:
                # Resume after all legs completed — go straight to research
                stops = pre_built_stops
                day = 1
                for stop in stops:
                    if not stop.get("arrival_day"):
                        stop["arrival_day"] = day
                    day += 1 + stop.get("nights", req.min_nights_per_stop)
            else:
                stops = await self._run_all_legs()
                if stops is None:
                    # Paused waiting for zone guidance — job state saved, return sentinel
                    return {}

            await self.progress("route_ready", "route_architect", {"stops": stops}, 10)

            # Phase 2–4: Research + Day Planning + Analysis (unchanged)
            return await self._run_research_and_planning(
                stops, pre_selected_accommodations, pre_all_accommodation_options
            )
        finally:
            debug_logger.clear_verbosity(job_id)

    async def _run_all_legs(self) -> Optional[list]:
        """Runs all legs sequentially. Returns None if paused mid-explore."""
        req = self.request
        job = self._load_job()
        all_stops = list(job.get("selected_stops", []))

        for leg_index in range(job.get("leg_index", 0), len(req.legs)):
            leg = req.legs[leg_index]
            if leg.mode == "transit":
                leg_stops = await self._run_transit_leg(leg, leg_index)
            else:
                leg_stops = await self._run_explore_leg(leg, leg_index)
                if leg_stops is None:
                    return None  # Paused for zone guidance

            all_stops.extend(leg_stops)

            # Advance leg_index in Redis
            job = self._load_job()
            job["leg_index"] = leg_index + 1
            job["current_leg_mode"] = req.legs[leg_index + 1].mode if leg_index + 1 < len(req.legs) else None
            # Reset per-leg state
            job["segment_index"] = 0
            job["segment_stops"] = []
            job["region_plan"] = None
            job["region_plan_confirmed"] = False
            self._save_job(job)

            await debug_logger.push_event(
                self.job_id, "leg_complete", None,
                {"leg_id": leg.leg_id, "leg_index": leg_index, "mode": leg.mode}
            )

        return all_stops

    async def _run_transit_leg(self, leg, leg_index: int) -> list:
        """Transit leg: use RouteArchitectAgent (unchanged logic)."""
        req = self.request
        job = self._load_job()
        existing_stops = job.get("segment_stops", [])

        if existing_stops:
            return existing_stops   # Already built interactively

        await debug_logger.log(LogLevel.AGENT, f"RouteArchitect für Leg {leg_index}", job_id=self.job_id)
        route = await RouteArchitectAgent(req, self.job_id).run()
        return route.get("stops", [])

    async def _run_explore_leg(self, leg, leg_index: int) -> Optional[list]:
        """Explore leg: RegionPlannerAgent plans regions, user confirms interactively."""
        job = self._load_job()

        if not job.get("region_plan"):
            # First call: generate region plan
            description = leg.explore_description or f"{leg.start_location} bis {leg.end_location} erkunden"
            agent = RegionPlannerAgent(self.request, self.job_id)
            region_plan = await agent.plan(description=description, leg_index=leg_index)
            job = self._load_job()
            job["region_plan"] = region_plan.model_dump()
            job["status"] = "awaiting_region_confirmation"
            self._save_job(job)
            await debug_logger.push_event(
                self.job_id, "region_plan_ready", None,
                {"regions": [r.model_dump() for r in region_plan.regions],
                 "summary": region_plan.summary, "leg_id": leg.leg_id}
            )
            return None  # Pause — user confirms via /api/confirm-regions

        # Region plan confirmed — stops are being selected via normal transit flow
        job = self._load_job()
        return job.get("selected_stops", [])

    async def _run_research_and_planning(self, stops, pre_selected_accommodations,
                                          pre_all_accommodation_options) -> dict:
        """Unchanged research + day planning phase."""
        req = self.request
        job_id = self.job_id

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
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "activities"})
            result = await ActivitiesAgent(req, job_id).run_stop(stop)
            act_map[sid] = result
            await debug_logger.push_event(job_id, "activities_loaded", None,
                                           {"stop_id": sid, "region": region,
                                            "activities": result.get("top_activities", [])})

        async def research_restaurants(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "restaurants"})
            result = await RestaurantsAgent(req, job_id).run_stop(stop)
            rest_map[sid] = result
            await debug_logger.push_event(job_id, "restaurants_loaded", None,
                                           {"stop_id": sid, "region": region,
                                            "restaurants": result.get("restaurants", [])})

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
                "all_accommodation_options": (pre_all_accommodation_options or {}).get(str(sid), []),
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
            further = stop["further_activities"]
            region = stop.get("region", "")
            for act in further:
                images = await fetch_unsplash_images(
                    f"{act.get('name', '')} {region}", "activity"
                )
                act.update(images)

        await debug_logger.log(LogLevel.INFO, "Tagesplaner startet", job_id=job_id)

        # Phase 3: Day Planner
        route_for_planner = {"stops": stops}
        plan = await DayPlannerAgent(req, job_id).run(
            route=route_for_planner,
            accommodations=all_accommodations,
            activities=all_research,
        )

        # Merge all accommodation options into each stop
        for stop_dict in plan.get("stops", []):
            sid = stop_dict.get("id")
            stop_dict["all_accommodation_options"] = (pre_all_accommodation_options or {}).get(str(sid), [])

        await debug_logger.log(LogLevel.SUCCESS, "Reiseplan fertig!", job_id=job_id)

        # Phase 4: Reise-Analyse
        await debug_logger.log(LogLevel.INFO, "Reise-Analyse wird erstellt…", job_id=job_id)
        try:
            analysis_result = await TripAnalysisAgent(req, job_id).run(plan, req)
            plan["trip_analysis"] = analysis_result
        except Exception as exc:
            await debug_logger.log(LogLevel.WARNING,
                f"Reise-Analyse fehlgeschlagen (nicht kritisch): {exc}", job_id=job_id)
            plan["trip_analysis"] = None

        # Send job_complete
        await self.progress("job_complete", None, plan, 100)

        return plan
