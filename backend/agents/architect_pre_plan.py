from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "architect_pre_plan"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein strategischer Reiseplaner. Deine Aufgabe ist es, eine kompakte "
        "Regionsübersicht für eine Reise zu erstellen: eine geordnete Liste von Regionen "
        "mit empfohlenen Übernachtungsnächten und maximalen Fahrzeiten zwischen den Regionen. "
        "KRITISCH — Nächte pro Region: Verteile die Nächte nach Potential des Ortes. "
        "Wichtige Städte und schöne Regionen bekommen mehr Nächte als reine Transitstopps. "
        "KRITISCH — Fahrzeiten: Kein Regionswechsel darf die angegebene maximale Fahrzeit überschreiten. "
        "KRITISCH — Nächtebudget: Die Summe aller empfohlenen Nächte muss exakt gleich dem angegebenen Nächtebudget sein. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a strategic travel planner. Your task is to create a compact "
        "region overview for a trip: an ordered list of regions "
        "with recommended overnight stays and maximum drive times between regions. "
        "CRITICAL — Nights per region: Distribute nights according to the potential of each place. "
        "Important cities and beautiful regions get more nights than pure transit stops. "
        "CRITICAL — Drive times: No region change may exceed the specified maximum drive time. "
        "CRITICAL — Nights budget: The sum of all recommended nights must exactly equal the specified nights budget. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक रणनीतिक यात्रा योजनाकार हैं। आपका कार्य यात्रा के लिए एक संक्षिप्त "
        "क्षेत्र अवलोकन बनाना है: अनुशंसित रात्रि-प्रवासों और क्षेत्रों के बीच अधिकतम "
        "ड्राइव समय के साथ क्षेत्रों की एक क्रमबद्ध सूची। "
        "महत्वपूर्ण — प्रति क्षेत्र रातें: स्थान की क्षमता के अनुसार रातें वितरित करें। "
        "महत्वपूर्ण शहरों और सुंदर क्षेत्रों को केवल ट्रांजिट स्टॉप से अधिक रातें मिलती हैं। "
        "महत्वपूर्ण — ड्राइव समय: कोई भी क्षेत्र परिवर्तन निर्दिष्ट अधिकतम ड्राइव समय से अधिक नहीं हो सकता। "
        "महत्वपूर्ण — रातों का बजट: सभी अनुशंसित रातों का योग निर्दिष्ट रातों के बजट के बराबर होना चाहिए। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class ArchitectPrePlanAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    def _build_prompt(self) -> str:
        req = self.request
        lang = getattr(req, 'language', 'de')
        leg = req.legs[0]  # Pre-plan is for the first transit leg
        nights_budget = leg.total_days - 1

        _L = {
            "de": {
                "styles_default": "allgemein",
                "desc_label": "Reisebeschreibung",
                "pref_label": "Bevorzugte Aktivitäten",
                "mandatory_label": "Pflichtaktivitäten",
                "header": "Erstelle einen Regionsplan für folgende Reise:",
                "from": "Von",
                "to": "Nach",
                "nights_budget": "Nächtebudget",
                "nights_sum_note": "Summe aller Regionen MUSS exakt {n} ergeben",
                "nights": "Nächte",
                "max_drive": "Maximale Fahrzeit pro Etappe",
                "styles": "Reisestile",
                "return_json": "Gib exakt dieses JSON zurück:",
                "rules": "Regeln",
                "rule1": "Summe aller recommended_nights = {n}",
                "rule2": "max_drive_hours pro Region <= {h}h",
                "rule3": "Regionen müssen logisch auf der Route zwischen {s} und {e} liegen",
                "rule4": "Verteile Nächte nach Potential: attraktive Orte bekommen mehr Nächte als Transitstopps",
            },
            "en": {
                "styles_default": "general",
                "desc_label": "Travel description",
                "pref_label": "Preferred activities",
                "mandatory_label": "Mandatory activities",
                "header": "Create a region plan for the following trip:",
                "from": "From",
                "to": "To",
                "nights_budget": "Nights budget",
                "nights_sum_note": "Sum of all regions MUST equal exactly {n}",
                "nights": "nights",
                "max_drive": "Maximum drive time per leg",
                "styles": "Travel styles",
                "return_json": "Return exactly this JSON:",
                "rules": "Rules",
                "rule1": "Sum of all recommended_nights = {n}",
                "rule2": "max_drive_hours per region <= {h}h",
                "rule3": "Regions must be logically located on the route between {s} and {e}",
                "rule4": "Distribute nights by potential: attractive places get more nights than transit stops",
            },
            "hi": {
                "styles_default": "सामान्य",
                "desc_label": "यात्रा विवरण",
                "pref_label": "पसंदीदा गतिविधियां",
                "mandatory_label": "अनिवार्य गतिविधियां",
                "header": "निम्नलिखित यात्रा के लिए एक क्षेत्र योजना बनाएं:",
                "from": "से",
                "to": "तक",
                "nights_budget": "रातों का बजट",
                "nights_sum_note": "सभी क्षेत्रों का योग बिल्कुल {n} होना चाहिए",
                "nights": "रातें",
                "max_drive": "प्रति चरण अधिकतम ड्राइव समय",
                "styles": "यात्रा शैलियां",
                "return_json": "बिल्कुल यह JSON लौटाएं:",
                "rules": "नियम",
                "rule1": "सभी recommended_nights का योग = {n}",
                "rule2": "प्रति क्षेत्र max_drive_hours <= {h}h",
                "rule3": "क्षेत्र {s} और {e} के बीच मार्ग पर तार्किक रूप से स्थित होने चाहिए",
                "rule4": "क्षमता के अनुसार रातें वितरित करें: आकर्षक स्थानों को ट्रांजिट स्टॉप से अधिक रातें मिलती हैं",
            },
        }
        L = _L.get(lang, _L["de"])

        styles_str = ", ".join(req.travel_styles) if req.travel_styles else L["styles_default"]
        desc_line = f"\n{L['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = (
            f"\n{L['pref_label']}: {', '.join(req.preferred_activities)}"
            if req.preferred_activities else ""
        )
        mandatory_line = (
            f"\n{L['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}"
            if req.mandatory_activities else ""
        )

        return f"""{L['header']}

{L['from']}: {leg.start_location}
{L['to']}: {leg.end_location}
{L['nights_budget']}: {nights_budget} {L['nights']} ({L['nights_sum_note'].format(n=nights_budget)})
{L['max_drive']}: {req.max_drive_hours_per_day}h
{L['styles']}: {styles_str}{desc_line}{pref_line}{mandatory_line}

{L['return_json']}
{{
  "regions": [
    {{"name": "Regionname", "recommended_nights": 2, "max_drive_hours": 3.0}},
    {{"name": "Regionname", "recommended_nights": 3, "max_drive_hours": 2.5}}
  ],
  "total_nights": {nights_budget}
}}

{L['rules']}:
1. {L['rule1'].format(n=nights_budget)}
2. {L['rule2'].format(h=req.max_drive_hours_per_day)}
3. {L['rule3'].format(s=leg.start_location, e=leg.end_location)}
4. {L['rule4']}"""

    async def run(self) -> dict:
        prompt = self._build_prompt()
        lang = getattr(self.request, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])

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
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(
            call,
            job_id=self.job_id,
            agent_name="ArchitectPrePlan",
            max_attempts=1,
        )
        return parse_agent_json(response.content[0].text)
