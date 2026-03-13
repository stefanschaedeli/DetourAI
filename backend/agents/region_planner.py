from models.travel_request import TravelRequest
from models.trip_leg import RegionPlan, RegionPlanItem
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model

SYSTEM_PROMPT = (
    "Du bist ein Reiserouten-Stratege. Plane eine Rundreise durch Regionen basierend auf der "
    "Beschreibung des Reisenden. Ordne Regionen in einer logistisch sinnvollen Reihenfolge "
    "(minimale Rückwege, geografische Effizienz). Jede Region soll ein Gebiet repräsentieren, "
    "in dem der Reisende konkrete Stopps machen kann. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

REGION_SCHEMA = """{
  "regions": [
    { "name": "Regionsname", "lat": 0.0, "lon": 0.0, "reason": "Warum diese Region" }
  ],
  "summary": "Zusammenfassung der Rundreise"
}"""


class RegionPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5")

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"
        return (
            f"Startort: {leg.start_location}\n"
            f"Endort: {leg.end_location}\n"
            f"Verfügbare Tage: {leg.total_days}\n"
            f"Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h\n"
            f"Reisestile: {styles}\n"
            f"Reisende: {req.adults} Erwachsene"
            + (f", Kinder: {len(req.children)}" if req.children else "")
        )

    async def plan(self, description: str, leg_index: int) -> RegionPlan:
        context = self._leg_context(leg_index)

        prompt = (
            f"{context}\n\n"
            f"Beschreibung des Reisenden:\n{description}\n\n"
            f"Erstelle einen Regionen-Plan: eine geordnete Liste von Regionen, "
            f"die der Reisende auf einer Rundreise besuchen soll.\n"
            f"- Jede Region = ein Gebiet mit mehreren möglichen Stopps\n"
            f"- Logistisch sinnvolle Reihenfolge (minimale Rückwege)\n"
            f"- Anzahl Regionen passend zur verfügbaren Zeit\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API, f"→ RegionPlannerAgent (Plan) {description[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)

    async def replace_region(
        self, index: int, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Aktueller Regionen-Plan:\n{regions_str}\n\n"
            f"Der Reisende möchte Region {index+1} ({current_plan.regions[index].name}) ersetzen:\n"
            f'"{instruction}"\n\n'
            f"Erstelle den aktualisierten Plan. Ersetze NUR Region {index+1}, "
            f"behalte alle anderen Regionen bei. Passe die Reihenfolge an falls nötig.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Ersetzen #{index+1}) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)

    async def recalculate(
        self, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Bisheriger Regionen-Plan:\n{regions_str}\n"
            f"Zusammenfassung: {current_plan.summary}\n\n"
            f"Korrektur des Reisenden:\n\"{instruction}\"\n\n"
            f"Erstelle einen komplett neuen Regionen-Plan unter Berücksichtigung "
            f"der Korrektur. Der bisherige Plan dient als Kontext.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Neu berechnen) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent")
        text = response.content[0].text
        data = parse_agent_json(text)
        return RegionPlan(**data)
