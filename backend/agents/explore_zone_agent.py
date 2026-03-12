import json
from models.travel_request import TravelRequest
from models.trip_leg import ExploreZoneAnalysis, ExploreStop
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiserouten-Experte. Analysiere eine Reisezone und plane einen effizienten Rundkurs. "
    "Berücksichtige lokale Logistik (Fähren, Bergpässe, Straßennetze) und geografische Effizienz "
    "(vermeide unnötige Rückwege). "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

FIRST_PASS_SCHEMA = """{
  "zone_characteristics": "string — Terrain, Logistik, besondere Merkmale der Zone",
  "preliminary_anchors": ["Liste von Muss-Sehen-Orten, geografisch geordnet"],
  "guided_questions": ["2-3 zonenspezifische Fragen an den Reisenden"]
}"""

SECOND_PASS_SCHEMA = """{
  "circuit": [
    {
      "name": "Konkreter Ortsname (Stadt/Dorf, keine Region)",
      "lat": 0.0,
      "lon": 0.0,
      "suggested_nights": 1,
      "significance": "anchor | scenic | hidden_gem",
      "logistics_note": "optional — z.B. Fähre erforderlich"
    }
  ],
  "warnings": ["Logistische Hinweise für die gesamte Route"]
}"""


class ExploreZoneAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5")

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        bbox = leg.zone_bbox
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"

        if bbox:
            zone_info = (
                f"Zone: {bbox.zone_label}\n"
                f"Begrenzungsrahmen: N={bbox.north:.2f} S={bbox.south:.2f} "
                f"E={bbox.east:.2f} W={bbox.west:.2f}\n"
            )
        else:
            zone_info = f"Erkundungszone: {leg.start_location} bis {leg.end_location}\n"

        return (
            f"{zone_info}"
            f"Verfügbare Tage in dieser Zone: {leg.total_days}\n"
            f"Reisestile: {styles}\n"
            f"Reisende: {req.adults} Erwachsene"
            + (f", Kinder: {len(req.children)}" if req.children else "")
        )

    async def run_first_pass(self, leg_index: int) -> ExploreZoneAnalysis:
        req = self.request
        leg = req.legs[leg_index]
        context = self._leg_context(leg_index)

        mandatory = ""
        if req.mandatory_activities:
            acts = ", ".join(a.name for a in req.mandatory_activities)
            mandatory = f"\nPflichtaktivitäten: {acts}"

        prompt = (
            f"{context}{mandatory}\n\n"
            f"Analysiere die Zone und erstelle:\n"
            f"1. Eine kurze Charakterisierung der Zone (Terrain, Logistik, Besonderheiten)\n"
            f"2. Eine vorläufige Liste der wichtigsten Sehenswürdigkeiten, geografisch geordnet\n"
            f"3. 2-3 spezifische Fragen an den Reisenden, die den Rundkurs wesentlich beeinflussen\n\n"
            f"Antwortformat:\n{FIRST_PASS_SCHEMA}"
        )

        label = leg.zone_bbox.zone_label if leg.zone_bbox else f"{leg.start_location}–{leg.end_location}"
        await debug_logger.log(LogLevel.API, f"→ ExploreZoneAgent (1. Durchlauf) {label}",
                               job_id=self.job_id, agent="ExploreZoneAgent")

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ExploreZoneAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return ExploreZoneAnalysis(**data)

    async def run_second_pass(
        self,
        leg_index: int,
        first_pass: ExploreZoneAnalysis,
        guidance: list[str],
    ) -> tuple[list[ExploreStop], list[str]]:
        req = self.request
        leg = req.legs[leg_index]
        context = self._leg_context(leg_index)

        guidance_str = "\n".join(f"- {q}: {a}" for q, a in
                                  zip(first_pass.guided_questions, guidance))

        prompt = (
            f"{context}\n\n"
            f"Zonenanalyse:\n{first_pass.zone_characteristics}\n\n"
            f"Vorläufige Ankerpunkte: {', '.join(first_pass.preliminary_anchors)}\n\n"
            f"Antworten des Reisenden:\n{guidance_str}\n\n"
            f"Erstelle jetzt einen vollständigen, logistisch optimierten Rundkurs für {leg.total_days} Tage.\n"
            f"Regeln:\n"
            f"- Konkrete Ortsnamen (Städte/Dörfer) — KEINE Regionen\n"
            f"- Geografisch effizienter Rundkurs (minimale Rückwege)\n"
            f"- Fähren und Logistik im Rundkurs berücksichtigen\n"
            f"- Nächte pro Stopp basierend auf Bedeutung und Aktivitätsdichte\n"
            f"- Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h\n\n"
            f"Antwortformat:\n{SECOND_PASS_SCHEMA}"
        )

        label = leg.zone_bbox.zone_label if leg.zone_bbox else f"{leg.start_location}–{leg.end_location}"
        await debug_logger.log(LogLevel.API, f"→ ExploreZoneAgent (2. Durchlauf) {label}",
                               job_id=self.job_id, agent="ExploreZoneAgent")

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ExploreZoneAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        circuit = [ExploreStop(**s) for s in data.get("circuit", [])]
        warnings = data.get("warnings", [])
        return circuit, warnings
