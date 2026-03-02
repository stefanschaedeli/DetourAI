from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner. Schlage genau 3 Zwischenstopps vor: direct, scenic, cultural. "
    "KRITISCH — Regeln für das Feld 'region': "
    "Immer eine konkrete Ortschaft (Stadt, Dorf, Kleinstadt) angeben — NIEMALS Regionen, Gebirge, Länder oder Gebiete "
    "(z.B. NICHT 'Toskana', 'Alpen', 'Provence', 'Schwarzwald', sondern 'Siena', 'Annecy', 'Aix-en-Provence', 'Freiburg im Breisgau'). "
    "KRITISCH — Fahrzeiten: Jede Option muss drive_hours ≤ dem angegebenen Maximum einhalten. "
    "Wähle nähere Zwischenstopps wenn nötig — lieber einen kürzeren Etappenstopp als das Limit zu überschreiten. "
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
        route_geometry: dict = None,
    ) -> dict:
        req = self.request
        geo = route_geometry or {}

        prev_stop = selected_stops[-1]["region"] if selected_stops else req.start_location
        prev_country = selected_stops[-1].get("country", "") if selected_stops else "CH"

        stops_str = ""
        if selected_stops:
            parts = [f"Stop {s['id']}: {s['region']} ({s.get('country','?')}, {s.get('nights',1)} Nächte, {s.get('drive_km','?')} km vom Vorgänger)"
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

        # Build geometry context block
        geo_lines = []
        if geo.get("segment_total_km"):
            geo_lines.append(f"Gesamtstrecke {prev_stop} → {segment_target}: ~{geo['segment_total_km']:.0f} km / ~{geo.get('segment_total_hours', 0):.1f}h Fahrzeit")
        if geo.get("stops_remaining") is not None:
            geo_lines.append(f"Empfohlene Anzahl weiterer Stopps bis {segment_target}: {geo['stops_remaining']}")
        if geo.get("ideal_km_from_prev"):
            geo_lines.append(
                f"Ideale Distanz dieses Stops vom letzten Stop: ~{geo['ideal_km_from_prev']:.0f} km / ~{geo.get('ideal_hours_from_prev', 0):.1f}h"
                f" (gleichmässige Aufteilung der Reststrecke auf {geo['stops_remaining']} Etappen)"
            )
            geo_lines.append(
                f"→ Wähle Orte die ca. {geo['ideal_km_from_prev']:.0f} km von {prev_stop} entfernt liegen, "
                f"NICHT direkt am Start und NICHT direkt am Ziel."
            )
        geo_block = "\n".join(geo_lines) + "\n" if geo_lines else ""

        prompt = f"""Segment {segment_index + 1} von {segment_count} Richtung: {segment_target}

Start der Gesamtreise: {req.start_location}
Letzter Stop (Abfahrtspunkt): {prev_stop}
Endziel dieses Segments: {segment_target}
Aktueller Stop #{stop_number}
{stops_str}
{geo_block}Verbleibende Tage im Segment: {days_remaining}
Maximale Fahrzeit pro Etappe: {req.max_drive_hours_per_day}h
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder (Alter: ' + ', '.join(str(c) for c in req.children) + ')' if req.children else ''}
{complete_hint}{extra_hint}
Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor:
- option_type "direct": kürzeste Route Richtung {segment_target}
- option_type "scenic": landschaftlich schöne Alternative
- option_type "cultural": kulturell interessante Alternative

PFLICHT — alle 3 Regeln einhalten:
1. drive_hours von {prev_stop} zu diesem Stop: ≤ {req.max_drive_hours_per_day}h
2. Distanz: ~{geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80):.0f} km von {prev_stop}
   (Toleranz ±30%; NICHT unter {geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80) * 0.5:.0f} km — zu nahe am letzten Stop)
3. Teile lange Strecken auf — niemals direkt zum Ziel springen wenn noch {geo.get('stops_remaining', 1)} Etappe(n) geplant sind
Nächte: {req.min_nights_per_stop}–{req.max_nights_per_stop}.

Befülle folgende Felder kontextabhängig:
- population: Einwohnerzahl als lesbarer String (z.B. "45'000 Einwohner"), falls bekannt
- altitude_m: Meereshöhe in Metern, besonders relevant für Bergregionen
- language: Hauptsprache der Region
- climate_note: Klimahinweis passend zur Reisezeit ({getattr(req, 'start_date', 'unbekannt')})
- must_see: Top 2-3 Sehenswürdigkeiten passend zu den Reisestilen {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
{('- family_friendly: true/false (Kinder reisen mit)' if has_children else '')}

Gib exakt dieses JSON zurück. lat/lon = WGS84-Koordinaten des Stadtzentrums (PFLICHT – keine null):
{{
  "options": [
    {{"id": 1, "option_type": "direct", "region": "...", "country": "FR", "lat": 45.7640, "lon": 4.8357, "drive_hours": 3.5, "drive_km": 280, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 2, "option_type": "scenic", "region": "...", "country": "FR", "lat": 45.9237, "lon": 6.8694, "drive_hours": 4.0, "drive_km": 320, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": 1200, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 3, "option_type": "cultural", "region": "...", "country": "FR", "lat": 43.2965, "lon": 5.3698, "drive_hours": 3.0, "drive_km": 250, "nights": 2, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}}
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
