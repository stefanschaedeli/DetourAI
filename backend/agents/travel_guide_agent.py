"""Agent that generates narrative travel guide content and additional activity suggestions for each trip stop."""

from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.wikipedia import get_city_summary
from agents._client import get_client, get_model, get_max_tokens
import asyncio

AGENT_KEY = "travel_guide"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein erfahrener Reisejournalist. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are an experienced travel journalist. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक अनुभवी यात्रा पत्रकार हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}

# ---------------------------------------------------------------------------
# Localized string tables
# ---------------------------------------------------------------------------

_L = {
    "de": {
        "none": "keine",
        "wiki_header": "Wikipedia-Zusammenfassung über {region}:",
        "wiki_use": "Nutze diese Fakten als Grundlage für deinen Reiseführer.",
        "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
        "write_guide": "Schreibe einen Reiseführer für",
        "stay": "Aufenthalt", "nights": "Nächte",
        "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder",
        "styles": "Reisestile", "styles_default": "allgemein",
        "already_planned": "Bereits geplante Aktivitäten (NICHT wiederholen)",
        "return_json": "Gib exakt dieses JSON zurück:",
        "intro_desc": "Einladende Einleitung über {region} (2 Sätze)",
        "history_desc": "Geschichte und kulturelle Highlights (2 Sätze)",
        "food_desc": "Lokale Spezialitäten (2 Sätze)",
        "tips_desc": "Praktische Tipps für den Aufenthalt (2 Sätze)",
        "gems_desc": "Geheimtipps jenseits der Touristenpfade (2 Sätze)",
        "best_time_desc": "Beste Reisezeit (1-2 Sätze)",
        "write_lang": "Schreibe alle Texte auf Deutsch.",
        "further": "Gib 2-3 weitere Aktivitäten zurück, die sich von den bereits geplanten unterscheiden.",
        "radius_note": "WICHTIG: Alle weiteren Aktivitäten müssen innerhalb von {r} km vom Übernachtungsort in {region} liegen.",
        "activities_header": "Schlage weitere Aktivitäten vor für",
    },
    "en": {
        "none": "none",
        "wiki_header": "Wikipedia summary about {region}:",
        "wiki_use": "Use these facts as a basis for your travel guide.",
        "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
        "write_guide": "Write a travel guide for",
        "stay": "Stay", "nights": "nights",
        "travelers": "Travelers", "adults": "adults", "children": "children",
        "styles": "Travel styles", "styles_default": "general",
        "already_planned": "Already planned activities (do NOT repeat)",
        "return_json": "Return exactly this JSON:",
        "intro_desc": "Inviting introduction about {region} (2 sentences)",
        "history_desc": "History and cultural highlights (2 sentences)",
        "food_desc": "Local specialties (2 sentences)",
        "tips_desc": "Practical tips for the stay (2 sentences)",
        "gems_desc": "Hidden gems off the beaten path (2 sentences)",
        "best_time_desc": "Best time to visit (1-2 sentences)",
        "write_lang": "Write all texts in English.",
        "further": "Return 2-3 additional activities that differ from the already planned ones.",
        "radius_note": "IMPORTANT: All additional activities must be within {r} km of the accommodation in {region}.",
        "activities_header": "Suggest further activities for",
    },
    "hi": {
        "none": "कोई नहीं",
        "wiki_header": "{region} के बारे में विकिपीडिया सारांश:",
        "wiki_use": "अपने यात्रा गाइड के लिए इन तथ्यों को आधार के रूप में उपयोग करें।",
        "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
        "write_guide": "के लिए एक यात्रा गाइड लिखें",
        "stay": "ठहराव", "nights": "रातें",
        "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे",
        "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
        "already_planned": "पहले से नियोजित गतिविधियां (दोहराएं नहीं)",
        "return_json": "बिल्कुल यह JSON लौटाएं:",
        "intro_desc": "{region} के बारे में आमंत्रित परिचय (2 वाक्य)",
        "history_desc": "इतिहास और सांस्कृतिक हाइलाइट्स (2 वाक्य)",
        "food_desc": "स्थानीय विशेषताएं (2 वाक्य)",
        "tips_desc": "ठहरने के लिए व्यावहारिक सुझाव (2 वाक्य)",
        "gems_desc": "पर्यटन पथ से हटकर छिपे रत्न (2 वाक्य)",
        "best_time_desc": "यात्रा का सबसे अच्छा समय (1-2 वाक्य)",
        "write_lang": "सभी पाठ हिंदी में लिखें।",
        "further": "पहले से नियोजित गतिविधियों से भिन्न 2-3 अतिरिक्त गतिविधियां लौटाएं।",
        "radius_note": "महत्वपूर्ण: सभी अतिरिक्त गतिविधियां {region} में आवास से {r} km के भीतर होनी चाहिए।",
        "activities_header": "के लिए आगे की गतिविधियाँ सुझाएं",
    },
}


class TravelGuideAgent:
    """Agent that writes localized travel guide narratives and suggests further activities for a single stop.

    Runs two parallel Claude calls per stop (guide narratives + further activities) using Haiku
    for fast generation, then merges results.
    """

    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        # Haiku is used here: the task is prose generation, not complex reasoning,
        # and splitting into two parallel calls makes quality sufficient at much higher speed.
        self.model = get_model("claude-haiku-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict, existing_activity_names: list) -> dict:
        """Generate travel guide content and additional activities for one stop via two parallel Claude calls."""
        stop_id = stop.get("id", 1)

        # Fetch Wikipedia context once, shared by both calls
        region = stop.get("region", "")
        wiki = await get_city_summary(region)
        wiki_extract = wiki.get("extract", "")[:500] if wiki else ""

        guide_result, activities_result = await asyncio.gather(
            self._run_guide(stop, wiki_extract),
            self._run_further_activities(stop, existing_activity_names, wiki_extract),
        )

        return {
            "stop_id": stop_id,
            "travel_guide": guide_result.get("travel_guide"),
            "further_activities": activities_result.get("further_activities", []),
        }

    async def _run_guide(self, stop: dict, wiki_extract: str) -> dict:
        """Call Claude for the 6 narrative travel guide fields only."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        GL = _L.get(lang, _L["de"])

        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)
        children_str = f", {len(req.children)} {GL['children']}" if req.children else ""

        if lang == "hi":
            guide_line = f"{region}, {country} {GL['write_guide']}:"
        else:
            guide_line = f"{GL['write_guide']} {region}, {country}:"

        desc_line = f"\n{GL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{GL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{GL['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        wiki_block = ""
        if wiki_extract:
            wiki_block = f"\n\n{GL['wiki_header'].format(region=region)}\n{wiki_extract}\n{GL['wiki_use']}\n"

        prompt = f"""{guide_line}

{GL['stay']}: {nights} {GL['nights']}
{GL['travelers']}: {req.adults} {GL['adults']}{children_str}
{GL['styles']}: {', '.join(req.travel_styles) if req.travel_styles else GL['styles_default']}{mandatory_line}{pref_line}{desc_line}

{GL['return_json']}
{{
  "travel_guide": {{
    "intro_narrative": "{GL['intro_desc'].format(region=region)}",
    "history_culture": "{GL['history_desc']}",
    "food_specialties": "{GL['food_desc']}",
    "local_tips": "{GL['tips_desc']}",
    "insider_gems": "{GL['gems_desc']}",
    "best_time_to_visit": "{GL['best_time_desc']}"
  }}
}}

{GL['write_lang']}{wiki_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Reiseführer-Text: {region})",
            job_id=self.job_id, agent="TravelGuideAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TravelGuideAgent",
                                         token_accumulator=self.token_accumulator)
        return parse_agent_json(response.content[0].text)

    async def _run_further_activities(self, stop: dict, existing_activity_names: list, wiki_extract: str) -> dict:
        """Call Claude for 2-3 further activity suggestions only."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        GL = _L.get(lang, _L["de"])

        region = stop.get("region", "")
        country = stop.get("country", "")
        existing_names_str = ", ".join(existing_activity_names) if existing_activity_names else GL["none"]

        if lang == "hi":
            header_line = f"{region}, {country} {GL['activities_header']}:"
        else:
            header_line = f"{GL['activities_header']} {region}, {country}:"

        wiki_block = ""
        if wiki_extract:
            wiki_block = f"\n\n{GL['wiki_header'].format(region=region)}\n{wiki_extract}\n"

        prompt = f"""{header_line}

{GL['already_planned']}: {existing_names_str}

{GL['return_json']}
{{
  "further_activities": [
    {{
      "name": "...",
      "description": "...",
      "duration_hours": 2.0,
      "price_chf": 0.0,
      "suitable_for_children": true,
      "notes": "...",
      "address": "...",
      "google_maps_url": "https://maps.google.com/?q=..."
    }}
  ]
}}

{GL['write_lang']} {GL['further']} {GL['radius_note'].format(r=req.activities_radius_km * 2, region=region)}{wiki_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Weitere Aktivitäten: {region})",
            job_id=self.job_id, agent="TravelGuideAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TravelGuideAgent",
                                         token_accumulator=self.token_accumulator)
        return parse_agent_json(response.content[0].text)
