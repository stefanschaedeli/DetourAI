"""Travel planner orchestrator — coordinates all agent phases from route to day planning."""
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
from utils.i18n import t as i18n_t
from utils.image_fetcher import fetch_unsplash_images

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class TravelPlannerOrchestrator:
    """Coordinates the full planning pipeline: route building, research, day planning, and analysis.

    Phases:
      1. Route — RouteArchitectAgent per transit leg; RegionPlannerAgent for explore legs
      2. Research — parallel ActivitiesAgent, RestaurantsAgent, TravelGuideAgent per stop
      3. Day Planning — DayPlannerAgent assembles the complete itinerary
      4. Analysis — TripAnalysisAgent enriches the plan with trip-level insights
    """

    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self._token_accumulator: list = []

    def _get_store(self):
        from services.redis_store import redis_client
        return redis_client

    def _load_job(self) -> dict:
        store = self._get_store()
        raw = store.get(f"job:{self.job_id}")
        return json.loads(raw) if raw else {}

    def _save_job(self, job: dict):
        store = self._get_store()
        store.setex(f"job:{self.job_id}", 86400, json.dumps(job))

    async def progress(self, event_type: str, agent_id, data: dict, percent: int = 0):
        """Push a progress SSE event for this job via the debug_logger event bus."""
        await debug_logger.push_event(self.job_id, event_type, agent_id, data, percent)

    async def _check_quota_mid_job(self, user_id: Optional[int]) -> None:
        if user_id is None:
            return
        from utils.auth_db import get_quota
        from utils.travel_db import get_user_token_total
        quota = await asyncio.to_thread(get_quota, user_id)
        if quota is None:
            return
        saved = await get_user_token_total(user_id)
        current = sum(e["input"] + e["output"] for e in self._token_accumulator)
        total = saved + current
        if total >= quota:
            raise Exception(
                f"Token-Kontingent erschöpft ({total:,} / {quota:,} Tokens verwendet). "
                "Bitte kontaktieren Sie den Administrator."
            )

    async def run(self, pre_built_stops=None, pre_selected_accommodations=None,
                  pre_all_accommodation_options=None, user_id: Optional[int] = None) -> dict:
        """Execute all planning phases and return the final travel plan dict."""
        self._user_id = user_id
        req = self.request
        job_id = self.job_id

        debug_logger.set_verbosity(job_id, req.log_verbosity)
        self._token_accumulator = []

        try:
            lang = getattr(req, 'language', 'de')
            await debug_logger.log(LogLevel.INFO, i18n_t("progress.orchestrator_start", lang),
                                   job_id=job_id, message_key="progress.orchestrator_start")

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

    async def _run_all_legs(self) -> list:
        """Runs all legs sequentially and returns all collected stops."""
        req = self.request
        job = self._load_job()
        all_stops = list(job.get("selected_stops", []))

        for leg_index in range(job.get("leg_index", 0), len(req.legs)):
            leg = req.legs[leg_index]
            if leg.mode == "transit":
                leg_stops = await self._run_transit_leg(leg, leg_index)
            else:
                leg_stops = await self._run_explore_leg(leg, leg_index)

            all_stops.extend(leg_stops)

            # Advance leg_index in Redis
            job = self._load_job()
            job["leg_index"] = leg_index + 1
            job["current_leg_mode"] = req.legs[leg_index + 1].mode if leg_index + 1 < len(req.legs) else None
            # Reset per-leg state
            job["segment_index"] = 0
            job["segment_stops"] = []
            job["region_plan"] = None
            self._save_job(job)

            await debug_logger.push_event(
                self.job_id, "leg_complete", None,
                {"leg_id": leg.leg_id, "leg_index": leg_index, "mode": leg.mode}
            )

        return all_stops

    @staticmethod
    def _validate_drive_limits(stops: list, max_hours: float) -> tuple:
        """
        Two-tier drive limit validation (per D-04).
        - Soft limit: max_hours — flag with warning but accept
        - Hard limit: max_hours * 1.3 — reject (return hard_violation=True)
        Ferry hours (stop.get("ferry_hours", 0)) are excluded from drive time (per D-05).
        Returns (stops_with_warnings, hard_violation_found).
        """
        hard_limit = max_hours * 1.3
        hard_violation = False
        for stop in stops:
            drive = stop.get("drive_hours", 0)
            # ferry_hours excluded from limit check per D-05
            if drive <= 0:
                continue
            if drive > hard_limit:
                hard_violation = True
                stop["drive_limit_warning"] = f"Fahrzeit {drive:.1f}h überschreitet Hardlimit ({hard_limit:.1f}h)"
            elif drive > max_hours:
                stop["drive_limit_warning"] = f"Fahrzeit {drive:.1f}h überschreitet Softlimit ({max_hours:.1f}h)"
        return stops, hard_violation

    async def _run_transit_leg(self, leg, leg_index: int) -> list:
        """Transit leg: use RouteArchitectAgent, ensure start+destination are included."""
        req = self.request
        job = self._load_job()
        existing_stops = job.get("segment_stops", [])

        if existing_stops:
            return existing_stops   # Already built interactively

        await debug_logger.log(LogLevel.AGENT, f"RouteArchitect für Leg {leg_index}", job_id=self.job_id)
        route = await RouteArchitectAgent(req, self.job_id, token_accumulator=self._token_accumulator).run()
        stops = route.get("stops", [])

        # Post-generation drive limit validation (D-04)
        max_retries = 2
        for attempt in range(max_retries + 1):
            stops, hard_violation = self._validate_drive_limits(stops, req.max_drive_hours_per_day)
            if not hard_violation:
                break
            if attempt < max_retries:
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Route hat Hardlimit-Verletzung (Versuch {attempt + 1}/{max_retries + 1}) — generiere neu",
                    job_id=self.job_id,
                )
                route = await RouteArchitectAgent(req, self.job_id, token_accumulator=self._token_accumulator).run()
                stops = route.get("stops", [])
            else:
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Route hat nach {max_retries + 1} Versuchen noch Hardlimit-Verletzungen — akzeptiere mit Warnungen",
                    job_id=self.job_id,
                )

        warnings = [s for s in stops if s.get("drive_limit_warning")]
        if warnings:
            for w in warnings:
                await debug_logger.log(
                    LogLevel.INFO,
                    f"Softlimit-Warnung für {w.get('region', '?')}: {w['drive_limit_warning']}",
                    job_id=self.job_id,
                )

        # Safety net: ensure destination is included as last stop
        if stops and leg.end_location:
            last_region = stops[-1].get("region", "").lower()
            end_loc = leg.end_location.lower()
            if end_loc not in last_region and last_region not in end_loc:
                max_id = max(s.get("id", 0) for s in stops)
                last_stop = stops[-1]
                dest_arrival = last_stop.get("arrival_day", 1) + last_stop.get("nights", 1) + 1
                stops.append({
                    "id": max_id + 1,
                    "region": leg.end_location,
                    "country": "XX",
                    "arrival_day": dest_arrival,
                    "nights": req.min_nights_per_stop,
                    "drive_hours": 0,
                    "is_fixed": False,
                    "notes": "Hauptziel",
                })
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Ziel '{leg.end_location}' fehlte in Route — automatisch ergänzt",
                    job_id=self.job_id,
                )

        # Safety net: ensure start city is included as first stop
        if stops and leg.start_location:
            first_region = stops[0].get("region", "").lower()
            start_loc = leg.start_location.lower()
            if start_loc not in first_region and first_region not in start_loc:
                for s in stops:
                    s["id"] = s.get("id", 0) + 1
                stops.insert(0, {
                    "id": 1,
                    "region": leg.start_location,
                    "country": "XX",
                    "arrival_day": 1,
                    "nights": 0,
                    "drive_hours": 0,
                    "is_fixed": False,
                    "notes": "Startort",
                })
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Startort '{leg.start_location}' fehlte in Route — automatisch ergänzt",
                    job_id=self.job_id,
                )

        return stops

    async def _run_explore_leg(self, leg, leg_index: int) -> list:
        """Explore leg: RegionPlannerAgent plans regions, auto-confirms, then runs transit stop selection."""
        from main import _auto_confirm_regions

        job = self._load_job()
        description = leg.explore_description or f"{leg.start_location} bis {leg.end_location} erkunden"
        agent = RegionPlannerAgent(self.request, self.job_id, token_accumulator=self._token_accumulator)
        region_plan = await agent.plan(description=description, leg_index=leg_index)
        job = self._load_job()
        job["region_plan"] = region_plan.model_dump()
        self._save_job(job)

        # Auto-confirm: inject regions as via_points and update request
        updated_request = await _auto_confirm_regions(job, self.job_id, region_plan)
        self.request = updated_request

        # Run the leg as a transit leg now that via_points are set
        updated_leg = updated_request.legs[leg_index]
        return await self._run_transit_leg(updated_leg, leg_index)

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

        lang = getattr(req, 'language', 'de')
        await debug_logger.log(LogLevel.INFO, i18n_t("progress.research_phase", lang, count=len(stops)),
                               job_id=job_id, message_key="progress.research_phase",
                               data={"count": len(stops)})

        async def research_activities(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "activities"})
            result = await ActivitiesAgent(req, job_id, token_accumulator=self._token_accumulator).run_stop(stop)
            act_map[sid] = result
            await debug_logger.push_event(job_id, "activities_loaded", None,
                                           {"stop_id": sid, "region": region,
                                            "activities": result.get("top_activities", [])})

        async def research_restaurants(stop):
            sid = stop.get("id")
            region = stop.get("region", "")
            await debug_logger.push_event(job_id, "stop_research_started", None,
                                           {"stop_id": sid, "region": region, "section": "restaurants"})
            result = await RestaurantsAgent(req, job_id, token_accumulator=self._token_accumulator).run_stop(stop)
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
        await self._check_quota_mid_job(getattr(self, '_user_id', None))

        # Merge research results
        for stop in stops:
            sid = stop.get("id")
            stop.update(loc_img_map.get(sid, {}))
            # Merge activity tags into stop (per D-09: union + dedup, max 4)
            activity_tags = act_map.get(sid, {}).get("tags", [])
            existing_tags = stop.get("tags", [])
            stop["tags"] = list(dict.fromkeys(existing_tags + activity_tags))[:4]
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
        await debug_logger.log(LogLevel.INFO, i18n_t("progress.guide_writing", lang, count=len(stops)),
                               job_id=job_id, message_key="progress.guide_writing",
                               data={"count": len(stops)})
        guide_map: dict = {}

        async def research_travel_guide(stop):
            sid = stop.get("id")
            existing_acts = [a["name"] for a in act_map.get(sid, {}).get("top_activities", [])]
            result = await TravelGuideAgent(req, job_id, token_accumulator=self._token_accumulator).run_stop(stop, existing_acts)
            guide_map[sid] = result

        await asyncio.gather(*[research_travel_guide(s) for s in stops])
        await self._check_quota_mid_job(getattr(self, '_user_id', None))

        # Merge travel guide results into stops
        for stop in stops:
            sid = stop.get("id")
            guide_result = guide_map.get(sid, {})
            stop["travel_guide"] = guide_result.get("travel_guide")
            stop["further_activities"] = guide_result.get("further_activities", [])
            further = stop["further_activities"]
            region = stop.get("region", "")

            async def _fetch_act_image(act: dict, r: str) -> None:
                images = await fetch_unsplash_images(f"{act.get('name', '')} {r}", "activity")
                act.update(images)

            await asyncio.gather(*[_fetch_act_image(a, region) for a in further])

        await debug_logger.log(LogLevel.INFO, i18n_t("progress.day_planner_start", lang),
                               job_id=job_id, message_key="progress.day_planner_start")

        # Phase 3: Day Planner
        route_for_planner = {"stops": stops}
        plan = await DayPlannerAgent(req, job_id, token_accumulator=self._token_accumulator).run(
            route=route_for_planner,
            accommodations=all_accommodations,
            activities=all_research,
        )

        # Merge all accommodation options into each stop
        for stop_dict in plan.get("stops", []):
            sid = stop_dict.get("id")
            stop_dict["all_accommodation_options"] = (pre_all_accommodation_options or {}).get(str(sid), [])

        await debug_logger.log(LogLevel.SUCCESS, "Reiseplan fertig!", job_id=job_id)

        # Inject token counts as internal metadata (before job_complete so they're in the initial payload)
        total_in  = sum(e["input"]  for e in self._token_accumulator)
        total_out = sum(e["output"] for e in self._token_accumulator)
        plan["_token_counts"] = {
            "total_input_tokens":  total_in,
            "total_output_tokens": total_out,
            "total_tokens":        total_in + total_out,
        }

        # Phase 4 kicks off AFTER job_complete so the guide is visible immediately
        plan["trip_analysis"] = None

        # Send job_complete — frontend shows the guide now
        await self.progress("job_complete", None, plan, 100)

        # Phase 4: Reise-Analyse (runs in background while user views the guide)
        await debug_logger.log(LogLevel.INFO, i18n_t("progress.analysis_start", lang),
                               job_id=job_id, message_key="progress.analysis_start")
        try:
            analysis_result = await TripAnalysisAgent(req, job_id, token_accumulator=self._token_accumulator).run(plan, req)
            plan["trip_analysis"] = analysis_result
        except Exception as exc:
            await debug_logger.log(LogLevel.WARNING,
                f"Reise-Analyse fehlgeschlagen (nicht kritisch): {exc}", job_id=job_id,
                message_key="progress.analysis_failed")
            plan["trip_analysis"] = None

        # Notify frontend of analysis result (null if failed — frontend guards on this)
        await self.progress("analysis_complete", None, {"trip_analysis": plan["trip_analysis"]}, 100)

        # Persist the merged plan (with trip_analysis) back to Redis so saved travels are complete
        job = self._load_job()
        job["plan"] = plan
        self._save_job(job)

        return plan
