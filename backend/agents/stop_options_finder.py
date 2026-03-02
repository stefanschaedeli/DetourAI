from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner. Schlage genau 3 Zwischenstopps vor: direct, scenic, cultural. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class StopOptionsFinderAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5")

    async def find_options(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int = 0,
        segment_count: int = 1,
    ) -> dict:
        req = self.request

        prev_stop = selected_stops[-1]["region"] if selected_stops else req.start_location
        prev_country = selected_stops[-1].get("country", "") if selected_stops else "CH"

        stops_str = ""
        if selected_stops:
            parts = [f"Stop {s['id']}: {s['region']} ({s.get('country','?')}, {s.get('nights',1)} Nächte)"
                     for s in selected_stops]
            stops_str = "Bisherige Stopps: " + ", ".join(parts) + "\n"

        complete_hint = ""
        if route_could_be_complete:
            complete_hint = (
                f"\nHinweis: Die Route könnte mit diesem Stop abgeschlossen werden "
                f"(Ziel: {segment_target}). Mindestens eine Option sollte direkt zum Ziel führen.\n"
            )

        prompt = f"""Segment {segment_index + 1} von {segment_count} Richtung: {segment_target}

Start: {req.start_location}
Aktueller Stop #{stop_number}
Letzter Stop: {prev_stop}
Endziel des Segments: {segment_target}
{stops_str}
Verbleibende Tage im Segment: {days_remaining}
Maximale Fahrzeit pro Tag: {req.max_drive_hours_per_day}h
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder' if req.children else ''}
{complete_hint}
Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor:
- option_type "direct": kürzeste Route Richtung {segment_target}
- option_type "scenic": landschaftlich schöne Alternative
- option_type "cultural": kulturell interessante Alternative

Fahrzeit muss ≤ {req.max_drive_hours_per_day}h sein.
Nächte: {req.min_nights_per_stop}–{req.max_nights_per_stop}.

Gib exakt dieses JSON zurück:
{{
  "options": [
    {{"id": 1, "option_type": "direct", "region": "...", "country": "FR", "drive_hours": 3.5, "nights": 2, "highlights": ["...", "..."], "teaser": "..."}},
    {{"id": 2, "option_type": "scenic", "region": "...", "country": "FR", "drive_hours": 4.0, "nights": 2, "highlights": ["...", "..."], "teaser": "..."}},
    {{"id": 3, "option_type": "cultural", "region": "...", "country": "FR", "drive_hours": 3.0, "nights": 2, "highlights": ["...", "..."], "teaser": "..."}}
  ],
  "estimated_total_stops": 4,
  "route_could_be_complete": false
}}"""

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")
        await debug_logger.log_prompt("StopOptionsFinder", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="StopOptionsFinder")
        text = response.content[0].text
        # Return Claude's result immediately — no Nominatim/OSRM validation here.
        # Drive times on option cards are for display only; the authoritative
        # OSRM enrichment runs later in DayPlannerAgent._enrich_with_osrm().
        return parse_agent_json(text)
