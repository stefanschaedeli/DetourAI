"""Agent that interactively proposes intermediate stop options along a driving route, supporting both batch and streaming modes."""

import asyncio
import json
import re
from typing import AsyncIterator

from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.wikipedia import get_city_summary
from agents._client import get_client, get_model, get_max_tokens
from utils.ferry_ports import is_island_destination, validate_island_coordinates

AGENT_KEY = "stop_options_finder"

# Backward compat alias for tests
SYSTEM_PROMPT = None  # set after SYSTEM_PROMPTS definition

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Reiseplaner der Zwischenstopps entlang einer konkreten Fahrroute vorschlägt. "
        "KRITISCH — Regeln für das Feld 'region': "
        "Immer eine konkrete Ortschaft (Stadt, Dorf, Kleinstadt) angeben — NIEMALS Regionen, Gebirge, Länder oder Gebiete "
        "(z.B. NICHT 'Toskana', 'Alpen', 'Provence', 'Schwarzwald', sondern 'Siena', 'Annecy', 'Aix-en-Provence', 'Freiburg im Breisgau'). "
        "KRITISCH — Geographie: Vorgeschlagene Stopps müssen ZWISCHEN dem aktuellen Standort und dem Ziel liegen, "
        "nicht hinter dem Ziel oder in eine andere Richtung. Orientiere dich an den Referenzorten entlang der Route. "
        "KRITISCH — Fahrzeiten: Jede Option muss drive_hours ≤ dem angegebenen Maximum einhalten. "
        "Wähle nähere Zwischenstopps wenn nötig — lieber einen kürzeren Etappenstopp als das Limit zu überschreiten. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON. "
        "STIL-REGEL: Wenn Reisestile angegeben sind, muessen mindestens 2 der 3 Optionen "
        "dem Reisestil entsprechen. Die 3. Option darf ein interessanter Wildcard-Vorschlag sein. "
        "Kennzeichne in jedem Vorschlag: \"matches_travel_style\": true/false. "
    ),
    "en": (
        "You are a travel planner who suggests intermediate stops along a specific driving route. "
        "CRITICAL — Rules for the 'region' field: "
        "Always specify a concrete settlement (city, town, village) — NEVER regions, mountain ranges, countries or areas "
        "(e.g. NOT 'Tuscany', 'Alps', 'Provence', 'Black Forest', but 'Siena', 'Annecy', 'Aix-en-Provence', 'Freiburg im Breisgau'). "
        "CRITICAL — Geography: Suggested stops must be BETWEEN the current location and the destination, "
        "not behind the destination or in another direction. Use the reference cities along the route as guidance. "
        "CRITICAL — Drive times: Each option must have drive_hours <= the specified maximum. "
        "Choose closer intermediate stops if needed — better a shorter leg stop than exceeding the limit. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON. "
        "STYLE RULE: If travel styles are specified, at least 2 of 3 options "
        "must match the travel style. The 3rd option may be an interesting wildcard suggestion. "
        "Mark each suggestion: \"matches_travel_style\": true/false. "
    ),
    "hi": (
        "आप एक यात्रा योजनाकार हैं जो एक विशिष्ट ड्राइविंग मार्ग के साथ मध्यवर्ती स्टॉप सुझाते हैं। "
        "महत्वपूर्ण — 'region' फ़ील्ड के नियम: "
        "हमेशा एक ठोस बस्ती (शहर, कस्बा, गांव) निर्दिष्ट करें — कभी भी क्षेत्र, पर्वत श्रृंखला, देश या इलाके नहीं। "
        "महत्वपूर्ण — भूगोल: सुझाए गए स्टॉप वर्तमान स्थान और गंतव्य के बीच होने चाहिए, "
        "गंतव्य के पीछे या किसी अन्य दिशा में नहीं। "
        "महत्वपूर्ण — ड्राइव समय: प्रत्येक विकल्प का drive_hours <= निर्दिष्ट अधिकतम होना चाहिए। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON। "
        "शैली नियम: यदि यात्रा शैलियां निर्दिष्ट हैं, तो 3 में से कम से कम 2 विकल्प "
        "यात्रा शैली से मेल खाने चाहिए। तीसरा विकल्प एक दिलचस्प वाइल्डकार्ड सुझाव हो सकता है। "
        "प्रत्येक सुझाव में चिह्नित करें: \"matches_travel_style\": true/false। "
    ),
}
SYSTEM_PROMPT = SYSTEM_PROMPTS["de"]  # backward compat for tests


class StopOptionsFinderAgent:
    """Agent that generates exactly 3 localized stop options for each interactive route-building step, with Wikipedia enrichment and island validation."""

    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    def _build_prompt(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int,
        segment_count: int,
        extra_instructions: str,
        route_geometry: dict,
        architect_context: dict = None,
    ) -> str:
        """Build a fully localized prompt for Claude to suggest 3 stop options, incorporating route geometry, architect context, and travel style guidance."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        geo = route_geometry or {}
        is_rundreise = geo.get("rundreise_mode", False)

        # Prompt label translations
        _L = {
            "de": {
                "previous_stops": "bisherige Stopps", "last": "letzte",
                "nights": "Nächte", "km_from_prev": "km vom Vorgänger",
                "exclusion": "KRITISCH — Duplikat-Vermeidung: Schlage KEINEN der folgenden bereits ausgewählten Stopps erneut vor: ",
                "exclusion_suffix": ". Diese Orte sind bereits Teil der Route.",
                "complete_hint": "Hinweis: Die Route könnte mit diesem Stop abgeschlossen werden (Ziel: {target}). Mindestens eine Option sollte direkt zum Ziel führen.",
                "extra_hint": "Sonderwunsch des Nutzers: ",
                "total_dist": "Gesamtstrecke",
                "drive_time": "Fahrzeit",
                "remaining_stops": "Empfohlene Anzahl weiterer Stopps bis",
                "ideal_dist": "Ideale Distanz dieses Stops vom letzten Stop",
                "choose_places": "Wähle Orte die ca. {km} km von {prev} entfernt liegen, NICHT direkt am Start und NICHT direkt am Ziel.",
                "corridor": "ROUTE-KORRIDOR: Die Fahrroute verläuft durch/nahe: {cities}. Suche Stopps in diesem Bereich oder in der unmittelbaren Umgebung dieser Route.",
                "search_area": "SUCHBEREICH (±30 km entlang der Fahrroute):",
                "all_in_area": "Alle 3 Optionen MÜSSEN in diesem geographischen Bereich liegen.",
                "architect_rec": "ARCHITECT-EMPFEHLUNG",
                "nights_hints": "Die Nächteangaben sind Empfehlungen basierend auf dem Potential der Orte — du kannst davon abweichen.",
                "for_this_stop": "FÜR DIESEN STOP: Empfehle {n} Nächte (basierend auf Potential der Region {name}).",
                "direction_ctx": "RICHTUNGSKONTEXT: Vom letzten Stopp ({prev}) zum Ziel ({target}) betraegt die Fahrtrichtung ca. {bearing} Grad. WICHTIG: Schlage NUR Orte vor, die grob in dieser Richtung liegen. Keine Rueckwaertsfahrten oder starke Umwege (> 90 Grad Abweichung).",
                "rundreise_mode": "RUNDREISE-MODUS AKTIV: Wir haben viel Zeit — suche Orte die einen bewussten Umweg darstellen.",
                "suggest_3": "Schlage genau 3 verschiedene Optionen vor:",
                "suggest_3_for": "Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor",
                "direct": "direkt an der Hauptroute Richtung",
                "scenic": "landschaftlich schöne Alternative",
                "cultural": "kulturell interessante Alternative",
                "near_route": "nahe der Route",
                "shortest": "kürzeste Route Richtung",
                "umweg_links": "Umweg links/westlich der Direktroute",
                "umweg_rechts": "Umweg rechts/östlich der Direktroute",
                "abenteuer": "überraschende andere Richtung, maximaler Kontrast zur Direktroute",
                "rules_header": "PFLICHT — alle {n} Regeln einhalten:",
                "rule_drive": "drive_hours von {prev} zu diesem Stop: ≤ {h}h",
                "rule_dist": "Distanz: ~{km} km von {prev}",
                "rule_tolerance": "Toleranz ±30%; NICHT unter {km} km — zu nahe am letzten Stop",
                "rule_tolerance_rund": "Toleranz ±40% — bewusst größerer Bereich als normal",
                "rule_origin": "NICHT zu nahe am Reise-Startpunkt {origin}: min {km} km Luftlinie",
                "rule_target": "NICHT zu nahe am Ziel {target}: min {km} km Luftlinie",
                "rule_split": "Teile lange Strecken auf — niemals direkt zum Ziel springen wenn noch {n} Etappe(n) geplant sind",
                "rule_direction": "RICHTUNG: Der Stop muss geographisch ZWISCHEN {prev} und {target} liegen — NICHT hinter dem Ziel und NICHT in die entgegengesetzte Richtung. Nutze die Route-Referenzorte als Orientierung.",
                "rule_area": "SUCHBEREICH: Wenn ein geographischer Suchbereich (Lat/Lon) angegeben ist, müssen alle Optionen innerhalb dieses Bereichs liegen. Prüfe die lat/lon-Koordinaten deiner Vorschläge gegen den angegebenen Bereich.",
                "rule_no_target": "Gehe BEWUSST NICHT Richtung {target} — wähle Orte seitlich oder entgegengesetzt",
                "style_pref": "REISESTIL-PRAEFERENZ: Der Nutzer bevorzugt \"{styles}\". Mindestens 2 von 3 Optionen muessen diesem Stil entsprechen. Die 3. Option darf ein ueberraschender Geheimtipp sein.",
                "desc_label": "Reisebeschreibung",
                "pref_label": "Bevorzugte Aktivitäten",
                "mandatory_label": "Pflichtaktivitäten",
                "segment": "Segment", "of": "von", "direction": "Richtung",
                "trip_start": "Start der Gesamtreise",
                "last_stop": "Letzter Stop (Abfahrtspunkt)",
                "segment_dest": "Endziel dieses Segments",
                "current_stop": "Aktueller Stop",
                "remaining_days": "Verbleibende Tage im Segment",
                "max_drive": "Maximale Fahrzeit pro Etappe",
                "styles": "Reisestile", "styles_default": "allgemein",
                "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder", "age": "Alter",
                "nights_range": "Nächte",
                "population": "Einwohnerzahl als lesbarer String",
                "inhabitants": "Einwohner",
                "altitude": "Meereshöhe in Metern",
                "language_field": "Hauptsprache der Region",
                "climate": "Klimahinweis passend zur Reisezeit",
                "must_see": "Top 2-3 Sehenswürdigkeiten passend zu den Reisestilen",
                "family_friendly": "Kinder reisen mit",
                "teaser_hint": "WICHTIG — 3-4 Sätze (~100-150 Wörter). Erkläre WARUM dieser Stopp perfekt zur Reise passt.",
                "teaser_ref": "Beziehe dich konkret auf die Reisestile ({styles}), die Reisenden ({travelers}) und was diesen Ort besonders macht. Keine generischen Floskeln — überzeugend und spezifisch begründen.",
                "tags_hint": "3-4 kurze Schlagworte die den Charakter und die Staerken des Stopps beschreiben",
                "tags_examples": "z.B. \"Strand\", \"Kultur\", \"Wandern\", \"Kueste\", \"Insel\", \"Natur\", \"Berge\", \"Altstadt\", \"Weinregion\", \"Familienfreundlich\"",
                "return_json": "Gib exakt dieses JSON zurück. lat/lon = WGS84-Koordinaten des Stadtzentrums (PFLICHT – keine null):",
                "fill_fields": "Befülle folgende Felder kontextabhängig:",
                "travel_date": "unbekannt",
            },
            "en": {
                "previous_stops": "Previous stops", "last": "last",
                "nights": "nights", "km_from_prev": "km from previous",
                "exclusion": "CRITICAL — Duplicate prevention: Do NOT suggest any of the following already selected stops again: ",
                "exclusion_suffix": ". These places are already part of the route.",
                "complete_hint": "Note: The route could be completed with this stop (destination: {target}). At least one option should lead directly to the destination.",
                "extra_hint": "Special request from user: ",
                "total_dist": "Total distance",
                "drive_time": "drive time",
                "remaining_stops": "Recommended number of further stops until",
                "ideal_dist": "Ideal distance of this stop from the last stop",
                "choose_places": "Choose places approximately {km} km from {prev}, NOT right at the start and NOT right at the destination.",
                "corridor": "ROUTE CORRIDOR: The driving route passes through/near: {cities}. Search for stops in this area or in the immediate vicinity of this route.",
                "search_area": "SEARCH AREA (±30 km along the driving route):",
                "all_in_area": "All 3 options MUST be within this geographic area.",
                "architect_rec": "ARCHITECT RECOMMENDATION",
                "nights_hints": "Night recommendations are based on the potential of the places — you can deviate.",
                "for_this_stop": "FOR THIS STOP: Recommend {n} nights (based on the potential of region {name}).",
                "direction_ctx": "DIRECTION CONTEXT: From the last stop ({prev}) to the destination ({target}) the travel direction is approx. {bearing} degrees. IMPORTANT: Only suggest places that are roughly in this direction. No backtracking or major detours (> 90 degree deviation).",
                "rundreise_mode": "ROUND TRIP MODE ACTIVE: We have plenty of time — search for places that represent a deliberate detour.",
                "suggest_3": "Suggest exactly 3 different options:",
                "suggest_3_for": "Suggest exactly 3 different options for the next intermediate stop",
                "direct": "directly on the main route towards",
                "scenic": "scenic alternative",
                "cultural": "culturally interesting alternative",
                "near_route": "near the route",
                "shortest": "shortest route towards",
                "umweg_links": "Detour left/west of the direct route",
                "umweg_rechts": "Detour right/east of the direct route",
                "abenteuer": "surprising different direction, maximum contrast to direct route",
                "rules_header": "MANDATORY — follow all {n} rules:",
                "rule_drive": "drive_hours from {prev} to this stop: <= {h}h",
                "rule_dist": "Distance: ~{km} km from {prev}",
                "rule_tolerance": "Tolerance ±30%; NOT under {km} km — too close to last stop",
                "rule_tolerance_rund": "Tolerance ±40% — deliberately larger range than normal",
                "rule_origin": "NOT too close to trip start {origin}: min {km} km as the crow flies",
                "rule_target": "NOT too close to destination {target}: min {km} km as the crow flies",
                "rule_split": "Split long distances — never jump directly to destination when {n} leg(s) are still planned",
                "rule_direction": "DIRECTION: The stop must be geographically BETWEEN {prev} and {target} — NOT behind the destination and NOT in the opposite direction. Use the route reference cities as guidance.",
                "rule_area": "SEARCH AREA: If a geographic search area (Lat/Lon) is specified, all options must be within this area. Check the lat/lon coordinates of your suggestions against the specified area.",
                "rule_no_target": "Do NOT go towards {target} — choose places to the side or in the opposite direction",
                "style_pref": "TRAVEL STYLE PREFERENCE: The user prefers \"{styles}\". At least 2 of 3 options must match this style. The 3rd option may be a surprising hidden gem.",
                "desc_label": "Travel description",
                "pref_label": "Preferred activities",
                "mandatory_label": "Mandatory activities",
                "segment": "Segment", "of": "of", "direction": "towards",
                "trip_start": "Start of entire trip",
                "last_stop": "Last stop (departure point)",
                "segment_dest": "Final destination of this segment",
                "current_stop": "Current stop",
                "remaining_days": "Remaining days in segment",
                "max_drive": "Maximum drive time per leg",
                "styles": "Travel styles", "styles_default": "general",
                "travelers": "Travelers", "adults": "adults", "children": "children", "age": "age",
                "nights_range": "Nights",
                "population": "Population as readable string",
                "inhabitants": "inhabitants",
                "altitude": "Altitude in meters",
                "language_field": "Main language of the region",
                "climate": "Climate note for the travel period",
                "must_see": "Top 2-3 sights matching the travel styles",
                "family_friendly": "Children are traveling along",
                "teaser_hint": "IMPORTANT — 3-4 sentences (~100-150 words). Explain WHY this stop is perfect for the trip.",
                "teaser_ref": "Refer specifically to travel styles ({styles}), travelers ({travelers}) and what makes this place special. No generic phrases — convincing and specific reasoning.",
                "tags_hint": "3-4 short keywords describing the character and strengths of the stop",
                "tags_examples": "e.g. \"Beach\", \"Culture\", \"Hiking\", \"Coast\", \"Island\", \"Nature\", \"Mountains\", \"Old Town\", \"Wine Region\", \"Family-Friendly\"",
                "return_json": "Return exactly this JSON. lat/lon = WGS84 coordinates of the city center (REQUIRED — no null):",
                "fill_fields": "Fill in the following fields contextually:",
                "travel_date": "unknown",
            },
            "hi": {
                "previous_stops": "पिछले स्टॉप", "last": "अंतिम",
                "nights": "रातें", "km_from_prev": "पिछले से km",
                "exclusion": "महत्वपूर्ण — डुप्लिकेट रोकथाम: निम्नलिखित पहले से चयनित स्टॉप में से कोई भी फिर से सुझाव न दें: ",
                "exclusion_suffix": "। ये स्थान पहले से मार्ग का हिस्सा हैं।",
                "complete_hint": "नोट: इस स्टॉप के साथ मार्ग पूरा हो सकता है (गंतव्य: {target})। कम से कम एक विकल्प सीधे गंतव्य की ओर ले जाना चाहिए।",
                "extra_hint": "उपयोगकर्ता का विशेष अनुरोध: ",
                "total_dist": "कुल दूरी",
                "drive_time": "ड्राइव समय",
                "remaining_stops": "तक शेष स्टॉप की अनुशंसित संख्या",
                "ideal_dist": "अंतिम स्टॉप से इस स्टॉप की आदर्श दूरी",
                "choose_places": "{prev} से लगभग {km} km दूर स्थान चुनें, शुरुआत के पास नहीं और गंतव्य के पास नहीं।",
                "corridor": "मार्ग गलियारा: ड्राइविंग मार्ग {cities} से होकर गुजरता है। इस क्षेत्र में स्टॉप खोजें।",
                "search_area": "खोज क्षेत्र (ड्राइविंग मार्ग के साथ ±30 km):",
                "all_in_area": "सभी 3 विकल्प इस भौगोलिक क्षेत्र में होने चाहिए।",
                "architect_rec": "आर्किटेक्ट अनुशंसा",
                "nights_hints": "रातों के सुझाव स्थानों की क्षमता पर आधारित हैं — आप विचलित हो सकते हैं।",
                "for_this_stop": "इस स्टॉप के लिए: {n} रातों की अनुशंसा ({name} क्षेत्र की क्षमता के आधार पर)।",
                "direction_ctx": "दिशा संदर्भ: अंतिम स्टॉप ({prev}) से गंतव्य ({target}) तक यात्रा दिशा लगभग {bearing} डिग्री है। केवल इस दिशा में स्थान सुझाएं।",
                "rundreise_mode": "राउंड ट्रिप मोड सक्रिय: हमारे पास काफी समय है — जानबूझकर चक्कर लगाने वाले स्थान खोजें।",
                "suggest_3": "बिल्कुल 3 अलग-अलग विकल्प सुझाएं:",
                "suggest_3_for": "अगले मध्यवर्ती स्टॉप के लिए बिल्कुल 3 अलग-अलग विकल्प सुझाएं",
                "direct": "मुख्य मार्ग पर सीधे दिशा में",
                "scenic": "प्राकृतिक सुंदर विकल्प",
                "cultural": "सांस्कृतिक रूप से दिलचस्प विकल्प",
                "near_route": "मार्ग के पास",
                "shortest": "सबसे छोटा मार्ग दिशा में",
                "umweg_links": "सीधे मार्ग के बाएं/पश्चिम में चक्कर",
                "umweg_rechts": "सीधे मार्ग के दाएं/पूर्व में चक्कर",
                "abenteuer": "आश्चर्यजनक अलग दिशा, सीधे मार्ग से अधिकतम विपरीत",
                "rules_header": "अनिवार्य — सभी {n} नियमों का पालन करें:",
                "rule_drive": "{prev} से इस स्टॉप तक drive_hours: <= {h}h",
                "rule_dist": "दूरी: ~{km} km {prev} से",
                "rule_tolerance": "सहनशीलता ±30%; {km} km से कम नहीं — अंतिम स्टॉप के बहुत करीब",
                "rule_tolerance_rund": "सहनशीलता ±40% — सामान्य से जानबूझकर बड़ा क्षेत्र",
                "rule_origin": "यात्रा प्रारंभ {origin} के बहुत करीब नहीं: न्यूनतम {km} km",
                "rule_target": "गंतव्य {target} के बहुत करीब नहीं: न्यूनतम {km} km",
                "rule_split": "लंबी दूरियों को विभाजित करें — जब {n} चरण अभी भी योजनाबद्ध हैं तो सीधे गंतव्य पर न जाएं",
                "rule_direction": "दिशा: स्टॉप भौगोलिक रूप से {prev} और {target} के बीच होना चाहिए।",
                "rule_area": "खोज क्षेत्र: यदि भौगोलिक खोज क्षेत्र निर्दिष्ट है, तो सभी विकल्प इस क्षेत्र में होने चाहिए।",
                "rule_no_target": "{target} की ओर न जाएं — बगल या विपरीत दिशा में स्थान चुनें",
                "style_pref": "यात्रा शैली वरीयता: उपयोगकर्ता \"{styles}\" पसंद करता है। 3 में से कम से कम 2 विकल्प इस शैली से मेल खाने चाहिए।",
                "desc_label": "यात्रा विवरण",
                "pref_label": "पसंदीदा गतिविधियां",
                "mandatory_label": "अनिवार्य गतिविधियां",
                "segment": "खंड", "of": "का", "direction": "दिशा",
                "trip_start": "संपूर्ण यात्रा की शुरुआत",
                "last_stop": "अंतिम स्टॉप (प्रस्थान बिंदु)",
                "segment_dest": "इस खंड का अंतिम गंतव्य",
                "current_stop": "वर्तमान स्टॉप",
                "remaining_days": "खंड में शेष दिन",
                "max_drive": "प्रति चरण अधिकतम ड्राइव समय",
                "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
                "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे", "age": "आयु",
                "nights_range": "रातें",
                "population": "जनसंख्या",
                "inhabitants": "निवासी",
                "altitude": "ऊंचाई मीटर में",
                "language_field": "क्षेत्र की मुख्य भाषा",
                "climate": "यात्रा अवधि के लिए जलवायु नोट",
                "must_see": "यात्रा शैलियों से मेल खाने वाले शीर्ष 2-3 दर्शनीय स्थल",
                "family_friendly": "बच्चे साथ यात्रा कर रहे हैं",
                "teaser_hint": "महत्वपूर्ण — 3-4 वाक्य। बताएं कि यह स्टॉप यात्रा के लिए क्यों सही है।",
                "teaser_ref": "यात्रा शैलियों ({styles}), यात्रियों ({travelers}) और इस स्थान को विशेष बनाने वाली बातों का विशेष रूप से उल्लेख करें।",
                "tags_hint": "स्टॉप के चरित्र और ताकत का वर्णन करने वाले 3-4 छोटे कीवर्ड",
                "tags_examples": "जैसे \"समुद्र तट\", \"संस्कृति\", \"लंबी पैदल यात्रा\", \"तट\", \"द्वीप\", \"प्रकृति\", \"पहाड़\", \"पुराना शहर\"",
                "return_json": "बिल्कुल यह JSON लौटाएं। lat/lon = शहर के केंद्र के WGS84 निर्देशांक (अनिवार्य — कोई null नहीं):",
                "fill_fields": "निम्नलिखित फ़ील्ड संदर्भानुसार भरें:",
                "travel_date": "अज्ञात",
            },
        }
        L = _L.get(lang, _L["de"])

        prev_stop = selected_stops[-1]["region"] if selected_stops else req.start_location

        MAX_HISTORY_FULL = 8
        TAIL_COUNT = 5

        capped_stops = selected_stops
        history_prefix = ""
        if len(selected_stops) > MAX_HISTORY_FULL:
            capped_stops = selected_stops[-TAIL_COUNT:]
            history_prefix = f"{len(selected_stops)} {L['previous_stops']}, {L['last']} {TAIL_COUNT}: "

        stops_str = ""
        if selected_stops:
            parts = [
                f"Stop {s['id']}: {s['region']} ({s.get('country','?')}, {s.get('nights',1)} {L['nights']}, {s.get('drive_km','?')} {L['km_from_prev']})"
                for s in capped_stops
            ]
            # Capitalize label at start of line
            label_cap = L['previous_stops'][0].upper() + L['previous_stops'][1:]
            stops_str = f"{label_cap}: {history_prefix}" + ", ".join(parts) + "\n"

        exclusion_rule = ""
        if selected_stops:
            excluded_names = ", ".join(s["region"] for s in selected_stops)
            exclusion_rule = L["exclusion"] + excluded_names + L["exclusion_suffix"] + "\n"

        complete_hint = ""
        if route_could_be_complete:
            complete_hint = "\n" + L["complete_hint"].format(target=segment_target) + "\n"

        has_children = bool(req.children)
        family_field = '"family_friendly": true,' if has_children else ""

        extra_hint = ""
        if extra_instructions:
            extra_hint = f"\n{L['extra_hint']}{extra_instructions}\n"

        # Build geometry context block
        geo_lines = []
        if geo.get("segment_total_km"):
            geo_lines.append(
                f"{L['total_dist']} {prev_stop} → {segment_target}: ~{geo['segment_total_km']:.0f} km / ~{geo.get('segment_total_hours', 0):.1f}h {L['drive_time']}"
            )
        if geo.get("stops_remaining") is not None:
            geo_lines.append(f"{L['remaining_stops']} {segment_target}: {geo['stops_remaining']}")
        if geo.get("ideal_km_from_prev"):
            geo_lines.append(
                f"{L['ideal_dist']}: ~{geo['ideal_km_from_prev']:.0f} km / ~{geo.get('ideal_hours_from_prev', 0):.1f}h"
            )
            if not is_rundreise:
                ideal_km_str = f"{geo['ideal_km_from_prev']:.0f}"
                geo_lines.append(
                    f"→ {L['choose_places'].format(km=ideal_km_str, prev=prev_stop)}"
                )

        # Corridor reference cities for transit mode
        ref_cities = geo.get("corridor_reference_cities", [])
        if ref_cities and not is_rundreise:
            geo_lines.append(L["corridor"].format(cities=", ".join(ref_cities)))

        # Bounding box as hard limit
        box = geo.get("corridor_box")
        if box and not is_rundreise:
            geo_lines.append(
                f"{L['search_area']} "
                f"Lat {box['min_lat']:.2f}–{box['max_lat']:.2f}, Lon {box['min_lon']:.2f}–{box['max_lon']:.2f}. "
                f"{L['all_in_area']}"
            )

        geo_block = "\n".join(geo_lines) + "\n" if geo_lines else ""

        # Architect pre-plan context block (RTE-02)
        architect_block = ""
        if architect_context:
            regions = architect_context.get("regions", [])
            if regions:
                region_lines = []
                for r in regions:
                    nights_hint = f"{r['recommended_nights']}N"
                    drive_hint = f", ~{r['max_drive_hours']}h" if r.get('max_drive_hours') else ""
                    region_lines.append(f"{r['name']} ({nights_hint}{drive_hint})")
                summary = " → ".join(region_lines)
                architect_block = (
                    f"\n{L['architect_rec']}: {summary}\n"
                    f"{L['nights_hints']}\n"
                )
                # D-07: Per-stop nights suggestion based on position in region list
                estimated_total = architect_context.get("estimated_total_stops", len(regions))
                if estimated_total > 0:
                    region_idx = min(
                        int((stop_number - 1) / max(1, estimated_total) * len(regions)),
                        len(regions) - 1
                    )
                    current_region = regions[region_idx]
                    rec_nights = current_region.get("recommended_nights", 2)
                    architect_block += L["for_this_stop"].format(n=rec_nights, name=current_region['name']) + "\n"

        # Bearing context for backtracking prevention (D-10)
        prev_coords = geo.get("_from_coords")
        target_coords = geo.get("_to_coords")
        bearing_block = ""
        if prev_coords and target_coords and not is_rundreise:
            from utils.maps_helper import bearing_degrees
            prev_lat, prev_lon = prev_coords if prev_coords else (None, None)
            target_lat, target_lon = target_coords if target_coords else (None, None)
            if prev_lat and target_lat:
                route_bearing = bearing_degrees((prev_lat, prev_lon), (target_lat, target_lon))
                bearing_block = "\n" + L["direction_ctx"].format(
                    prev=prev_stop, target=segment_target, bearing=f"{route_bearing:.0f}"
                ) + "\n"

        # Option-type block
        if is_rundreise:
            option_block = (
                f"{L['rundreise_mode']}\n"
                f"{L['suggest_3']}\n"
                f'- option_type "umweg_links": {L["umweg_links"]}\n'
                f'- option_type "umweg_rechts": {L["umweg_rechts"]}\n'
                f'- option_type "abenteuer": {L["abenteuer"]}\n'
            )
        else:
            ref_cities = geo.get("corridor_reference_cities", [])
            if ref_cities:
                ref_str = ", ".join(ref_cities)
                option_block = (
                    f"{L['suggest_3_for']} ({ref_str}):\n"
                    f'- option_type "direct": {L["direct"]} {segment_target}\n'
                    f'- option_type "scenic": {L["scenic"]} {L["near_route"]}\n'
                    f'- option_type "cultural": {L["cultural"]} {L["near_route"]}\n'
                )
            else:
                option_block = (
                    f"{L['suggest_3_for']}:\n"
                    f'- option_type "direct": {L["shortest"]} {segment_target}\n'
                    f'- option_type "scenic": {L["scenic"]}\n'
                    f'- option_type "cultural": {L["cultural"]}\n'
                )

        # Rules block
        ideal_km = geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80)
        ideal_km_str = f"{ideal_km:.0f}"
        half_km_str = f"{ideal_km * 0.5:.0f}"
        origin_loc = geo.get('origin_location', req.start_location)
        min_origin_km = f"{geo.get('min_km_from_origin', 0):.0f}"
        min_target_km = f"{geo.get('min_km_from_target', 0):.0f}"

        if is_rundreise:
            rules_block = (
                f"{L['rules_header'].format(n=4)}\n"
                f"1. {L['rule_drive'].format(prev=prev_stop, h=req.max_drive_hours_per_day)}\n"
                f"2. {L['rule_dist'].format(km=ideal_km_str, prev=prev_stop)}\n"
                f"   ({L['rule_tolerance_rund']})\n"
                f"3. {L['rule_origin'].format(origin=origin_loc, km=min_origin_km)}\n"
                f"4. {L['rule_no_target'].format(target=segment_target)}\n"
            )
        else:
            rules_block = (
                f"{L['rules_header'].format(n=7)}\n"
                f"1. {L['rule_drive'].format(prev=prev_stop, h=req.max_drive_hours_per_day)}\n"
                f"2. {L['rule_dist'].format(km=ideal_km_str, prev=prev_stop)}\n"
                f"   ({L['rule_tolerance'].format(km=half_km_str)})\n"
                f"3. {L['rule_origin'].format(origin=origin_loc, km=min_origin_km)}\n"
                f"4. {L['rule_target'].format(target=segment_target, km=min_target_km)}\n"
                f"5. {L['rule_split'].format(n=geo.get('stops_remaining', 1))}\n"
                f"6. {L['rule_direction'].format(prev=prev_stop, target=segment_target)}\n"
                f"7. {L['rule_area']}\n"
            )

        # Travel style emphasis (D-05)
        style_emphasis = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            style_emphasis = "\n" + L["style_pref"].format(styles=styles_str) + "\n"

        # Optionale Wunsch-Kontextblöcke (CTX-02, CTX-03)
        desc_line = f"\n{L['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{L['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{L['mandatory_label']}: {', '.join(f'{a.name}' + (f' ({a.location})' if a.location else '') for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        # JSON example option_types
        if is_rundreise:
            ex1_type = "umweg_links"
            ex2_type = "umweg_rechts"
            ex3_type = "abenteuer"
        else:
            ex1_type = "direct"
            ex2_type = "scenic"
            ex3_type = "cultural"

        travelers_str = f"{req.adults} {L['adults']}"
        if req.children:
            travelers_str += f", {len(req.children)} {L['children']} ({L['age']}: {', '.join(str(c) for c in req.children)})"
        styles_display = ', '.join(req.travel_styles) if req.travel_styles else L['styles_default']

        return f"""{L['segment']} {segment_index + 1} {L['of']} {segment_count} {L['direction']}: {segment_target}

{L['trip_start']}: {req.start_location}
{L['last_stop']}: {prev_stop}
{L['segment_dest']}: {segment_target}
{L['current_stop']} #{stop_number}
{stops_str}{exclusion_rule}
{geo_block}{architect_block}{bearing_block}{L['remaining_days']}: {days_remaining}
{L['max_drive']}: {req.max_drive_hours_per_day}h
{L['styles']}: {styles_display}
{L['travelers']}: {travelers_str}
{complete_hint}{extra_hint}
{option_block}{style_emphasis}{mandatory_line}{pref_line}{desc_line}
{rules_block}{L['nights_range']}: {req.min_nights_per_stop}–{req.max_nights_per_stop}.

{L['fill_fields']}:
- population: {L['population']} (z.B. "45'000 {L['inhabitants']}"), falls bekannt
- altitude_m: {L['altitude']}
- language: {L['language_field']}
- climate_note: {L['climate']} ({getattr(req, 'start_date', L['travel_date'])})
- must_see: {L['must_see']} {styles_display}
{(f'- family_friendly: true/false ({L["family_friendly"]})' if has_children else '')}
- teaser: {L['teaser_hint']}
  {L['teaser_ref'].format(styles=styles_display, travelers=travelers_str)}
- tags: {L['tags_hint']}
  ({L['tags_examples']})

{L['return_json']}
{{
  "options": [
    {{"id": 1, "option_type": "{ex1_type}", "region": "...", "country": "FR", "lat": 45.7640, "lon": 4.8357, "drive_hours": 3.5, "drive_km": 280, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true, "tags": ["Kultur", "Altstadt", "Kulinarik"]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 2, "option_type": "{ex2_type}", "region": "...", "country": "FR", "lat": 45.9237, "lon": 6.8694, "drive_hours": 4.0, "drive_km": 320, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": 1200, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true, "tags": ["Berge", "Natur", "Wandern"]{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 3, "option_type": "{ex3_type}", "region": "...", "country": "FR", "lat": 43.2965, "lon": 5.3698, "drive_hours": 3.0, "drive_km": 250, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true, "tags": ["Kueste", "Strand", "Entspannung"]{', ' + family_field[:-1] if family_field else ''}}}
  ],
  "estimated_total_stops": 4,
  "route_could_be_complete": false
}}"""

    async def find_options(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int = 0,
        segment_count: int = 1,
        extra_instructions: str = "",
        route_geometry: dict = None,
        architect_context: dict = None,
    ) -> dict:
        """Call Claude to produce 3 stop options and enrich results with Wikipedia summaries and island coordinate validation."""
        prompt = self._build_prompt(
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=days_remaining,
            route_could_be_complete=route_could_be_complete,
            segment_target=segment_target,
            segment_index=segment_index,
            segment_count=segment_count,
            extra_instructions=extra_instructions,
            route_geometry=route_geometry,
            architect_context=architect_context,
        )

        lang = getattr(self.request, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")
        await debug_logger.log_prompt("StopOptionsFinder", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="StopOptionsFinder")
        text = response.content[0].text
        # Return Claude's result immediately — drive_hours/drive_km are placeholders.
        # Authoritative Google Directions enrichment runs in main.py after this call.
        result = parse_agent_json(text)

        # Wikipedia-Anreicherung: echte Beschreibungen und Einwohnerzahlen
        for option in result.get("options", []):
            region = option.get("region", "")
            if region:
                wiki = await get_city_summary(region)
                if wiki:
                    if wiki.get("extract"):
                        option.setdefault("description", wiki["extract"][:200])
                    if wiki.get("thumbnail_url"):
                        option["wikipedia_image"] = wiki["thumbnail_url"]

            # Island coordinate validation (D-10, GEO-02)
            opt_lat = option.get("lat")
            opt_lon = option.get("lon")
            if opt_lat is not None and opt_lon is not None:
                coords = (opt_lat, opt_lon)
                island_group = is_island_destination(coords)
                if island_group:
                    if not validate_island_coordinates(region, coords, island_group):
                        await debug_logger.log(
                            LogLevel.WARNING,
                            f"Insel-Koordinaten-Validierung fehlgeschlagen: {region} "
                            f"({coords[0]:.4f}, {coords[1]:.4f}) nicht in {island_group} bbox",
                            job_id=self.job_id, agent="StopOptionsFinder",
                        )
                        # Coordinates resolved to mainland instead of island -- flag for review
                        # but do not discard (graceful degradation)

        return result

    async def find_options_streaming(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int = 0,
        segment_count: int = 1,
        extra_instructions: str = "",
        route_geometry: dict = None,
        architect_context: dict = None,
    ) -> AsyncIterator[dict]:
        """
        Calls Claude with streaming and yields individual option dicts as soon
        as each complete JSON object becomes detectable in the stream.
        Also yields a final dict {"_all_options": [...], "estimated_total_stops": int,
        "route_could_be_complete": bool} once the full response is parsed.
        """
        prompt = self._build_prompt(
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=days_remaining,
            route_could_be_complete=route_could_be_complete,
            segment_target=segment_target,
            segment_index=segment_index,
            segment_count=segment_count,
            extra_instructions=extra_instructions,
            route_geometry=route_geometry,
            architect_context=architect_context,
        )

        lang = getattr(self.request, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])

        await debug_logger.log(LogLevel.API, f"→ Anthropic API stream: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")

        accumulated = ""
        emitted_count = 0

        def _extract_next_option(text: str, already_emitted: int):
            """Find the next complete option object in the accumulated JSON text."""
            # Locate the "options" array
            arr_match = re.search(r'"options"\s*:\s*\[', text)
            if not arr_match:
                return None, already_emitted
            arr_start = arr_match.end()
            # Find each complete {...} block after arr_start
            depth = 0
            obj_start = None
            count = 0
            i = arr_start
            while i < len(text):
                ch = text[i]
                if ch == '{':
                    if depth == 0:
                        obj_start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and obj_start is not None:
                        count += 1
                        if count > already_emitted:
                            try:
                                obj = json.loads(text[obj_start:i + 1])
                                return obj, count
                            except json.JSONDecodeError:
                                pass
                i += 1
            return None, already_emitted

        def _do_stream():
            nonlocal accumulated, emitted_count
            results = []
            with self.client.messages.stream(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text_chunk in stream.text_stream:
                    accumulated += text_chunk
                    opt, new_count = _extract_next_option(accumulated, emitted_count)
                    if opt is not None:
                        emitted_count = new_count
                        results.append(("option", opt))
                full_text = stream.get_final_text()
            return results, full_text

        import time as _time
        t0 = _time.monotonic()
        try:
            partial_results, final_text = await asyncio.to_thread(_do_stream)
        except Exception as exc:
            import traceback
            await debug_logger.log(
                LogLevel.ERROR,
                f"Stream-Fehler: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                job_id=self.job_id, agent="StopOptionsFinder",
            )
            raise
        elapsed = _time.monotonic() - t0

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"← Stream fertig in {elapsed:.1f}s — {len(partial_results)} Option(en) im Stream erkannt",
            job_id=self.job_id, agent="StopOptionsFinder",
        )

        for kind, payload in partial_results:
            if kind == "option":
                yield payload

        # Parse the complete response for metadata + any options not yet emitted
        try:
            full_parsed = parse_agent_json(final_text)
        except (ValueError, json.JSONDecodeError) as exc:
            await debug_logger.log(
                LogLevel.WARNING,
                f"JSON-Antwort abgeschnitten, verwende {emitted_count} im Stream erkannte Optionen. Fehler: {exc}",
                job_id=self.job_id, agent="StopOptionsFinder",
            )
            # Fall back to streamed options — already yielded above
            yield {
                "_all_options": [p for k, p in partial_results if k == "option"],
                "estimated_total_stops": 4,
                "route_could_be_complete": False,
            }
            return

        all_options = full_parsed.get("options", [])
        # Emit any options that weren't caught during streaming (edge cases)
        for opt in all_options[emitted_count:]:
            yield opt

        # Final sentinel with complete metadata
        yield {
            "_all_options": all_options,
            "estimated_total_stops": full_parsed.get("estimated_total_stops", 4),
            "route_could_be_complete": full_parsed.get("route_could_be_complete", False),
        }

