from models.travel_request import TravelRequest
from models.trip_leg import RegionPlan, RegionPlanItem
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "region_planner"

SYSTEM_PROMPT = (
    "Du bist ein Reiserouten-Stratege. Plane eine Rundreise durch Regionen basierend auf der "
    "Beschreibung des Reisenden. Ordne Regionen in einer logistisch sinnvollen Reihenfolge "
    "(minimale Rückwege, geografische Effizienz). Jede Region soll ein Gebiet repräsentieren, "
    "in dem der Reisende konkrete Stopps machen kann.\n"
    "Für jede Region liefere:\n"
    "- name: Name der Region\n"
    "- lat/lon: Zentrale Koordinaten der Region\n"
    "- reason: Warum diese Region zur Reise passt (1 Satz)\n"
    "- teaser: Kurzer, einladender Satz der die Region beschreibt und Lust auf den Besuch macht\n"
    "- highlights: 3-5 konkrete Sehenswürdigkeiten, Aktivitäten oder Besonderheiten der Region\n\n"
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

REGION_SCHEMA = """{
  "regions": [
    {
      "name": "Regionsname",
      "lat": 0.0,
      "lon": 0.0,
      "reason": "Warum diese Region zur Reise passt",
      "teaser": "Ein Satz der die Region beschreibt und Lust macht",
      "highlights": ["Sehenswürdigkeit 1", "Aktivität 2", "Besonderheit 3"]
    }
  ],
  "summary": "Zusammenfassung der Rundreise"
}"""


class RegionPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"
        lines = []
        if leg.start_location:
            lines.append(f"Startort: {leg.start_location}")
        if leg.end_location:
            lines.append(f"Endort: {leg.end_location}")
        lines.append(f"Verfügbare Tage: {leg.total_days}")
        lines.append(f"Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h")
        lines.append(f"Reisestile: {styles}")
        travellers = f"Reisende: {req.adults} Erwachsene"
        if req.children:
            travellers += f", Kinder: {len(req.children)}"
        lines.append(travellers)
        return "\n".join(lines)

    async def _extract_json(self, response) -> dict:
        """Extract JSON from response, warning on truncation."""
        if response.stop_reason == "max_tokens":
            await debug_logger.log(
                LogLevel.WARNING,
                "RegionPlannerAgent Antwort wurde abgeschnitten (max_tokens erreicht)",
                job_id=self.job_id, agent="RegionPlannerAgent",
            )
        text = response.content[0].text
        return parse_agent_json(text)

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
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        data = await self._extract_json(response)
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
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        data = await self._extract_json(response)
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
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        data = await self._extract_json(response)
        return RegionPlan(**data)
