from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens
from utils.ferry_ports import is_island_destination, get_ferry_ports, ISLAND_GROUPS
from utils.maps_helper import geocode_google

AGENT_KEY = "route_architect"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Reiseplaner für Familien. "
        "Du pruefst die Plausibilitaet von Reisewuenschen und planst optimale Routen. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. "
        "Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a travel planner for families. "
        "You check the plausibility of travel requests and plan optimal routes. "
        "Reply ONLY with a valid JSON object. "
        "No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप परिवारों के लिए एक यात्रा योजनाकार हैं। "
        "आप यात्रा इच्छाओं की व्यवहार्यता की जांच करते हैं और इष्टतम मार्गों की योजना बनाते हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। "
        "कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class RouteArchitectAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self) -> dict:
        await debug_logger.log(
            LogLevel.AGENT, "RouteArchitect startet",
            job_id=self.job_id, agent="RouteArchitect",
        )

        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])

        _L = {
            "de": {
                "via_points": "Via-Punkte", "fixed_date": "Fixdatum",
                "mandatory": "Pflichtaktivitäten", "preferred": "Bevorzugte Aktivitäten",
                "style_routing": (
                    "ROUTENPLANUNG NACH REISESTIL: Die Route soll durch Regionen fuehren, die zum "
                    "Reisestil \"{styles}\" passen. Beispiel: Bei \"Strand\" -> Kuestenroute bevorzugen. "
                    "Bei \"Kultur\" -> Route durch historisch bedeutsame Regionen. "
                    "Bei \"Berge\" -> Alpenuebergaenge und Bergregionen. "
                    "Bei \"Natur\" -> Nationalparks und Naturschutzgebiete."
                ),
                "plausibility": (
                    "PLAUSIBILITAETSPRUEFUNG: Pruefe ob die angegebenen Reisestile ({styles}) "
                    "geographisch zum Zielgebiet ({dest}) passen. Wenn ein Reisestil "
                    "im Zielgebiet nicht umsetzbar ist (z.B. \"Vulkane\" in Frankreich, \"Strand\" in den Alpen), "
                    "fuege ein \"plausibility_warning\" Feld zum JSON hinzu mit:\n"
                    "- \"warning\": Erklaerung warum der Stil nicht zum Ziel passt\n"
                    "- \"suggestions\": Liste von 2-3 alternativen Reisestilen die besser passen\n"
                    "Wenn alle Stile zum Ziel passen, KEIN plausibility_warning Feld einfuegen."
                ),
                "island": (
                    "INSEL-ZIEL ERKANNT: {dest} liegt auf einer Insel ({group}). "
                    "Die Route MUSS einen Faehrhafen als eigenen Stopp beinhalten. "
                    "Uebliche Faehrhaefen fuer diese Region: {ports}. "
                    "Fuege den Faehrhafen als eigenen Stopp in die Route ein. "
                    "Trage die Faehrueberfahrt in ferry_crossings ein mit: "
                    "from_port, to_port, estimated_hours, estimated_cost_chf."
                ),
                "drive_limit_header": "FAHRZEITLIMIT (KRITISCH — MUSS eingehalten werden):",
                "drive_limit_1": "Maximale Fahrzeit pro Tag: {h}h (NUR reine Fahrzeit, OHNE Fährüberfahrten)",
                "drive_limit_2": "Fährzeit zählt NICHT als Fahrzeit. Wenn ein Tag 2h Fahrt + 4h Fähre hat, ist die Fahrzeit = 2h.",
                "drive_limit_3": "Jeder Stop muss ein drive_hours Feld haben, das NUR die Fahrzeit (ohne Fähre) angibt.",
                "drive_limit_4": "KEIN Stop darf drive_hours > {h}h haben.",
                "drive_limit_5": "Bei Inselzielen oder Fährüberfahrten: Plane einen Stopp VOR dem Fährhafen, damit die Fahrzeit zum Hafen unter dem Limit bleibt.",
                "drive_limit_6": "Wenn die Distanz zwischen zwei sinnvollen Stopps zu gross ist, füge einen zusätzlichen Zwischenstopp ein.",
                "plan_route": "Plane eine Reiseroute mit Zwischenstopps:",
                "start": "Start", "main_dest": "Hauptziel",
                "duration": "Reisedauer", "days": "Tage",
                "travelers": "Reisende", "adults": "Erwachsene", "children_age": "Kinder im Alter",
                "styles": "Reisestile", "styles_default": "allgemein",
                "desc_label": "Reisebeschreibung",
                "max_drive": "Maximale Fahrzeit pro Tag",
                "strict_note": "STRIKT — siehe FAHRZEITLIMIT unten",
                "nights_per_stop": "Nächte pro Stop",
                "budget": "Budget",
                "create_route": "Erstelle eine optimale Route. Der erste Stop MUSS der Startort sein, der letzte Stop MUSS das Hauptziel sein.",
                "intermediate": "Dazwischen plane 2–5 sinnvolle Zwischenstopps. Verteile die Tage sinnvoll.",
                "return_json": "Gib genau dieses JSON zurück:",
                "notes_start": "Startort", "notes_dest": "Hauptziel",
            },
            "en": {
                "via_points": "Via points", "fixed_date": "Fixed date",
                "mandatory": "Mandatory activities", "preferred": "Preferred activities",
                "style_routing": (
                    "ROUTE PLANNING BY TRAVEL STYLE: The route should pass through regions that match "
                    "the travel style \"{styles}\". Example: For \"beach\" -> prefer coastal route. "
                    "For \"culture\" -> route through historically significant regions. "
                    "For \"mountains\" -> alpine passes and mountain regions. "
                    "For \"nature\" -> national parks and nature reserves."
                ),
                "plausibility": (
                    "PLAUSIBILITY CHECK: Check whether the specified travel styles ({styles}) "
                    "geographically match the destination area ({dest}). If a travel style "
                    "is not feasible in the destination area (e.g. \"volcanoes\" in France, \"beach\" in the Alps), "
                    "add a \"plausibility_warning\" field to the JSON with:\n"
                    "- \"warning\": Explanation of why the style doesn't match the destination\n"
                    "- \"suggestions\": List of 2-3 alternative travel styles that fit better\n"
                    "If all styles match the destination, do NOT include a plausibility_warning field."
                ),
                "island": (
                    "ISLAND DESTINATION DETECTED: {dest} is on an island ({group}). "
                    "The route MUST include a ferry port as its own stop. "
                    "Common ferry ports for this region: {ports}. "
                    "Add the ferry port as its own stop in the route. "
                    "Enter the ferry crossing in ferry_crossings with: "
                    "from_port, to_port, estimated_hours, estimated_cost_chf."
                ),
                "drive_limit_header": "DRIVE TIME LIMIT (CRITICAL — MUST be respected):",
                "drive_limit_1": "Maximum drive time per day: {h}h (ONLY actual driving time, WITHOUT ferry crossings)",
                "drive_limit_2": "Ferry time does NOT count as drive time. If a day has 2h driving + 4h ferry, the drive time = 2h.",
                "drive_limit_3": "Each stop must have a drive_hours field that indicates ONLY driving time (without ferry).",
                "drive_limit_4": "NO stop may have drive_hours > {h}h.",
                "drive_limit_5": "For island destinations or ferry crossings: Plan a stop BEFORE the ferry port so the drive time to the port stays under the limit.",
                "drive_limit_6": "If the distance between two sensible stops is too large, add an additional intermediate stop.",
                "plan_route": "Plan a travel route with intermediate stops:",
                "start": "Start", "main_dest": "Main destination",
                "duration": "Travel duration", "days": "days",
                "travelers": "Travelers", "adults": "adults", "children_age": "children aged",
                "styles": "Travel styles", "styles_default": "general",
                "desc_label": "Travel description",
                "max_drive": "Maximum drive time per day",
                "strict_note": "STRICT — see DRIVE TIME LIMIT below",
                "nights_per_stop": "Nights per stop",
                "budget": "Budget",
                "create_route": "Create an optimal route. The first stop MUST be the starting point, the last stop MUST be the main destination.",
                "intermediate": "In between, plan 2-5 sensible intermediate stops. Distribute the days wisely.",
                "return_json": "Return exactly this JSON:",
                "notes_start": "Starting point", "notes_dest": "Main destination",
            },
            "hi": {
                "via_points": "वाया पॉइंट", "fixed_date": "निश्चित तिथि",
                "mandatory": "अनिवार्य गतिविधियां", "preferred": "पसंदीदा गतिविधियां",
                "style_routing": (
                    "यात्रा शैली के अनुसार मार्ग योजना: मार्ग उन क्षेत्रों से होकर गुजरना चाहिए जो "
                    "यात्रा शैली \"{styles}\" से मेल खाते हैं। उदाहरण: \"समुद्र तट\" -> तटीय मार्ग को प्राथमिकता दें। "
                    "\"संस्कृति\" -> ऐतिहासिक रूप से महत्वपूर्ण क्षेत्रों से होकर मार्ग। "
                    "\"पहाड़\" -> अल्पाइन दर्रे और पर्वतीय क्षेत्र। "
                    "\"प्रकृति\" -> राष्ट्रीय उद्यान और प्रकृति अभयारण्य।"
                ),
                "plausibility": (
                    "व्यवहार्यता जांच: जांचें कि निर्दिष्ट यात्रा शैलियां ({styles}) "
                    "भौगोलिक रूप से गंतव्य क्षेत्र ({dest}) से मेल खाती हैं। यदि कोई यात्रा शैली "
                    "गंतव्य क्षेत्र में संभव नहीं है (जैसे फ्रांस में \"ज्वालामुखी\", आल्प्स में \"समुद्र तट\"), "
                    "तो JSON में \"plausibility_warning\" फ़ील्ड जोड़ें:\n"
                    "- \"warning\": शैली गंतव्य से मेल क्यों नहीं खाती इसकी व्याख्या\n"
                    "- \"suggestions\": 2-3 वैकल्पिक यात्रा शैलियों की सूची जो बेहतर फिट होती हैं\n"
                    "यदि सभी शैलियां गंतव्य से मेल खाती हैं, तो plausibility_warning फ़ील्ड शामिल न करें।"
                ),
                "island": (
                    "द्वीप गंतव्य पहचाना गया: {dest} एक द्वीप ({group}) पर है। "
                    "मार्ग में एक नौका बंदरगाह अपने स्वयं के स्टॉप के रूप में शामिल होना चाहिए। "
                    "इस क्षेत्र के सामान्य नौका बंदरगाह: {ports}। "
                    "नौका बंदरगाह को मार्ग में अपने स्वयं के स्टॉप के रूप में जोड़ें। "
                    "नौका क्रॉसिंग को ferry_crossings में दर्ज करें: "
                    "from_port, to_port, estimated_hours, estimated_cost_chf."
                ),
                "drive_limit_header": "ड्राइव समय सीमा (महत्वपूर्ण — पालन अनिवार्य):",
                "drive_limit_1": "प्रति दिन अधिकतम ड्राइव समय: {h}h (केवल वास्तविक ड्राइविंग समय, नौका क्रॉसिंग के बिना)",
                "drive_limit_2": "नौका समय ड्राइव समय में नहीं गिना जाता। यदि एक दिन में 2h ड्राइविंग + 4h नौका है, तो ड्राइव समय = 2h।",
                "drive_limit_3": "प्रत्येक स्टॉप में drive_hours फ़ील्ड होना चाहिए जो केवल ड्राइविंग समय (नौका के बिना) दर्शाता है।",
                "drive_limit_4": "किसी भी स्टॉप का drive_hours > {h}h नहीं हो सकता।",
                "drive_limit_5": "द्वीप गंतव्यों या नौका क्रॉसिंग के लिए: नौका बंदरगाह से पहले एक स्टॉप की योजना बनाएं।",
                "drive_limit_6": "यदि दो उचित स्टॉप के बीच की दूरी बहुत अधिक है, तो एक अतिरिक्त मध्यवर्ती स्टॉप जोड़ें।",
                "plan_route": "मध्यवर्ती स्टॉप के साथ एक यात्रा मार्ग की योजना बनाएं:",
                "start": "शुरुआत", "main_dest": "मुख्य गंतव्य",
                "duration": "यात्रा अवधि", "days": "दिन",
                "travelers": "यात्रीगण", "adults": "वयस्क", "children_age": "बच्चे आयु",
                "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
                "desc_label": "यात्रा विवरण",
                "max_drive": "प्रति दिन अधिकतम ड्राइव समय",
                "strict_note": "सख्त — नीचे ड्राइव समय सीमा देखें",
                "nights_per_stop": "प्रति स्टॉप रातें",
                "budget": "बजट",
                "create_route": "एक इष्टतम मार्ग बनाएं। पहला स्टॉप प्रारंभ स्थान होना चाहिए, अंतिम स्टॉप मुख्य गंतव्य होना चाहिए।",
                "intermediate": "बीच में 2-5 उचित मध्यवर्ती स्टॉप की योजना बनाएं। दिनों को समझदारी से वितरित करें।",
                "return_json": "बिल्कुल यह JSON लौटाएं:",
                "notes_start": "प्रारंभ स्थान", "notes_dest": "मुख्य गंतव्य",
            },
        }
        L = _L.get(lang, _L["de"])

        children_ages = [c.age for c in req.children]
        via_str = ""
        if req.via_points:
            parts = []
            for vp in req.via_points:
                s = vp.location
                if vp.fixed_date:
                    s += f" ({L['fixed_date']}: {vp.fixed_date})"
                if vp.notes:
                    s += f" [{vp.notes}]"
                parts.append(s)
            via_str = f"{L['via_points']}: {', '.join(parts)}\n"

        mandatory_str = ""
        if req.mandatory_activities:
            acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
            mandatory_str = f"{L['mandatory']}: {', '.join(acts)}\n"

        pref_str = f"{L['preferred']}: {', '.join(req.preferred_activities)}\n" if req.preferred_activities else ""

        # Travel style routing block (D-06)
        style_block = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            style_block = "\n" + L["style_routing"].format(styles=styles_str) + "\n"

        # Plausibility check block (D-11, D-12)
        plausibility_block = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            plausibility_block = "\n" + L["plausibility"].format(styles=styles_str, dest=req.main_destination) + "\n"

        # Ferry detection block (D-02, D-04)
        ferry_block = ""
        island_group = None
        await debug_logger.log(
            LogLevel.API,
            f"Geocoding Ziel fuer Faehr-Erkennung: {req.main_destination}",
            job_id=self.job_id, agent="RouteArchitect",
        )
        dest_geo = await geocode_google(req.main_destination)
        if dest_geo:
            island_group = is_island_destination((dest_geo[0], dest_geo[1]))
            if island_group:
                ports = get_ferry_ports(island_group)
                ferry_block = "\n" + L["island"].format(
                    dest=req.main_destination, group=island_group, ports=", ".join(ports)
                ) + "\n"
                await debug_logger.log(
                    LogLevel.INFO,
                    f"Insel-Ziel erkannt: {req.main_destination} ({island_group}), Haefen: {', '.join(ports)}",
                    job_id=self.job_id, agent="RouteArchitect",
                )

        drive_limit_block = (
            f"\n{L['drive_limit_header']}\n"
            f"- {L['drive_limit_1'].format(h=req.max_drive_hours_per_day)}\n"
            f"- {L['drive_limit_2']}\n"
            f"- {L['drive_limit_3']}\n"
            f"- {L['drive_limit_4'].format(h=req.max_drive_hours_per_day)}\n"
            f"- {L['drive_limit_5']}\n"
            f"- {L['drive_limit_6']}\n"
        )

        children_note = f", {L['children_age']} {children_ages}" if children_ages else ""
        prompt = f"""{L['plan_route']}

{L['start']}: {req.start_location}
{via_str}{L['main_dest']}: {req.main_destination}
{L['duration']}: {req.total_days} {L['days']} ({req.start_date} – {req.end_date})
{L['travelers']}: {req.adults} {L['adults']}{children_note}
{L['styles']}: {', '.join(req.travel_styles) if req.travel_styles else L['styles_default']}
{f"{L['desc_label']}: {req.travel_description}" if req.travel_description else ''}
{L['max_drive']}: {req.max_drive_hours_per_day}h ({L['strict_note']})
{L['nights_per_stop']}: {req.min_nights_per_stop}–{req.max_nights_per_stop}
{L['budget']}: CHF {req.budget_chf:,.0f}
{mandatory_str}{pref_str}{style_block}{plausibility_block}{ferry_block}{drive_limit_block}
{L['create_route']}
{L['intermediate']}
{L['return_json']}
{{
  "stops": [
    {{"id": 1, "region": "{req.start_location}", "country": "CH", "arrival_day": 1, "nights": 0, "drive_hours": 0, "ferry_hours": 0, "is_fixed": false, "notes": "{L['notes_start']}"}},
    {{"id": 2, "region": "Annecy", "country": "FR", "arrival_day": 2, "nights": 2, "drive_hours": 3.5, "ferry_hours": 0, "is_fixed": false, "notes": "..."}},
    {{"id": 3, "region": "{req.main_destination}", "country": "FR", "arrival_day": 8, "nights": 3, "drive_hours": 4.0, "ferry_hours": 0, "is_fixed": false, "notes": "{L['notes_dest']}"}}
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
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RouteArchitect",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text

        await debug_logger.log(
            LogLevel.SUCCESS, "RouteArchitect abgeschlossen",
            job_id=self.job_id, agent="RouteArchitect",
        )

        parsed = parse_agent_json(text)

        # Plausibility challenge -- fire-and-forget SSE warning (per D-13)
        if parsed.get("plausibility_warning"):
            pw = parsed["plausibility_warning"]
            await debug_logger.push_event(self.job_id, "style_mismatch_warning", {
                "warning": pw.get("warning", ""),
                "suggestions": pw.get("suggestions", []),
                "original_styles": req.travel_styles,
            })
            await debug_logger.log(
                LogLevel.INFO,
                f"Plausibilitaetswarnung: {pw.get('warning', '')}",
                job_id=self.job_id, agent="RouteArchitect",
            )

        # Ferry detection SSE event
        if parsed.get("ferry_crossings"):
            await debug_logger.push_event(self.job_id, "ferry_detected", {
                "crossings": parsed["ferry_crossings"],
                "island_group": island_group,
            })

        return parsed
