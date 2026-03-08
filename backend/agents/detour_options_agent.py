"""DetourOptionsAgent — Fallback wenn StopOptionsFinder 0 gültige Optionen findet.

Schlage 3 Umweg-Ziele vor, die seitlich der Direktstrecke liegen und die Reise bereichern.
Keine Proximity-Filter — Umwege dürfen nah am Startpunkt sein.
"""
from typing import Optional
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner für Umwege. Wenn die direkte Strecke zu kurz für Zwischenstopps ist, "
    "schlage attraktive Umwegziele vor — Orte die SEITLICH der Direktstrecke liegen, die Reise "
    "bereichern und von dort das Ziel trotzdem erreichbar machen. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen."
)


class DetourOptionsAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-haiku-4-5")

    def _build_prompt(
        self,
        prev_location: str,
        segment_target: str,
        route_geometry: dict,
        prev_coords: Optional[tuple] = None,
        target_coords: Optional[tuple] = None,
    ) -> str:
        req = self.request
        geo = route_geometry or {}
        km = geo.get("segment_total_km", "?")
        hours = geo.get("segment_total_hours", "?")
        max_h = req.max_drive_hours_per_day
        has_children = bool(req.children)
        family_field = '"family_friendly": true,' if has_children else ""

        # Build a geographic bounding box from the two endpoints so Claude
        # stays in the same region. Pad by ~1.5° (~120 km) in each direction.
        bbox_hint = ""
        if prev_coords and target_coords:
            lat_min = min(prev_coords[0], target_coords[0]) - 1.5
            lat_max = max(prev_coords[0], target_coords[0]) + 1.5
            lon_min = min(prev_coords[1], target_coords[1]) - 1.5
            lon_max = max(prev_coords[1], target_coords[1]) + 1.5
            bbox_hint = (
                f"\nGEOGRAFISCHE GRENZE (zwingend): Alle Orte müssen innerhalb dieser Bounding-Box liegen:\n"
                f"  Lat {lat_min:.2f}–{lat_max:.2f}, Lon {lon_min:.2f}–{lon_max:.2f}\n"
                f"Orte ausserhalb dieser Box sind NICHT erlaubt.\n"
            )

        return f"""Direkte Strecke von {prev_location} nach {segment_target}: ~{km} km / ~{hours}h Fahrzeit.
Diese Strecke ist zu kurz für klassische Zwischenstopps.

Schlage 3 attraktive Umwegziele vor — Orte die SEITLICH der Direktstrecke liegen:
- option_type "umweg_1": Umweg links/westlich der Direktroute
- option_type "umweg_2": Umweg rechts/östlich der Direktroute
- option_type "umweg_3": weitere seitliche Richtung (nord oder süd der Strecke)
{bbox_hint}
REGELN (alle einhalten):
1. Jeder Umweg-Ort muss von {prev_location} in ≤ {max_h}h erreichbar sein
2. Von dort muss {segment_target} ebenfalls in ≤ {max_h}h erreichbar sein
3. Der Ort liegt NICHT direkt auf der Luftlinie {prev_location} → {segment_target}
4. Konkrete Ortschaft angeben (Stadt/Dorf), KEINE Regionen oder Gebirge

Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder' if req.children else ''}
Nächte: {req.min_nights_per_stop}–{req.max_nights_per_stop}

Gib exakt dieses JSON zurück (lat/lon = WGS84-Koordinaten, PFLICHT):
{{
  "options": [
    {{"id": 1, "option_type": "umweg_1", "region": "...", "country": "CH", "lat": 47.0, "lon": 8.0, "drive_hours": 1.5, "drive_km": 90, "nights": 1, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Deutsch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 2, "option_type": "umweg_2", "region": "...", "country": "CH", "lat": 47.1, "lon": 7.5, "drive_hours": 1.8, "drive_km": 110, "nights": 1, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Deutsch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 3, "option_type": "umweg_3", "region": "...", "country": "CH", "lat": 46.9, "lon": 8.3, "drive_hours": 2.0, "drive_km": 120, "nights": 1, "highlights": ["...", "..."], "teaser": "...", "population": "...", "altitude_m": null, "language": "Deutsch", "climate_note": "...", "must_see": ["...", "..."]{', ' + family_field[:-1] if family_field else ''}}}
  ]
}}"""

    async def find_detour_options(
        self,
        prev_location: str,
        segment_target: str,
        route_geometry: dict = None,
        prev_coords: Optional[tuple] = None,
        target_coords: Optional[tuple] = None,
    ) -> list:
        """Findet 3 Umweg-Optionen. Gibt Liste von Option-Dicts zurück."""
        prompt = self._build_prompt(prev_location, segment_target, route_geometry, prev_coords, target_coords)

        await debug_logger.log(
            LogLevel.API,
            f"→ Anthropic API call: {self.model}",
            job_id=self.job_id,
            agent="DetourOptions",
        )
        await debug_logger.log_prompt("DetourOptions", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="DetourOptions")
        text = response.content[0].text
        parsed = parse_agent_json(text)
        return parsed.get("options", [])
