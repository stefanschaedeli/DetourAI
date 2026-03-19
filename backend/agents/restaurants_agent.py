from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_restaurants as gp_search_restaurants, place_photo_url
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "restaurants"

SYSTEM_PROMPT = (
    "Du bist ein Restaurantberater für Reisende. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class RestaurantsAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict) -> dict:
        req = self.request
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        persons = req.adults + len(req.children)
        total_days = req.total_days if req.total_days > 0 else 1
        budget_per_meal = round(req.budget_chf * 0.15 / persons / total_days, 2)
        children_count = len(req.children)

        # Pre-fetch: echte Restaurantdaten
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""

        if lat and lon:
            gp_results = await gp_search_restaurants(lat, lon, radius_m=req.activities_radius_km * 1000)
            if gp_results:
                lines = []
                for r in gp_results[:8]:
                    price = "€" * r.get("price_level", 2) if r.get("price_level") else "?"
                    lines.append(f"- {r['name']} | ★{r.get('rating','?')} ({r.get('user_ratings_total',0)} Bewertungen) | {r.get('address','')} | Preisniveau: {price}")
                real_data_block = "\n\nEchte Restaurants in der Nähe (Google Places Daten):\n" + "\n".join(lines) + "\nWähle aus diesen echten Restaurants und ergänze mit deinem Wissen.\n"

        if not real_data_block:
            brave_results = await search_places(f"restaurants {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}★) — {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = "\n\nEchte Suchergebnisse für Restaurants in der Region:\n" + "\n".join(lines) + "\nBevorzuge diese echten Orte in deiner Empfehlung.\n"

        prompt = f"""Empfehle Restaurants in {region}, {country}:

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Suchradius: {req.activities_radius_km} km
Max. Restaurants: {req.max_restaurants_per_stop}
Budget pro Mahlzeit/Person: ca. CHF {budget_per_meal:.0f}

WICHTIG: Alle Restaurants müssen innerhalb des Suchradius von {req.activities_radius_km} km vom Übernachtungsort in {region} liegen. Keine Ausnahmen.

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "restaurants": [
    {{
      "name": "...",
      "cuisine": "Französisch",
      "price_range": "€€",
      "family_friendly": true,
      "notes": "..."
    }}
  ]
}}{real_data_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Restaurants: {region})",
            job_id=self.job_id, agent="RestaurantsAgent",
        )
        await debug_logger.log_prompt("RestaurantsAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 1024),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RestaurantsAgent",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text
        result = parse_agent_json(text)

        # Bilder: Google Places Photo wenn verfügbar, sonst Stub
        if lat and lon:
            gp_results = await gp_search_restaurants(lat, lon, radius_m=req.activities_radius_km * 1000)
            gp_map = {r["name"].lower(): r for r in gp_results} if gp_results else {}
        else:
            gp_map = {}

        for restaurant in result.get("restaurants", []):
            matched = gp_map.get(restaurant.get("name", "").lower())
            if matched and matched.get("photo_reference"):
                restaurant["image_overview"] = place_photo_url(matched["photo_reference"])
                restaurant["image_mood"] = None
                restaurant["image_customer"] = None
            else:
                images = await fetch_unsplash_images(
                    f"{restaurant.get('name', '')} {region} {restaurant.get('cuisine', '')}",
                    "restaurant",
                )
                restaurant.update(images)
            if matched and matched.get("place_id"):
                restaurant["place_id"] = matched["place_id"]

        return result
