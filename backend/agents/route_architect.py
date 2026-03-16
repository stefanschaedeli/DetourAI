from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "route_architect"

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner für Familien. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. "
    "Kein Markdown, keine Erklärungen, nur JSON."
)


class RouteArchitectAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self) -> dict:
        await debug_logger.log(
            LogLevel.AGENT, "RouteArchitect startet",
            job_id=self.job_id, agent="RouteArchitect",
        )

        req = self.request
        children_ages = [c.age for c in req.children]
        via_str = ""
        if req.via_points:
            parts = []
            for vp in req.via_points:
                s = vp.location
                if vp.fixed_date:
                    s += f" (Fixdatum: {vp.fixed_date})"
                if vp.notes:
                    s += f" [{vp.notes}]"
                parts.append(s)
            via_str = f"Via-Punkte: {', '.join(parts)}\n"

        mandatory_str = ""
        if req.mandatory_activities:
            acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
            mandatory_str = f"Pflichtaktivitäten: {', '.join(acts)}\n"

        prompt = f"""Plane eine Reiseroute mit Zwischenstopps:

Start: {req.start_location}
{via_str}Hauptziel: {req.main_destination}
Reisedauer: {req.total_days} Tage ({req.start_date} – {req.end_date})
Reisende: {req.adults} Erwachsene{f', Kinder im Alter {children_ages}' if children_ages else ''}
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
{f'Reisebeschreibung: {req.travel_description}' if req.travel_description else ''}
Maximale Fahrzeit pro Tag: {req.max_drive_hours_per_day}h
Nächte pro Stop: {req.min_nights_per_stop}–{req.max_nights_per_stop}
Budget: CHF {req.budget_chf:,.0f}
{mandatory_str}

Erstelle eine optimale Route. Der erste Stop MUSS der Startort sein, der letzte Stop MUSS das Hauptziel sein.
Dazwischen plane 2–5 sinnvolle Zwischenstopps. Verteile die Tage sinnvoll.
Gib genau dieses JSON zurück:
{{
  "stops": [
    {{"id": 1, "region": "{req.start_location}", "country": "CH", "arrival_day": 1, "nights": 0, "drive_hours": 0, "is_fixed": false, "notes": "Startort"}},
    {{"id": 2, "region": "Annecy", "country": "FR", "arrival_day": 2, "nights": 2, "drive_hours": 3.5, "is_fixed": false, "notes": "..."}},
    {{"id": 3, "region": "{req.main_destination}", "country": "FR", "arrival_day": 8, "nights": 3, "drive_hours": 4.0, "is_fixed": false, "notes": "Hauptziel"}}
  ],
  "total_drive_days": 3,
  "total_rest_days": 7,
  "ferry_crossings": []
}}"""

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="RouteArchitect")
        await debug_logger.log_prompt("RouteArchitect", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RouteArchitect")
        text = response.content[0].text

        await debug_logger.log(
            LogLevel.SUCCESS, "RouteArchitect abgeschlossen",
            job_id=self.job_id, agent="RouteArchitect",
        )

        return parse_agent_json(text)
