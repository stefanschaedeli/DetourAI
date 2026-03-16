from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.wikipedia import get_city_summary
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "travel_guide"

SYSTEM_PROMPT = (
    "Du bist ein erfahrener Reisejournalist. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class TravelGuideAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict, existing_activity_names: list) -> dict:
        req = self.request
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)

        existing_names_str = ", ".join(existing_activity_names) if existing_activity_names else "keine"

        # Wikipedia-Kontext vorladen
        wiki_block = ""
        wiki = await get_city_summary(region)
        if wiki and wiki.get("extract"):
            wiki_block = f"\n\nWikipedia-Zusammenfassung über {region}:\n{wiki['extract'][:500]}\nNutze diese Fakten als Grundlage für deinen Reiseführer.\n"

        prompt = f"""Schreibe einen Reiseführer für {region}, {country}:

Aufenthalt: {nights} Nächte
Reisende: {req.adults} Erwachsene{f', {len(req.children)} Kinder' if req.children else ''}
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Bereits geplante Aktivitäten (NICHT wiederholen): {existing_names_str}

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "travel_guide": {{
    "intro_narrative": "Lebendige, einladende Einleitung über {region} (3-4 Sätze)",
    "history_culture": "Geschichte und kulturelle Highlights",
    "food_specialties": "Lokale Spezialitäten und kulinarische Besonderheiten",
    "local_tips": "Praktische Tipps für den Aufenthalt",
    "insider_gems": "Geheimtipps jenseits der Touristenpfade",
    "best_time_to_visit": "Beste Reisezeit und saisonale Empfehlungen"
  }},
  "further_activities": [
    {{
      "name": "...",
      "description": "...",
      "duration_hours": 2.0,
      "price_chf": 0.0,
      "suitable_for_children": true,
      "notes": "...",
      "address": "...",
      "google_maps_url": "https://maps.google.com/?q=..."
    }}
  ]
}}

Schreibe alle Texte auf Deutsch. Gib 3-5 weitere Aktivitäten zurück, die sich von den bereits geplanten unterscheiden.{wiki_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Reiseführer: {region})",
            job_id=self.job_id, agent="TravelGuideAgent",
        )
        await debug_logger.log_prompt("TravelGuideAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TravelGuideAgent")
        text = response.content[0].text
        result = parse_agent_json(text)
        return result
