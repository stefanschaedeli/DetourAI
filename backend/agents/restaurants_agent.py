from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Restaurantberater für Reisende. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class RestaurantsAgent:
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

        persons = req.adults + len(req.children)
        total_days = req.total_days if req.total_days > 0 else 1
        budget_per_meal = round(req.budget_chf * 0.15 / persons / total_days, 2)
        children_count = len(req.children)

        prompt = f"""Empfehle Restaurants in {region}, {country}:

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Suchradius: {req.activities_radius_km} km
Max. Restaurants: {req.max_restaurants_per_stop}
Budget pro Mahlzeit/Person: ca. CHF {budget_per_meal:.0f}

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
}}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Restaurants: {region})",
            job_id=self.job_id, agent="RestaurantsAgent",
        )
        await debug_logger.log_prompt("RestaurantsAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RestaurantsAgent")
        text = response.content[0].text
        return parse_agent_json(text)
