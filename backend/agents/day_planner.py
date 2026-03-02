import asyncio
from datetime import date, timedelta
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.maps_helper import geocode_nominatim, osrm_route, build_maps_url
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner. Erstelle einen detaillierten Tagesplan. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class DayPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5")

    def _build_stops(self, route: dict, accommodations: list, activities: list) -> list:
        """Merge route stops with accommodation and activity data."""
        stops = route.get("stops", []) if isinstance(route, dict) else list(route)

        # Build lookup maps
        acc_map = {a["stop_id"]: a["option"] for a in accommodations if "stop_id" in a}
        act_map = {}
        rest_map = {}
        for item in activities:
            sid = item.get("stop_id")
            if sid is not None:
                if "top_activities" in item:
                    act_map[sid] = item["top_activities"]
                if "restaurants" in item:
                    rest_map[sid] = item["restaurants"]

        enriched = []
        for stop in stops:
            sid = stop.get("id")
            enriched_stop = dict(stop)
            # Normalize drive_hours field
            if "drive_hours" in enriched_stop and "drive_hours_from_prev" not in enriched_stop:
                enriched_stop["drive_hours_from_prev"] = enriched_stop.pop("drive_hours")
            if sid in acc_map:
                enriched_stop["accommodation"] = acc_map[sid]
            if sid in act_map:
                enriched_stop["top_activities"] = act_map[sid]
            if sid in rest_map:
                enriched_stop["restaurants"] = rest_map[sid]
            enriched.append(enriched_stop)
        return enriched

    async def _enrich_with_osrm(self, stops: list) -> list:
        """Geocode all locations, then enrich stops with real drive times via OSRM."""
        req = self.request
        locations = [req.start_location] + [s.get("region", "") for s in stops]

        # Geocode sequentially with 350ms delay
        coords = []
        for loc in locations:
            coords.append(await geocode_nominatim(loc))
            await asyncio.sleep(0.35)

        # OSRM calls in parallel
        osrm_tasks = []
        for i in range(1, len(coords)):
            prev = coords[i - 1]
            curr = coords[i]
            if prev and curr:
                osrm_tasks.append(osrm_route([prev, curr]))
            else:
                osrm_tasks.append(asyncio.coroutine(lambda: (0.0, 0.0))())

        results = await asyncio.gather(*[t if asyncio.iscoroutine(t) else t for t in osrm_tasks],
                                       return_exceptions=True)

        enriched = []
        for i, stop in enumerate(stops):
            s = dict(stop)
            if i < len(results) and not isinstance(results[i], Exception):
                hours, km = results[i]
                s["drive_hours_from_prev"] = hours if hours > 0 else s.get("drive_hours_from_prev", 0)
                s["drive_km_from_prev"] = km if km > 0 else s.get("drive_km_from_prev", 0)
            else:
                s.setdefault("drive_hours_from_prev", 0)
                s.setdefault("drive_km_from_prev", 0)

            # Store lat/lng
            if i + 1 < len(coords) and coords[i + 1]:
                s["lat"], s["lng"] = coords[i + 1]

            # Google Maps URL for stop
            s["google_maps_url"] = build_maps_url([req.start_location, s.get("region", "")])

            enriched.append(s)
        return enriched

    def _fallback_cost_estimate(self, stops: list) -> dict:
        """Calculate cost estimate from stop data if Claude doesn't provide one."""
        req = self.request
        acc_total = 0.0
        for stop in stops:
            acc = stop.get("accommodation", {})
            if isinstance(acc, dict):
                acc_total += acc.get("total_price_chf", 120 * stop.get("nights", 1))
            else:
                acc_total += 120 * stop.get("nights", 1)

        activities_chf = 80.0 * len(stops)
        total_nights = sum(s.get("nights", 1) for s in stops)
        food_chf = 50.0 * total_nights
        total_drive = sum(s.get("drive_hours_from_prev", 0) for s in stops)
        fuel_chf = total_drive * 12.0

        total = acc_total + activities_chf + food_chf + fuel_chf
        return {
            "accommodations_chf": round(acc_total, 2),
            "ferries_chf": 0.0,
            "activities_chf": round(activities_chf, 2),
            "food_chf": round(food_chf, 2),
            "fuel_chf": round(fuel_chf, 2),
            "total_chf": round(total, 2),
            "budget_remaining_chf": round(req.budget_chf - total, 2),
        }

    async def run(self, route, accommodations: list, activities: list) -> dict:
        req = self.request

        await debug_logger.log(LogLevel.AGENT, "DayPlanner startet", job_id=self.job_id, agent="DayPlanner")

        stops = self._build_stops(route, accommodations, activities)

        await debug_logger.log(LogLevel.INFO, "OSRM-Anreicherung startet", job_id=self.job_id, agent="DayPlanner")
        stops = await self._enrich_with_osrm(stops)

        # Build overview Google Maps URL
        all_locations = [req.start_location] + [s.get("region", "") for s in stops]
        overview_url = build_maps_url(all_locations)

        # Prepare compact stops summary for Claude
        stops_summary = []
        for stop in stops:
            s = {
                "id": stop.get("id"),
                "region": stop.get("region"),
                "country": stop.get("country"),
                "arrival_day": stop.get("arrival_day"),
                "nights": stop.get("nights"),
                "drive_hours": stop.get("drive_hours_from_prev", 0),
                "accommodation": stop.get("accommodation", {}).get("name", "unbekannt") if stop.get("accommodation") else "unbekannt",
                "activities": [a.get("name") for a in stop.get("top_activities", [])[:3]],
            }
            stops_summary.append(s)

        start_date = req.start_date
        if isinstance(start_date, str):
            from datetime import date as date_cls
            start_date = date_cls.fromisoformat(start_date)

        prompt = f"""Erstelle einen Tagesplan für diese Reise:

Start: {req.start_location} am {start_date}
Stops: {stops_summary}
Gesamtbudget: CHF {req.budget_chf:,.0f}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder' if req.children else ''}

Gib exakt dieses JSON zurück:
{{
  "day_plans": [
    {{
      "day": 1,
      "date": "{start_date.strftime('%d.%m.%Y')}",
      "type": "drive",
      "title": "Abreise nach ...",
      "description": "...",
      "stops_on_route": ["...", "..."],
      "google_maps_route_url": null
    }}
  ],
  "cost_estimate": {{
    "accommodations_chf": 0,
    "ferries_chf": 0,
    "activities_chf": 0,
    "food_chf": 0,
    "fuel_chf": 0,
    "total_chf": 0,
    "budget_remaining_chf": 0
  }}
}}"""

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="DayPlanner")
        await debug_logger.log_prompt("DayPlanner", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="DayPlanner")
        text = response.content[0].text
        plan_data = parse_agent_json(text)

        day_plans = plan_data.get("day_plans", [])
        cost_estimate = plan_data.get("cost_estimate")

        # Add Google Maps route URLs to day plans
        for dp in day_plans:
            route_stops = dp.get("stops_on_route", [])
            if route_stops:
                dp["google_maps_route_url"] = build_maps_url(route_stops)

        if not cost_estimate or cost_estimate.get("total_chf", 0) == 0:
            cost_estimate = self._fallback_cost_estimate(stops)

        await debug_logger.log(LogLevel.SUCCESS, "DayPlanner abgeschlossen", job_id=self.job_id, agent="DayPlanner")

        return {
            "job_id": self.job_id,
            "start_location": req.start_location,
            "start_lat": None,
            "start_lng": None,
            "stops": stops,
            "day_plans": day_plans,
            "cost_estimate": cost_estimate,
            "google_maps_overview_url": overview_url,
            "outputs": {},
        }
