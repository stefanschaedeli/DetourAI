import asyncio
from datetime import date, timedelta
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.maps_helper import geocode_google, google_directions_simple, build_maps_url
from utils.weather import get_forecast
from utils.currency import detect_currency, get_chf_rate
from agents._client import get_client, get_model, get_max_tokens
from utils.settings_store import get_setting

AGENT_KEY = "day_planner"

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner. Erstelle einen detaillierten Tagesplan. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class DayPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

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

    async def _enrich_with_google(self, stops: list) -> list:
        """Geocode all locations, then enrich stops with real drive times via Google Directions."""
        req = self.request
        locations = [req.start_location] + [s.get("region", "") for s in stops]

        # Geocode all in parallel (no rate limit needed for Google)
        coords = await asyncio.gather(*[geocode_google(loc) for loc in locations])

        # Store start coords and place_id
        self._start_coords = (coords[0][0], coords[0][1]) if coords[0] else None
        self._start_place_id = coords[0][2] if coords[0] else None

        # Google Directions calls in parallel (using location strings)
        dir_tasks = []
        for i in range(1, len(locations)):
            prev_result = coords[i - 1]
            curr_result = coords[i]
            if prev_result and curr_result:
                dir_tasks.append(google_directions_simple(locations[i - 1], locations[i]))
            else:
                async def _zero(): return (0.0, 0.0)
                dir_tasks.append(_zero())

        results = await asyncio.gather(*[t if asyncio.iscoroutine(t) else t for t in dir_tasks],
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

            # Store lat/lng and place_id
            if i + 1 < len(coords) and coords[i + 1]:
                s["lat"], s["lng"] = coords[i + 1][0], coords[i + 1][1]
                s["place_id"] = coords[i + 1][2]

            start_pid = getattr(self, "_start_place_id", None) or ""
            s["google_maps_url"] = build_maps_url(
                [req.start_location, s.get("region", "")],
                place_ids=[start_pid, s.get("place_id", "")]
            )
            enriched.append(s)
        return enriched

    async def _enrich_with_weather(self, stops: list) -> list:
        """Wetter-Vorhersagen für alle Stopps laden."""
        req = self.request
        start_date = req.start_date
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)

        for stop in stops:
            lat = stop.get("lat")
            lng = stop.get("lng")
            if not lat or not lng:
                continue
            arrival_day = stop.get("arrival_day", 1)
            nights = stop.get("nights", 1)
            arr_date = start_date + timedelta(days=arrival_day - 1)
            dep_date = arr_date + timedelta(days=nights)
            weather = await get_forecast(lat, lng, arr_date.isoformat(), dep_date.isoformat())
            if weather:
                stop["weather_forecast"] = weather
        return stops

    def _fallback_cost_estimate(self, stops: list) -> dict:
        """Calculate cost estimate from stop data if Claude doesn't provide one."""
        req = self.request
        acc_total = 0.0
        for stop in stops:
            acc = stop.get("accommodation", {})
            if isinstance(acc, dict):
                acc_total += acc.get("total_price_chf", get_setting("budget.fallback_accommodation_chf") * stop.get("nights", 1))
            else:
                acc_total += get_setting("budget.fallback_accommodation_chf") * stop.get("nights", 1)

        activities_chf = get_setting("budget.fallback_activities_chf") * len(stops)
        total_nights = sum(s.get("nights", 1) for s in stops)
        food_chf = get_setting("budget.fallback_food_chf") * total_nights
        total_drive = sum(s.get("drive_hours_from_prev", 0) for s in stops)
        fuel_chf = total_drive * get_setting("budget.fuel_chf_per_hour")

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

    def _distribute_per_stop(self, day_contexts: list) -> None:
        """Verteile Aktivitäten/Restaurants auf Tage am gleichen Stopp (Round-Robin).

        Mutiert day_contexts in-place: reduziert activities/restaurants pro Tag
        und fügt other_days_hint, day_of_stay, total_days_at_stop hinzu.
        """
        # Gruppiere nach Region
        from collections import defaultdict
        groups: dict[str, list[int]] = defaultdict(list)
        for i, ctx in enumerate(day_contexts):
            groups[ctx.get("region", "")].append(i)

        for region, indices in groups.items():
            if len(indices) <= 1:
                continue

            # Sortiere nach Tag-Nummer
            indices.sort(key=lambda i: day_contexts[i]["day"])
            total = len(indices)

            # Alle Tage teilen sich denselben Pool (vom ersten Tag kopiert)
            all_activities = list(day_contexts[indices[0]].get("activities", []))
            all_restaurants = list(day_contexts[indices[0]].get("restaurants", []))

            # Round-Robin: Ankunftstag (drive_hours > 0) bekommt letzte Priorität
            arrival_indices = [i for i in indices if day_contexts[i].get("drive_hours", 0) > 0]
            rest_indices = [i for i in indices if day_contexts[i].get("drive_hours", 0) <= 0]
            ordered = rest_indices + arrival_indices  # Ruhetage zuerst

            # Aktivitäten verteilen
            act_buckets: dict[int, list] = {i: [] for i in indices}
            for idx, act in enumerate(all_activities):
                target = ordered[idx % len(ordered)]
                act_buckets[target].append(act)

            # Restaurants: mindestens 1 pro Tag, Rest Round-Robin
            rest_buckets: dict[int, list] = {i: [] for i in indices}
            if all_restaurants:
                # Erst jedem Tag ein Restaurant geben
                for j, i in enumerate(ordered):
                    if j < len(all_restaurants):
                        rest_buckets[i].append(all_restaurants[j])
                # Übrige verteilen
                remaining = all_restaurants[len(ordered):]
                for idx, rest in enumerate(remaining):
                    target = ordered[idx % len(ordered)]
                    rest_buckets[target].append(rest)

            # Zuweisen + Hints bauen
            day_assignments: dict[int, dict] = {}
            for rank, i in enumerate(indices):
                ctx = day_contexts[i]
                ctx["activities"] = act_buckets[i]
                ctx["restaurants"] = rest_buckets[i]
                ctx["day_of_stay"] = rank + 1
                ctx["total_days_at_stop"] = total
                # Sammle Namen für Hint
                act_names = [a.get("name", "") for a in act_buckets[i] if a.get("name")]
                day_assignments[i] = {
                    "day": ctx["day"],
                    "acts": act_names,
                }

            # other_days_hint für jeden Tag
            for i in indices:
                other_parts = []
                for j in indices:
                    if j == i:
                        continue
                    info = day_assignments[j]
                    if info["acts"]:
                        other_parts.append(f"Tag {info['day']}: {', '.join(info['acts'])}")
                day_contexts[i]["other_days_hint"] = " | ".join(other_parts)

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

        # Wetter für diesen Tag
        weather_block = ""
        weather_forecast = day_ctx.get("weather_forecast", [])
        if weather_forecast:
            for w in weather_forecast:
                if w.get("date") == day_ctx.get("date_iso"):
                    weather_block = (
                        f"\nWetter am {w['date']}: {w['description']}, "
                        f"{w['temp_max']}°C / {w['temp_min']}°C, "
                        f"Niederschlag: {w['precipitation_mm']}mm\n"
                        f"Passe den Tagesplan ans Wetter an (bei Regen: Indoor-Aktivitäten bevorzugen).\n"
                    )
                    break

        prompt = f"""Erstelle einen stündlichen Tagesplan für Tag {day_num} ({date_str}):

Region: {region}
Abfahrt von: {prev_region}
Fahrtzeit: {drive_hours:.1f}h
Aktivitäten: {acts_str or 'keine spezifischen'}
Restaurants: {rests_str or 'keine spezifischen'}
Reisende: {self.request.adults} Erwachsene{f', {len(self.request.children)} Kinder' if self.request.children else ''}
{weather_block}
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

        # Mehrtägiger Aufenthalt: Kontext zu anderen Tagen
        other_days_hint = day_ctx.get("other_days_hint", "")
        if other_days_hint:
            prompt += (
                f"\n\nAndere Tage in {region} decken ab: {other_days_hint}\n"
                f"Plane NUR die dir zugewiesenen Aktivitäten/Restaurants. "
                f"Keine Überschneidungen."
            )

        day_of_stay = day_ctx.get("day_of_stay")
        total_days_at_stop = day_ctx.get("total_days_at_stop")
        if total_days_at_stop and total_days_at_stop > 1:
            prompt += f"\nDies ist Tag {day_of_stay} von {total_days_at_stop} in {region}."

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Tagesplan Tag {day_num}: {region})",
            job_id=self.job_id, agent="DayPlanner",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
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

        await debug_logger.log(LogLevel.INFO, "Google-Anreicherung startet", job_id=self.job_id, agent="DayPlanner")
        stops = await self._enrich_with_google(stops)

        # Wetter-Anreicherung für alle Stopps
        await debug_logger.log(LogLevel.INFO, "Wetter-Anreicherung startet", job_id=self.job_id, agent="DayPlanner")
        stops = await self._enrich_with_weather(stops)

        # Build overview Google Maps URL
        all_locations = [req.start_location] + [s.get("region", "") for s in stops]
        all_place_ids = [getattr(self, "_start_place_id", "") or ""] + [s.get("place_id", "") for s in stops]
        overview_url = build_maps_url(all_locations, place_ids=all_place_ids)

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

            weather_forecast = stop.get("weather_forecast", [])

            # Arrival day (drive day)
            arrival_date = start_date + timedelta(days=arrival_day - 1)
            day_contexts.append({
                "day": arrival_day,
                "date": arrival_date.strftime("%d.%m.%Y"),
                "date_iso": arrival_date.isoformat(),
                "region": region,
                "drive_hours": drive_hours,
                "activities": acts,
                "restaurants": rests,
                "prev_region": prev_region,
                "weather_forecast": weather_forecast,
            })

            # Rest/activity days at this stop
            for night_offset in range(1, nights):
                rest_day = arrival_day + night_offset
                rest_date = start_date + timedelta(days=rest_day - 1)
                day_contexts.append({
                    "day": rest_day,
                    "date": rest_date.strftime("%d.%m.%Y"),
                    "date_iso": rest_date.isoformat(),
                    "region": region,
                    "drive_hours": 0,
                    "activities": acts,
                    "restaurants": rests,
                    "prev_region": region,
                    "weather_forecast": weather_forecast,
                })

        # Aktivitäten/Restaurants auf Tage am gleichen Stopp verteilen
        self._distribute_per_stop(day_contexts)

        # Plan all days in parallel
        await debug_logger.log(LogLevel.INFO, f"Erstelle {len(day_contexts)} Tagespläne parallel", job_id=self.job_id, agent="DayPlanner")
        day_plan_results = await asyncio.gather(*[self._plan_single_day(ctx) for ctx in day_contexts])

        # Sort by day number and add Google Maps route URLs
        day_plans = sorted(day_plan_results, key=lambda d: d.get("day", 0))
        region_pid = {s.get("region", ""): s.get("place_id", "") for s in stops}
        region_pid[req.start_location] = getattr(self, "_start_place_id", "") or ""
        for dp in day_plans:
            route_stops = dp.get("stops_on_route", [])
            if route_stops:
                route_pids = [region_pid.get(loc, "") for loc in route_stops]
                dp["google_maps_route_url"] = build_maps_url(route_stops, place_ids=route_pids)

        cost_estimate = self._fallback_cost_estimate(stops)

        await debug_logger.log(LogLevel.SUCCESS, "DayPlanner abgeschlossen", job_id=self.job_id, agent="DayPlanner")

        start_coords = getattr(self, "_start_coords", None)
        return {
            "job_id": self.job_id,
            "start_location": req.start_location,
            "start_lat": start_coords[0] if start_coords else None,
            "start_lng": start_coords[1] if start_coords else None,
            "start_place_id": getattr(self, "_start_place_id", None),
            "stops": stops,
            "day_plans": day_plans,
            "cost_estimate": cost_estimate,
            "google_maps_overview_url": overview_url,
            "outputs": {},
        }
