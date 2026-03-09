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

        # Store start coords for use in the final result
        self._start_coords = coords[0] if coords else None

        # OSRM calls in parallel
        osrm_tasks = []
        for i in range(1, len(coords)):
            prev = coords[i - 1]
            curr = coords[i]
            if prev and curr:
                osrm_tasks.append(osrm_route([prev, curr]))
            else:
                async def _zero(): return (0.0, 0.0)
                osrm_tasks.append(_zero())

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

    async def _plan_single_day(self, day_ctx: dict) -> dict:
        """Plan one day with a stündlicher Zeitstrahl via one Claude call."""
        day_num = day_ctx["day"]
        date_str = day_ctx["date"]
        region = day_ctx.get("region", "")
        drive_hours = day_ctx.get("drive_hours", 0)
        activities = day_ctx.get("activities", [])
        restaurants = day_ctx.get("restaurants", [])
        prev_region = day_ctx.get("prev_region", self.request.start_location)

        acts_str = ", ".join(f"{a['name']} ({a.get('duration_hours', 2)}h)" for a in activities[:4])
        rests_str = ", ".join(f"{r['name']} ({r.get('cuisine', '')})" for r in restaurants[:3])

        prompt = f"""Erstelle einen stündlichen Tagesplan für Tag {day_num} ({date_str}):

Region: {region}
Abfahrt von: {prev_region}
Fahrtzeit: {drive_hours:.1f}h
Aktivitäten: {acts_str or 'keine spezifischen'}
Restaurants: {rests_str or 'keine spezifischen'}
Reisende: {self.request.adults} Erwachsene{f', {len(self.request.children)} Kinder' if self.request.children else ''}

Starte um 08:00 Uhr. Erstelle einen realistischen Zeitplan.

Gib exakt dieses JSON zurück:
{{
  "day": {day_num},
  "date": "{date_str}",
  "type": "mixed",
  "title": "Kurzer Tages-Titel",
  "description": "2-3 Sätze Beschreibung des Tages",
  "stops_on_route": ["{prev_region}", "{region}"],
  "time_blocks": [
    {{
      "time": "08:00",
      "activity_type": "drive",
      "title": "Abfahrt nach {region}",
      "location": "Autoroute / Hauptstrasse",
      "duration_minutes": {int(drive_hours * 60) if drive_hours > 0 else 0},
      "description": "Fahrt von {prev_region} nach {region}",
      "google_maps_url": null,
      "google_search_url": null,
      "price_chf": null
    }},
    {{
      "time": "12:30",
      "activity_type": "meal",
      "title": "Mittagessen",
      "location": "{region}",
      "duration_minutes": 60,
      "description": "Lokale Küche geniessen",
      "google_search_url": "https://www.google.com/search?q=restaurant+{region.replace(' ', '+').lower()}",
      "google_maps_url": null,
      "price_chf": 35.0
    }}
  ]
}}

Passe die time_blocks realistisch an den Tag an. activity_type kann sein: drive, activity, meal, break, check_in."""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Tagesplan Tag {day_num}: {region})",
            job_id=self.job_id, agent="DayPlanner",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        try:
            response = await call_with_retry(call, job_id=self.job_id, agent_name="DayPlanner")
            text = response.content[0].text
            day_data = parse_agent_json(text)
            # Ensure time_blocks is always a list
            if "time_blocks" not in day_data:
                day_data["time_blocks"] = []
            return day_data
        except Exception as e:
            await debug_logger.log(LogLevel.WARNING, f"DayPlanner Tag {day_num} Fehler: {e}", job_id=self.job_id)
            return {
                "day": day_num,
                "date": date_str,
                "type": "mixed",
                "title": f"Tag {day_num}: {region}",
                "description": f"Aufenthalt in {region}",
                "stops_on_route": [region],
                "time_blocks": [],
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

        # Prepare per-day contexts for parallel Claude calls
        start_date = req.start_date
        if isinstance(start_date, str):
            from datetime import date as date_cls
            start_date = date_cls.fromisoformat(start_date)

        day_contexts = []
        for stop in stops:
            arrival_day = stop.get("arrival_day", 1)
            nights = stop.get("nights", 1)
            region = stop.get("region", "")
            drive_hours = stop.get("drive_hours_from_prev", 0)

            # Find previous stop region
            stop_idx = stops.index(stop)
            prev_region = stops[stop_idx - 1].get("region", req.start_location) if stop_idx > 0 else req.start_location

            acts = stop.get("top_activities", [])
            rests = stop.get("restaurants", [])

            # Arrival day (drive day)
            arrival_date = start_date + timedelta(days=arrival_day - 1)
            day_contexts.append({
                "day": arrival_day,
                "date": arrival_date.strftime("%d.%m.%Y"),
                "region": region,
                "drive_hours": drive_hours,
                "activities": acts,
                "restaurants": rests,
                "prev_region": prev_region,
            })

            # Rest/activity days at this stop
            for night_offset in range(1, nights):
                rest_day = arrival_day + night_offset
                rest_date = start_date + timedelta(days=rest_day - 1)
                day_contexts.append({
                    "day": rest_day,
                    "date": rest_date.strftime("%d.%m.%Y"),
                    "region": region,
                    "drive_hours": 0,
                    "activities": acts,
                    "restaurants": rests,
                    "prev_region": region,
                })

        # Plan all days in parallel
        await debug_logger.log(LogLevel.INFO, f"Erstelle {len(day_contexts)} Tagespläne parallel", job_id=self.job_id, agent="DayPlanner")
        day_plan_results = await asyncio.gather(*[self._plan_single_day(ctx) for ctx in day_contexts])

        # Sort by day number and add Google Maps route URLs
        day_plans = sorted(day_plan_results, key=lambda d: d.get("day", 0))
        for dp in day_plans:
            route_stops = dp.get("stops_on_route", [])
            if route_stops:
                dp["google_maps_route_url"] = build_maps_url(route_stops)

        cost_estimate = self._fallback_cost_estimate(stops)

        await debug_logger.log(LogLevel.SUCCESS, "DayPlanner abgeschlossen", job_id=self.job_id, agent="DayPlanner")

        start_coords = getattr(self, "_start_coords", None)
        return {
            "job_id": self.job_id,
            "start_location": req.start_location,
            "start_lat": start_coords[0] if start_coords else None,
            "start_lng": start_coords[1] if start_coords else None,
            "stops": stops,
            "day_plans": day_plans,
            "cost_estimate": cost_estimate,
            "google_maps_overview_url": overview_url,
            "outputs": {},
        }
