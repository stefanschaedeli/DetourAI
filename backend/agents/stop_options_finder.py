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
        extra_instructions: str = "",
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

        has_children = bool(req.children)
        family_field = '"family_friendly": true,' if has_children else ""

        extra_hint = ""
        if extra_instructions:
            extra_hint = f"\nSonderwunsch des Nutzers: {extra_instructions}\n"

        prompt = f"""Segment {segment_index + 1} von {segment_count} Richtung: {segment_target}

Start: {req.start_location}
Aktueller Stop #{stop_number}
Letzter Stop: {prev_stop}
Endziel des Segments: {segment_target}
{stops_str}
Verbleibende Tage im Segment: {days_remaining}
Maximale Fahrzeit pro Tag: {req.max_drive_hours_per_day}h
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder (Alter: ' + ', '.join(str(c) for c in req.children) + ')' if req.children else ''}
{complete_hint}{extra_hint}
Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor:
- option_type "direct": kürzeste Route Richtung {segment_target}
- option_type "scenic": landschaftlich schöne Alternative
- option_type "cultural": kulturell interessante Alternative

Fahrzeit muss ≤ {req.max_drive_hours_per_day}h sein.
Nächte: {req.min_nights_per_stop}–{req.max_nights_per_stop}.

Befülle folgende Felder kontextabhängig:
- population: Einwohnerzahl als lesbarer String (z.B. "45'000 Einwohner"), falls bekannt
- altitude_m: Meereshöhe in Metern, besonders relevant für Bergregionen
- language: Hauptsprache der Region
- climate_note: Klimahinweis passend zur Reisezeit ({getattr(req, 'start_date', 'unbekannt')})
- must_see: Top 2-3 Sehenswürdigkeiten passend zu den Reisestilen {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
{('- family_friendly: true/false (Kinder reisen mit)' if has_children else '')}

Gib exakt dieses JSON zurück:
{{
  "options": [
    {{"id": 1, "option_type": "direct", "region": "...", "country": "FR", "drive_hours": 3.5, "drive_km": 280, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 2, "option_type": "scenic", "region": "...", "country": "FR", "drive_hours": 4.0, "drive_km": 320, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": 1200, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 3, "option_type": "cultural", "region": "...", "country": "FR", "drive_hours": 3.0, "drive_km": 250, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}}
  ],
  "estimated_total_stops": 4,
  "route_could_be_complete": false
}}"""

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")
        await debug_logger.log_prompt("StopOptionsFinder", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="StopOptionsFinder")
        text = response.content[0].text
        # Return Claude's result immediately — drive_hours/drive_km are placeholders.
        # Authoritative OSRM enrichment runs in main.py after this call.
        return parse_agent_json(text)
