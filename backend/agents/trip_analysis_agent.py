from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "trip_analysis"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein kritischer Reiseberater. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a critical travel advisor. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक आलोचनात्मक यात्रा सलाहकार हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class TripAnalysisAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self, plan: dict, request: TravelRequest) -> dict:
        req = request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        stops = plan.get("stops", [])
        cost = plan.get("cost_estimate", {})

        _L = {
            "de": {
                "no_acc": "keine Unterkunft", "no_acts": "keine", "no_stops": "Keine Stops",
                "nights": "Nächte", "acc": "Unterkunft", "acts": "Aktivitäten",
                "styles_default": "allgemein", "children": "Kinder", "age": "Alter",
                "no_prefs": "keine", "no_mandatory": "keine",
                "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten",
                "analyze": "Analysiere diesen Reiseplan kritisch und bewerte, wie gut er die Anforderungen des Benutzers erfüllt.",
                "user_reqs": "Benutzeranforderungen",
                "start": "Startort", "dest": "Ziel", "duration": "Dauer", "days": "Tage",
                "budget": "Budget", "travelers": "Reisende", "adults": "Erwachsene",
                "styles": "Reisestile", "acc_prefs": "Unterkunftswünsche",
                "mandatory": "Pflichtaktivitäten", "max_drive": "Max. Fahrtzeit/Tag",
                "min_nights": "Min. Nächte pro Stop",
                "plan_header": "Erstellter Reiseplan", "stops": "Stops",
                "cost_overview": "Kostenübersicht",
                "cost_acc": "Unterkunft", "cost_acts": "Aktivitäten", "cost_food": "Verpflegung",
                "cost_fuel": "Treibstoff", "cost_ferry": "Fähren",
                "cost_total": "Gesamt", "cost_remaining": "Rest",
                "return_json": "Gib exakt dieses JSON zurück:",
                "summary_desc": "Zusammenfassung der Reiseeinstellungen in 3-5 Sätzen",
                "analysis_desc": "Detaillierte Analyse in 3-5 Sätzen, wie gut der Plan die Anforderungen erfüllt",
                "strength": "Stärke", "weakness": "Schwäche",
                "short_title": "Kurzer Titel", "suggestion_desc": "Konkreter Verbesserungsvorschlag",
                "rules": "Regeln",
                "rule_summary": "settings_summary: 3-5 Sätze, fasst alle Reiseeinstellungen zusammen",
                "rule_score": "requirements_match_score: Ganzzahl 1-10 (10 = perfekte Erfüllung)",
                "rule_analysis": "requirements_analysis: 3-5 Sätze kritische Bewertung",
                "rule_strengths": "strengths: 2-4 konkrete Stärken des Plans",
                "rule_weaknesses": "weaknesses: 1-3 ehrliche Schwachstellen",
                "rule_suggestions": "improvement_suggestions: 2-4 Einträge mit impact \"high\", \"medium\" oder \"low\"",
                "rule_lang": "Alle Texte auf Deutsch",
            },
            "en": {
                "no_acc": "no accommodation", "no_acts": "none", "no_stops": "No stops",
                "nights": "nights", "acc": "Accommodation", "acts": "Activities",
                "styles_default": "general", "children": "children", "age": "age",
                "no_prefs": "none", "no_mandatory": "none",
                "desc_label": "Travel description", "pref_label": "Preferred activities",
                "analyze": "Critically analyze this travel plan and evaluate how well it meets the user's requirements.",
                "user_reqs": "User requirements",
                "start": "Start location", "dest": "Destination", "duration": "Duration", "days": "days",
                "budget": "Budget", "travelers": "Travelers", "adults": "adults",
                "styles": "Travel styles", "acc_prefs": "Accommodation preferences",
                "mandatory": "Mandatory activities", "max_drive": "Max. drive time/day",
                "min_nights": "Min. nights per stop",
                "plan_header": "Created travel plan", "stops": "Stops",
                "cost_overview": "Cost overview",
                "cost_acc": "Accommodation", "cost_acts": "Activities", "cost_food": "Food",
                "cost_fuel": "Fuel", "cost_ferry": "Ferries",
                "cost_total": "Total", "cost_remaining": "Remaining",
                "return_json": "Return exactly this JSON:",
                "summary_desc": "Summary of travel settings in 3-5 sentences",
                "analysis_desc": "Detailed analysis in 3-5 sentences of how well the plan meets requirements",
                "strength": "Strength", "weakness": "Weakness",
                "short_title": "Short title", "suggestion_desc": "Concrete improvement suggestion",
                "rules": "Rules",
                "rule_summary": "settings_summary: 3-5 sentences, summarizes all travel settings",
                "rule_score": "requirements_match_score: Integer 1-10 (10 = perfect fulfillment)",
                "rule_analysis": "requirements_analysis: 3-5 sentences critical evaluation",
                "rule_strengths": "strengths: 2-4 concrete strengths of the plan",
                "rule_weaknesses": "weaknesses: 1-3 honest weaknesses",
                "rule_suggestions": "improvement_suggestions: 2-4 entries with impact \"high\", \"medium\" or \"low\"",
                "rule_lang": "All texts in English",
            },
            "hi": {
                "no_acc": "कोई आवास नहीं", "no_acts": "कोई नहीं", "no_stops": "कोई स्टॉप नहीं",
                "nights": "रातें", "acc": "आवास", "acts": "गतिविधियां",
                "styles_default": "सामान्य", "children": "बच्चे", "age": "आयु",
                "no_prefs": "कोई नहीं", "no_mandatory": "कोई नहीं",
                "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां",
                "analyze": "इस यात्रा योजना का आलोचनात्मक विश्लेषण करें और मूल्यांकन करें कि यह उपयोगकर्ता की आवश्यकताओं को कितनी अच्छी तरह पूरा करती है।",
                "user_reqs": "उपयोगकर्ता आवश्यकताएं",
                "start": "प्रारंभ स्थान", "dest": "गंतव्य", "duration": "अवधि", "days": "दिन",
                "budget": "बजट", "travelers": "यात्रीगण", "adults": "वयस्क",
                "styles": "यात्रा शैलियां", "acc_prefs": "आवास वरीयताएं",
                "mandatory": "अनिवार्य गतिविधियां", "max_drive": "अधिकतम ड्राइव समय/दिन",
                "min_nights": "प्रति स्टॉप न्यूनतम रातें",
                "plan_header": "बनाई गई यात्रा योजना", "stops": "स्टॉप",
                "cost_overview": "लागत अवलोकन",
                "cost_acc": "आवास", "cost_acts": "गतिविधियां", "cost_food": "भोजन",
                "cost_fuel": "ईंधन", "cost_ferry": "नौका",
                "cost_total": "कुल", "cost_remaining": "शेष",
                "return_json": "बिल्कुल यह JSON लौटाएं:",
                "summary_desc": "3-5 वाक्यों में यात्रा सेटिंग्स का सारांश",
                "analysis_desc": "3-5 वाक्यों में विस्तृत विश्लेषण",
                "strength": "ताकत", "weakness": "कमजोरी",
                "short_title": "छोटा शीर्षक", "suggestion_desc": "ठोस सुधार सुझाव",
                "rules": "नियम",
                "rule_summary": "settings_summary: 3-5 वाक्य, सभी यात्रा सेटिंग्स का सारांश",
                "rule_score": "requirements_match_score: पूर्णांक 1-10 (10 = सही पूर्ति)",
                "rule_analysis": "requirements_analysis: 3-5 वाक्य आलोचनात्मक मूल्यांकन",
                "rule_strengths": "strengths: योजना की 2-4 ठोस ताकतें",
                "rule_weaknesses": "weaknesses: 1-3 ईमानदार कमजोरियां",
                "rule_suggestions": "improvement_suggestions: impact \"high\", \"medium\" या \"low\" के साथ 2-4 प्रविष्टियां",
                "rule_lang": "सभी पाठ हिंदी में",
            },
        }
        TL = _L.get(lang, _L["de"])

        # Build stop summary
        stop_lines = []
        for s in stops:
            acc = s.get("accommodation") or {}
            acc_name = acc.get("name", TL["no_acc"]) if acc else TL["no_acc"]
            acts = [a.get("name", "") for a in s.get("top_activities", [])[:3]]
            acts_str = ", ".join(acts) if acts else TL["no_acts"]
            stop_lines.append(
                f"- {s.get('region')}, {s.get('country')}: "
                f"{s.get('nights')} {TL['nights']}, {TL['acc']}: {acc_name}, "
                f"{TL['acts']}: {acts_str}"
            )
        stops_summary = "\n".join(stop_lines) if stop_lines else TL["no_stops"]

        travel_styles_str = ", ".join(req.travel_styles) if req.travel_styles else TL["styles_default"]
        children_str = f", {len(req.children)} {TL['children']} ({TL['age']}: {', '.join(str(c.age) for c in req.children)})" if req.children else ""
        prefs_str = "; ".join(req.accommodation_preferences) if req.accommodation_preferences else TL["no_prefs"]
        mandatory_acts = ", ".join(a.name for a in req.mandatory_activities) if req.mandatory_activities else TL["no_mandatory"]
        travel_desc_line = f"\n- {TL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_acts_line = f"\n- {TL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""

        prompt = f"""{TL['analyze']}

## {TL['user_reqs']}
- {TL['start']}: {req.start_location}
- {TL['dest']}: {req.main_destination}
- {TL['duration']}: {req.total_days} {TL['days']} ({req.start_date} – {req.end_date})
- {TL['budget']}: CHF {req.budget_chf}
- {TL['travelers']}: {req.adults} {TL['adults']}{children_str}
- {TL['styles']}: {travel_styles_str}
- {TL['acc_prefs']}: {prefs_str}
- {TL['mandatory']}: {mandatory_acts}{travel_desc_line}{pref_acts_line}
- {TL['max_drive']}: {req.max_drive_hours_per_day}h
- {TL['min_nights']}: {req.min_nights_per_stop}

## {TL['plan_header']}
{TL['stops']}:
{stops_summary}

{TL['cost_overview']}:
- {TL['cost_acc']}: CHF {cost.get('accommodations_chf', 0)}
- {TL['cost_acts']}: CHF {cost.get('activities_chf', 0)}
- {TL['cost_food']}: CHF {cost.get('food_chf', 0)}
- {TL['cost_fuel']}: CHF {cost.get('fuel_chf', 0)}
- {TL['cost_ferry']}: CHF {cost.get('ferries_chf', 0)}
- {TL['cost_total']}: CHF {cost.get('total_chf', 0)} ({TL['budget']}: CHF {req.budget_chf}, {TL['cost_remaining']}: CHF {cost.get('budget_remaining_chf', 0)})

{TL['return_json']}
{{
  "settings_summary": "{TL['summary_desc']}",
  "requirements_match_score": 8,
  "requirements_analysis": "{TL['analysis_desc']}",
  "strengths": [
    "{TL['strength']} 1",
    "{TL['strength']} 2"
  ],
  "weaknesses": [
    "{TL['weakness']} 1"
  ],
  "improvement_suggestions": [
    {{
      "title": "{TL['short_title']}",
      "description": "{TL['suggestion_desc']}",
      "impact": "high"
    }}
  ]
}}

{TL['rules']}:
- {TL['rule_summary']}
- {TL['rule_score']}
- {TL['rule_analysis']}
- {TL['rule_strengths']}
- {TL['rule_weaknesses']}
- {TL['rule_suggestions']}
- {TL['rule_lang']}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Reise-Analyse)",
            job_id=self.job_id, agent="TripAnalysisAgent",
        )
        await debug_logger.log_prompt("TripAnalysisAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TripAnalysisAgent",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text
        result = parse_agent_json(text)
        return result
