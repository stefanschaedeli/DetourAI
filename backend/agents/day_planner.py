"""Agent that builds a detailed hourly day-by-day travel plan, enriched with Google Directions, weather data, and cost estimates."""

import asyncio
from datetime import date, timedelta
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.maps_helper import geocode_google, google_directions_with_ferry, build_maps_url
from utils.weather import get_forecast
from utils.currency import detect_currency, get_chf_rate
from agents._client import get_client, get_model, get_max_tokens
from utils.settings_store import get_setting

AGENT_KEY = "day_planner"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Reiseplaner. Erstelle einen detaillierten Tagesplan. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a travel planner. Create a detailed daily plan. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक यात्रा योजनाकार हैं। एक विस्तृत दैनिक योजना बनाएं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class DayPlannerAgent:
    """Agent that produces an hourly day plan for every trip day, combining stop/accommodation/activity data with real drive times and weather."""

    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
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
                dir_tasks.append(google_directions_with_ferry(locations[i - 1], locations[i]))
            else:
                async def _zero(): return (0.0, 0.0, "", False)
                dir_tasks.append(_zero())

        results = await asyncio.gather(*[t if asyncio.iscoroutine(t) else t for t in dir_tasks],
                                       return_exceptions=True)

        enriched = []
        for i, stop in enumerate(stops):
            s = dict(stop)
            if i < len(results) and not isinstance(results[i], BaseException):
                hours, km, _, is_ferry = results[i]  # type: ignore[misc]
                s["drive_hours_from_prev"] = hours if hours > 0 else s.get("drive_hours_from_prev", 0)
                s["drive_km_from_prev"] = km if km > 0 else s.get("drive_km_from_prev", 0)
                if is_ferry:
                    s["is_ferry"] = True
                    s["ferry_hours"] = round(hours, 1)
                    s["ferry_cost_chf"] = round(50.0 + km * 0.5, 2)
                else:
                    s["is_ferry"] = False
                    s["ferry_hours"] = None
                    s["ferry_cost_chf"] = None
            else:
                s.setdefault("drive_hours_from_prev", 0)
                s.setdefault("drive_km_from_prev", 0)
                s["is_ferry"] = False
                s["ferry_hours"] = None
                s["ferry_cost_chf"] = None

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
        """Fetch weather forecasts for each stop and attach them to the stop dict."""
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

        # Ferry cost computation (D-12)
        ferry_chf = 0.0
        for stop in stops:
            if stop.get("is_ferry") or stop.get("ferry_hours"):
                ferry_km = stop.get("ferry_km", stop.get("drive_km_from_prev", 0))
                # Rough formula: CHF 50 base + CHF 0.5/km (converted from EUR estimate)
                ferry_chf += 50.0 + (ferry_km * 0.5)

        total = acc_total + activities_chf + food_chf + fuel_chf + ferry_chf
        return {
            "accommodations_chf": round(acc_total, 2),
            "ferries_chf": round(ferry_chf, 2),
            "activities_chf": round(activities_chf, 2),
            "food_chf": round(food_chf, 2),
            "fuel_chf": round(fuel_chf, 2),
            "total_chf": round(total, 2),
            "budget_remaining_chf": round(req.budget_chf - total, 2),
        }

    def _distribute_per_stop(self, day_contexts: list) -> None:
        """Distribute activities and restaurants across multiple days at the same stop via round-robin.

        Mutates day_contexts in-place: assigns per-day activity/restaurant subsets and adds
        other_days_hint, day_of_stay, and total_days_at_stop fields for prompt context.
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
        """Plan one day's hourly schedule via a single Claude call, incorporating weather, ferry, and multi-day-stop context."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])

        day_num = day_ctx["day"]
        date_str = day_ctx["date"]
        region = day_ctx.get("region", "")
        drive_hours = day_ctx.get("drive_hours", 0)
        activities = day_ctx.get("activities", [])
        restaurants = day_ctx.get("restaurants", [])
        prev_region = day_ctx.get("prev_region", req.start_location)

        acts_str = ", ".join(f"{a['name']} ({a.get('duration_hours', 2)}h)" for a in activities[:4])
        rests_str = ", ".join(f"{r['name']} ({r.get('cuisine', '')})" for r in restaurants[:3])

        _L = {
            "de": {
                "weather_on": "Wetter am", "precipitation": "Niederschlag",
                "weather_adapt": "Passe den Tagesplan ans Wetter an (bei Regen: Indoor-Aktivitäten bevorzugen).",
                "ferry": "FAEHRE: Dieser Tag beinhaltet eine Faehrueberfahrt von {h} Stunden. Verbleibende Fahrzeit nach der Faehre: {r}h. Plane die Faehre als eigenen time_block mit activity_type 'ferry' ein.",
                "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
                "create_plan": "Erstelle einen stündlichen Tagesplan für Tag",
                "region": "Region", "departure": "Abfahrt von", "drive_time": "Fahrtzeit",
                "activities": "Aktivitäten", "restaurants": "Restaurants",
                "none_specific": "keine spezifischen",
                "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder",
                "start_at": "Starte um 08:00 Uhr. Erstelle einen realistischen Zeitplan.",
                "title_short": "Kurzer Tages-Titel",
                "desc_day": "2-3 Sätze Beschreibung des Tages",
                "departure_to": "Abfahrt nach",
                "road": "Autoroute / Hauptstrasse",
                "drive_from": "Fahrt von {prev} nach {region}",
                "lunch": "Mittagessen",
                "local_cuisine": "Lokale Küche geniessen",
                "adapt": "Passe die time_blocks realistisch an den Tag an. activity_type kann sein: drive, activity, meal, break, check_in.",
                "other_days": "Andere Tage in {region} decken ab:",
                "plan_only": "Plane NUR die dir zugewiesenen Aktivitäten/Restaurants. Keine Überschneidungen.",
                "day_of": "Dies ist Tag {d} von {t} in {region}.",
            },
            "en": {
                "weather_on": "Weather on", "precipitation": "Precipitation",
                "weather_adapt": "Adapt the daily plan to the weather (in case of rain: prefer indoor activities).",
                "ferry": "FERRY: This day includes a ferry crossing of {h} hours. Remaining drive time after the ferry: {r}h. Plan the ferry as its own time_block with activity_type 'ferry'.",
                "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
                "create_plan": "Create an hourly daily plan for day",
                "region": "Region", "departure": "Departure from", "drive_time": "Drive time",
                "activities": "Activities", "restaurants": "Restaurants",
                "none_specific": "none specific",
                "travelers": "Travelers", "adults": "adults", "children": "children",
                "start_at": "Start at 08:00. Create a realistic schedule.",
                "title_short": "Short day title",
                "desc_day": "2-3 sentence description of the day",
                "departure_to": "Departure to",
                "road": "Highway / Main road",
                "drive_from": "Drive from {prev} to {region}",
                "lunch": "Lunch",
                "local_cuisine": "Enjoy local cuisine",
                "adapt": "Adapt the time_blocks realistically to the day. activity_type can be: drive, activity, meal, break, check_in.",
                "other_days": "Other days in {region} cover:",
                "plan_only": "Plan ONLY the activities/restaurants assigned to you. No overlaps.",
                "day_of": "This is day {d} of {t} in {region}.",
            },
            "hi": {
                "weather_on": "मौसम", "precipitation": "वर्षा",
                "weather_adapt": "मौसम के अनुसार दैनिक योजना अनुकूलित करें (बारिश में: इनडोर गतिविधियों को प्राथमिकता दें)।",
                "ferry": "नौका: इस दिन {h} घंटे की नौका क्रॉसिंग शामिल है। नौका के बाद शेष ड्राइव समय: {r}h।",
                "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
                "create_plan": "दिन के लिए प्रति घंटा दैनिक योजना बनाएं",
                "region": "क्षेत्र", "departure": "से प्रस्थान", "drive_time": "ड्राइव समय",
                "activities": "गतिविधियां", "restaurants": "रेस्तरां",
                "none_specific": "कोई विशिष्ट नहीं",
                "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे",
                "start_at": "08:00 बजे शुरू करें। एक यथार्थवादी समय सारिणी बनाएं।",
                "title_short": "छोटा दैनिक शीर्षक",
                "desc_day": "दिन का 2-3 वाक्य विवरण",
                "departure_to": "की ओर प्रस्थान",
                "road": "राजमार्ग / मुख्य सड़क",
                "drive_from": "{prev} से {region} तक ड्राइव",
                "lunch": "दोपहर का भोजन",
                "local_cuisine": "स्थानीय व्यंजनों का आनंद लें",
                "adapt": "time_blocks को दिन के अनुसार यथार्थवादी रूप से अनुकूलित करें। activity_type हो सकता है: drive, activity, meal, break, check_in।",
                "other_days": "{region} में अन्य दिन कवर करते हैं:",
                "plan_only": "केवल आपको सौंपी गई गतिविधियां/रेस्तरां की योजना बनाएं। कोई ओवरलैप नहीं।",
                "day_of": "यह {region} में {t} में से दिन {d} है।",
            },
        }
        DL = _L.get(lang, _L["de"])

        # Wetter für diesen Tag
        weather_block = ""
        weather_forecast = day_ctx.get("weather_forecast", [])
        if weather_forecast:
            for w in weather_forecast:
                if w.get("date") == day_ctx.get("date_iso"):
                    weather_block = (
                        f"\n{DL['weather_on']} {w['date']}: {w['description']}, "
                        f"{w['temp_max']}\u00b0C / {w['temp_min']}\u00b0C, "
                        f"{DL['precipitation']}: {w['precipitation_mm']}mm\n"
                        f"{DL['weather_adapt']}\n"
                    )
                    break

        # Ferry time deduction (D-11)
        ferry_info = ""
        if day_ctx.get("is_ferry") or day_ctx.get("ferry_hours"):
            ferry_hours = day_ctx.get("ferry_hours", 0)
            remaining_drive = max(0, req.max_drive_hours_per_day - ferry_hours)
            ferry_info = "\n" + DL["ferry"].format(h=f"{ferry_hours:.1f}", r=f"{remaining_drive:.1f}") + "\n"

        desc_line = f"\n{DL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{DL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{DL['mandatory_label']}: {', '.join(f'{a.name}' + (f' ({a.location})' if a.location else '') for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        children_str = f", {len(req.children)} {DL['children']}" if req.children else ""

        prompt = f"""{DL['create_plan']} {day_num} ({date_str}):

{DL['region']}: {region}
{DL['departure']}: {prev_region}
{DL['drive_time']}: {drive_hours:.1f}h
{DL['activities']}: {acts_str or DL['none_specific']}
{DL['restaurants']}: {rests_str or DL['none_specific']}
{DL['travelers']}: {req.adults} {DL['adults']}{children_str}{mandatory_line}{pref_line}{desc_line}
{weather_block}{ferry_info}
{DL['start_at']}

{{
  "day": {day_num},
  "date": "{date_str}",
  "type": "mixed",
  "title": "{DL['title_short']}",
  "description": "{DL['desc_day']}",
  "stops_on_route": ["{prev_region}", "{region}"],
  "time_blocks": [
    {{
      "time": "08:00",
      "activity_type": "drive",
      "title": "{DL['departure_to']} {region}",
      "location": "{DL['road']}",
      "duration_minutes": {int(drive_hours * 60) if drive_hours > 0 else 0},
      "description": "{DL['drive_from'].format(prev=prev_region, region=region)}",
      "google_maps_url": null,
      "google_search_url": null,
      "price_chf": null
    }},
    {{
      "time": "12:30",
      "activity_type": "meal",
      "title": "{DL['lunch']}",
      "location": "{region}",
      "duration_minutes": 60,
      "description": "{DL['local_cuisine']}",
      "google_search_url": "https://www.google.com/search?q=restaurant+{region.replace(' ', '+').lower()}",
      "google_maps_url": null,
      "price_chf": 35.0
    }}
  ]
}}

{DL['adapt']}"""

        # Mehrtägiger Aufenthalt: Kontext zu anderen Tagen
        other_days_hint = day_ctx.get("other_days_hint", "")
        if other_days_hint:
            prompt += (
                f"\n\n{DL['other_days'].format(region=region)} {other_days_hint}\n"
                f"{DL['plan_only']}"
            )

        day_of_stay = day_ctx.get("day_of_stay")
        total_days_at_stop = day_ctx.get("total_days_at_stop")
        if total_days_at_stop and total_days_at_stop > 1:
            prompt += "\n" + DL["day_of"].format(d=day_of_stay, t=total_days_at_stop, region=region)

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Tagesplan Tag {day_num}: {region})",
            job_id=self.job_id, agent="DayPlanner",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        try:
            response = await call_with_retry(call, job_id=self.job_id, agent_name="DayPlanner",
                                             token_accumulator=self.token_accumulator)
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
        """Orchestrate the full day-planning pipeline: merge stops, enrich with Google/weather, distribute activities, plan each day in parallel."""
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
                "is_ferry": stop.get("is_ferry", False),
                "ferry_hours": stop.get("ferry_hours", 0),
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
