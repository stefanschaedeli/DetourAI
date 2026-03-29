from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "trip_analysis"

SYSTEM_PROMPT = (
    "Du bist ein kritischer Reiseberater. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class TripAnalysisAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self, plan: dict, request: TravelRequest) -> dict:
        req = request
        stops = plan.get("stops", [])
        cost = plan.get("cost_estimate", {})

        # Build stop summary (one line per stop)
        stop_lines = []
        for s in stops:
            acc = s.get("accommodation") or {}
            acc_name = acc.get("name", "keine Unterkunft") if acc else "keine Unterkunft"
            acts = [a.get("name", "") for a in s.get("top_activities", [])[:3]]
            acts_str = ", ".join(acts) if acts else "keine"
            stop_lines.append(
                f"- {s.get('region')}, {s.get('country')}: "
                f"{s.get('nights')} Nächte, Unterkunft: {acc_name}, "
                f"Aktivitäten: {acts_str}"
            )
        stops_summary = "\n".join(stop_lines) if stop_lines else "Keine Stops"

        travel_styles_str = ", ".join(req.travel_styles) if req.travel_styles else "allgemein"
        children_str = f", {len(req.children)} Kinder (Alter: {', '.join(str(c.age) for c in req.children)})" if req.children else ""
        prefs_str = "; ".join(req.accommodation_preferences) if req.accommodation_preferences else "keine"
        mandatory_acts = ", ".join(a.name for a in req.mandatory_activities) if req.mandatory_activities else "keine"
        travel_desc_line = f"\n- Reisebeschreibung: {req.travel_description}" if req.travel_description else ""
        pref_acts_line = f"\n- Bevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""

        prompt = f"""Analysiere diesen Reiseplan kritisch und bewerte, wie gut er die Anforderungen des Benutzers erfüllt.

## Benutzeranforderungen
- Startort: {req.start_location}
- Ziel: {req.main_destination}
- Dauer: {req.total_days} Tage ({req.start_date} – {req.end_date})
- Budget: CHF {req.budget_chf}
- Reisende: {req.adults} Erwachsene{children_str}
- Reisestile: {travel_styles_str}
- Unterkunftswünsche: {prefs_str}
- Pflichtaktivitäten: {mandatory_acts}{travel_desc_line}{pref_acts_line}
- Max. Fahrtzeit/Tag: {req.max_drive_hours_per_day}h
- Min. Nächte pro Stop: {req.min_nights_per_stop}

## Erstellter Reiseplan
Stops:
{stops_summary}

Kostenübersicht:
- Unterkunft: CHF {cost.get('accommodations_chf', 0)}
- Aktivitäten: CHF {cost.get('activities_chf', 0)}
- Verpflegung: CHF {cost.get('food_chf', 0)}
- Treibstoff: CHF {cost.get('fuel_chf', 0)}
- Fähren: CHF {cost.get('ferries_chf', 0)}
- Gesamt: CHF {cost.get('total_chf', 0)} (Budget: CHF {req.budget_chf}, Rest: CHF {cost.get('budget_remaining_chf', 0)})

Gib exakt dieses JSON zurück:
{{
  "settings_summary": "Zusammenfassung der Reiseeinstellungen in 3-5 Sätzen auf Deutsch",
  "requirements_match_score": 8,
  "requirements_analysis": "Detaillierte Analyse in 3-5 Sätzen, wie gut der Plan die Anforderungen erfüllt",
  "strengths": [
    "Stärke 1",
    "Stärke 2"
  ],
  "weaknesses": [
    "Schwäche 1"
  ],
  "improvement_suggestions": [
    {{
      "title": "Kurzer Titel",
      "description": "Konkreter Verbesserungsvorschlag",
      "impact": "high"
    }}
  ]
}}

Regeln:
- settings_summary: 3-5 Sätze, fasst alle Reiseeinstellungen zusammen
- requirements_match_score: Ganzzahl 1-10 (10 = perfekte Erfüllung)
- requirements_analysis: 3-5 Sätze kritische Bewertung
- strengths: 2-4 konkrete Stärken des Plans
- weaknesses: 1-3 ehrliche Schwachstellen
- improvement_suggestions: 2-4 Einträge mit impact "high", "medium" oder "low"
- Alle Texte auf Deutsch"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Reise-Analyse)",
            job_id=self.job_id, agent="TripAnalysisAgent",
        )
        await debug_logger.log_prompt("TripAnalysisAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TripAnalysisAgent",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text
        result = parse_agent_json(text)
        return result
