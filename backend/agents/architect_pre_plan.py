from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "architect_pre_plan"

SYSTEM_PROMPT = (
    "Du bist ein strategischer Reiseplaner. Deine Aufgabe ist es, eine kompakte "
    "Regionsübersicht für eine Reise zu erstellen: eine geordnete Liste von Regionen "
    "mit empfohlenen Übernachtungsnächten und maximalen Fahrzeiten zwischen den Regionen. "
    "KRITISCH — Nächte pro Region: Verteile die Nächte nach Potential des Ortes. "
    "Wichtige Städte und schöne Regionen bekommen mehr Nächte als reine Transitstopps. "
    "KRITISCH — Fahrzeiten: Kein Regionswechsel darf die angegebene maximale Fahrzeit überschreiten. "
    "KRITISCH — Nächtebudget: Die Summe aller empfohlenen Nächte muss exakt gleich dem angegebenen Nächtebudget sein. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class ArchitectPrePlanAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    def _build_prompt(self) -> str:
        req = self.request
        leg = req.legs[0]  # Pre-plan is for the first transit leg
        nights_budget = leg.total_days - 1

        styles_str = ", ".join(req.travel_styles) if req.travel_styles else "allgemein"
        desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
        pref_line = (
            f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}"
            if req.preferred_activities else ""
        )
        mandatory_line = (
            f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}"
            if req.mandatory_activities else ""
        )

        return f"""Erstelle einen Regionsplan für folgende Reise:

Von: {leg.start_location}
Nach: {leg.end_location}
Nächtebudget: {nights_budget} Nächte (Summe aller Regionen MUSS exakt {nights_budget} ergeben)
Maximale Fahrzeit pro Etappe: {req.max_drive_hours_per_day}h
Reisestile: {styles_str}{desc_line}{pref_line}{mandatory_line}

Gib exakt dieses JSON zurück:
{{
  "regions": [
    {{"name": "Regionname", "recommended_nights": 2, "max_drive_hours": 3.0}},
    {{"name": "Regionname", "recommended_nights": 3, "max_drive_hours": 2.5}}
  ],
  "total_nights": {nights_budget}
}}

Regeln:
1. Summe aller recommended_nights = {nights_budget}
2. max_drive_hours pro Region <= {req.max_drive_hours_per_day}h
3. Regionen müssen logisch auf der Route zwischen {leg.start_location} und {leg.end_location} liegen
4. Verteile Nächte nach Potential: attraktive Orte bekommen mehr Nächte als Transitstopps"""

    async def run(self) -> dict:
        prompt = self._build_prompt()
        await debug_logger.log(
            LogLevel.API,
            f"→ Anthropic API call: {self.model}",
            job_id=self.job_id,
            agent="ArchitectPrePlan",
        )
        await debug_logger.log_prompt("ArchitectPrePlan", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 1024),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(
            call,
            job_id=self.job_id,
            agent_name="ArchitectPrePlan",
            max_attempts=1,
        )
        return parse_agent_json(response.content[0].text)
