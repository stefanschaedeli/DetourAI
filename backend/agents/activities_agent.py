import asyncio
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_attractions, place_photo_url
from utils.weather import get_forecast
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Aktivitätsberater für Reisende. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class ActivitiesAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5")

    async def run_stop(self, stop: dict) -> dict:
        req = self.request
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)
        children_count = len(req.children)

        budget_per_stop = req.budget_chf * 0.15 / max(1, req.total_days) * nights

        # Pre-fetch: echte Sehenswürdigkeiten und Wetter
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""
        weather_block = ""

        if lat and lon:
            gp_results = await search_attractions(lat, lon, radius_m=req.activities_radius_km * 1000)
            if gp_results:
                lines = [f"- {a['name']} | ★{a.get('rating','?')} ({a.get('user_ratings_total',0)} Bewertungen) | {a.get('address','')}" for a in gp_results[:8]]
                real_data_block = "\n\nEchte Sehenswürdigkeiten in der Nähe (Google Places Daten):\n" + "\n".join(lines) + "\nBevorzuge diese echten Orte und ergänze mit deinem Wissen.\n"

            # Wetter für wetterangepasste Empfehlungen
            arrival_day = stop.get("arrival_day", 1)
            start_date = req.start_date
            if hasattr(start_date, "isoformat"):
                from datetime import timedelta
                arr_date = start_date + timedelta(days=arrival_day - 1)
                dep_date = arr_date + timedelta(days=nights)
                weather = await get_forecast(lat, lon, arr_date.isoformat(), dep_date.isoformat())
                if weather:
                    lines = [f"- {w['date']}: {w['description']}, {w['temp_max']}°C/{w['temp_min']}°C, Niederschlag: {w['precipitation_mm']}mm" for w in weather]
                    weather_block = "\n\nWettervorhersage für den Aufenthalt:\n" + "\n".join(lines) + "\nPasse Empfehlungen ans Wetter an (bei Regen: Indoor-Aktivitäten bevorzugen).\n"

        if not real_data_block:
            brave_results = await search_places(f"Sehenswürdigkeiten {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}★) — {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = "\n\nEchte Suchergebnisse für Aktivitäten:\n" + "\n".join(lines) + "\nBevorzuge diese echten Orte.\n"

        prompt = f"""Finde die besten Aktivitäten in {region}, {country}:

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Aufenthalt: {nights} Nächte
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Suchradius: {req.activities_radius_km} km
Max. Aktivitäten: {req.max_activities_per_stop}
Aktivitätenbudget: ca. CHF 80 pro Person
{f'Pflichtaktivitäten: {", ".join(a.name for a in req.mandatory_activities)}' if req.mandatory_activities else ''}

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "top_activities": [
    {{
      "name": "...",
      "description": "...",
      "duration_hours": 2.0,
      "price_chf": 25.0,
      "suitable_for_children": true,
      "notes": "...",
      "address": "...",
      "google_maps_url": "https://maps.google.com/?q=..."
    }}
  ]
}}{real_data_block}{weather_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Aktivitäten: {region})",
            job_id=self.job_id, agent="ActivitiesAgent",
        )
        await debug_logger.log_prompt("ActivitiesAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ActivitiesAgent")
        text = response.content[0].text
        result = parse_agent_json(text)

        activities = result.get("top_activities", [])
        if lat and lon:
            gp_results = await search_attractions(lat, lon, radius_m=req.activities_radius_km * 1000)
            gp_map = {a["name"].lower(): a for a in gp_results} if gp_results else {}
        else:
            gp_map = {}

        for activity in activities:
            matched = gp_map.get(activity.get("name", "").lower())
            if matched and matched.get("photo_reference"):
                activity["image_overview"] = place_photo_url(matched["photo_reference"])
                activity["image_mood"] = None
                activity["image_customer"] = None
            else:
                images = await fetch_unsplash_images(
                    f"{activity.get('name', '')} {region}", "activity"
                )
                activity.update(images)

        result["top_activities"] = activities
        return result
