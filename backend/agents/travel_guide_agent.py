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
        "Du bist ein erfahrener Reisejournalist und Reiseführer-Autor mit tiefer Kenntnis europäischer "
        "und weltweiter Reiseziele. Du schreibst lebendige, detaillierte und praktisch nützliche Texte, "
        "die konkrete Namen von Sehenswürdigkeiten, Restaurants, Märkten und lokalen Highlights nennen. "
        "Deine Texte sind informativ, persönlich und inspirierend — kein generisches Tourismus-Blabla, "
        "sondern echte Insider-Empfehlungen. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are an experienced travel journalist and guidebook author with deep knowledge of European "
        "and worldwide travel destinations. You write vivid, detailed, and practically useful texts "
        "that name specific attractions, restaurants, markets, and local highlights. "
        "Your texts are informative, personal, and inspiring — not generic tourism filler, "
        "but genuine insider recommendations. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक अनुभवी यात्रा पत्रकार और गाइडबुक लेखक हैं जिन्हें यूरोपीय और विश्वव्यापी "
        "यात्रा गंतव्यों का गहरा ज्ञान है। आप जीवंत, विस्तृत और व्यावहारिक रूप से उपयोगी पाठ लिखते हैं "
        "जो विशिष्ट आकर्षणों, रेस्तरां, बाजारों और स्थानीय हाइलाइट्स के नाम बताते हैं। "
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
        "wiki_use": "Nutze diese Fakten als Grundlage für deinen Reiseführer. Nenne konkrete Orte, Sehenswürdigkeiten und historische Fakten.",
        "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
        "write_guide": "Schreibe einen ausführlichen Reiseführer für",
        "stay": "Aufenthalt", "nights": "Nächte",
        "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder",
        "styles": "Reisestile", "styles_default": "allgemein",
        "already_planned": "Bereits geplante Aktivitäten (NICHT wiederholen)",
        "quality_instruction": (
            "Schreibe ausführliche, informative Texte mit konkreten Namen, Empfehlungen und praktischen Details. "
            "Jeder Abschnitt soll 2-3 vollständige Absätze umfassen."
        ),
        "intro_desc": "Einladende, lebendige Einleitung über {region} (2-3 Absätze): Was macht diesen Ort besonders? Welche erste Eindrücke erwarten den Besucher? Nenne das charakteristische Flair, die Atmosphäre und 2-3 konkrete Highlights.",
        "history_desc": "Geschichte und kulturelle Highlights (2-3 Absätze): Wichtige historische Ereignisse und Epochen, bedeutende Bauwerke und Monumente mit Namen, kulturelle Besonderheiten und lokale Traditionen, interessante historische Fakten.",
        "food_desc": "Lokale Spezialitäten und Kulinarik (2-3 Absätze): Typische Gerichte und ihre Geschichte, empfehlenswerte Restaurants oder Märkte mit Namen, lokale Getränke und Spezialitäten, kulinarische Erlebnisse die man nicht verpassen sollte.",
        "tips_desc": "Praktische Tipps für den Aufenthalt (2-3 Absätze): Beste Fortbewegungsmittel, Öffnungszeiten und Besuchszeiten, lokale Gepflogenheiten und Etikette, hilfreiche Apps oder Ressourcen, Sicherheitshinweise falls relevant.",
        "gems_desc": "Geheimtipps jenseits der Touristenpfade (2-3 Absätze): Wenig bekannte Orte die Einheimische kennen, versteckte Aussichtspunkte oder ruhige Ecken, besondere lokale Erlebnisse abseits der Massen, authentische Begegnungen mit der lokalen Kultur.",
        "best_time_desc": "Beste Reisezeit und saisonale Tipps (1-2 Absätze): Ideale Monate für einen Besuch, Wetter und Klima, saisonale Events oder Besonderheiten, Vor- und Nachteile verschiedener Jahreszeiten.",
        "getting_around_desc": "Mobilität und Fortbewegung (1-2 Absätze): Lokaler öffentlicher Verkehr, Parkplatzsituation, Fahrradverleih, Fussgängerzonen, Taxi/Uber-Verfügbarkeit, Entfernungen zu wichtigen Sehenswürdigkeiten.",
        "nature_desc": "Natur und Landschaft (2-3 Absätze): Geografische Besonderheiten, schöne Aussichtspunkte mit Namen, Naturparks und Wanderwege, Seen, Flüsse, Berge oder Küste, besondere Flora und Fauna.",
        "family_desc": "Tipps für Familien mit Kindern (2 Absätze): Kinderfreundliche Sehenswürdigkeiten, Spielplätze und Parks, familienfreundliche Restaurants, praktische Tipps für Reisen mit Kindern in dieser Region.",
        "shopping_desc": "Shopping und Märkte (1-2 Absätze): Wochenmärkte und ihre Öffnungszeiten, typische Souvenirs und lokale Produkte, bekannte Einkaufsstrassen, besondere Geschäfte oder Manufakturen.",
        "write_lang": "Schreibe alle Texte auf Deutsch.",
        "further": "Gib 4-5 weitere Aktivitäten zurück, die sich von den bereits geplanten unterscheiden. Jede Aktivität soll eine aussagekräftige Beschreibung von 2-3 Sätzen haben, die erklärt was die Aktivität besonders macht und was man erwartet.",
        "activities_header": "Schlage weitere Aktivitäten vor für",
        "with_children": "Reisegruppe umfasst Kinder",
    },
    "en": {
        "none": "none",
        "wiki_header": "Wikipedia summary about {region}:",
        "wiki_use": "Use these facts as a basis for your travel guide. Name specific places, attractions, and historical facts.",
        "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
        "write_guide": "Write a detailed travel guide for",
        "stay": "Stay", "nights": "nights",
        "travelers": "Travelers", "adults": "adults", "children": "children",
        "styles": "Travel styles", "styles_default": "general",
        "already_planned": "Already planned activities (do NOT repeat)",
        "quality_instruction": (
            "Write detailed, informative texts with specific names, recommendations, and practical details. "
            "Each section should comprise 2-3 full paragraphs."
        ),
        "intro_desc": "Inviting, vivid introduction about {region} (2-3 paragraphs): What makes this place special? What first impressions await visitors? Name the characteristic flair, atmosphere, and 2-3 concrete highlights.",
        "history_desc": "History and cultural highlights (2-3 paragraphs): Key historical events and eras, significant buildings and monuments by name, cultural peculiarities and local traditions, interesting historical facts.",
        "food_desc": "Local specialties and cuisine (2-3 paragraphs): Typical dishes and their history, recommended restaurants or markets by name, local drinks and specialties, culinary experiences not to miss.",
        "tips_desc": "Practical tips for the stay (2-3 paragraphs): Best modes of transport, opening hours and visit times, local customs and etiquette, helpful apps or resources, safety notes if relevant.",
        "gems_desc": "Hidden gems off the beaten path (2-3 paragraphs): Lesser-known spots locals know, hidden viewpoints or quiet corners, special local experiences away from the crowds, authentic encounters with local culture.",
        "best_time_desc": "Best time to visit and seasonal tips (1-2 paragraphs): Ideal months for a visit, weather and climate, seasonal events or highlights, pros and cons of different seasons.",
        "getting_around_desc": "Getting around (1-2 paragraphs): Local public transport, parking situation, bike rentals, pedestrian zones, taxi/ride-share availability, distances to key sights.",
        "nature_desc": "Nature and landscape (2-3 paragraphs): Geographical highlights, beautiful viewpoints by name, nature parks and hiking trails, lakes, rivers, mountains or coast, notable flora and fauna.",
        "family_desc": "Tips for families with children (2 paragraphs): Child-friendly attractions, playgrounds and parks, family-friendly restaurants, practical tips for travelling with children in this region.",
        "shopping_desc": "Shopping and markets (1-2 paragraphs): Weekly markets and opening times, typical souvenirs and local products, well-known shopping streets, special shops or workshops.",
        "write_lang": "Write all texts in English.",
        "further": "Return 4-5 additional activities that differ from the already planned ones. Each activity should have a meaningful description of 2-3 sentences explaining what makes it special and what to expect.",
        "activities_header": "Suggest further activities for",
        "with_children": "Travel group includes children",
    },
    "hi": {
        "none": "कोई नहीं",
        "wiki_header": "{region} के बारे में विकिपीडिया सारांश:",
        "wiki_use": "अपने यात्रा गाइड के लिए इन तथ्यों को आधार के रूप में उपयोग करें। विशिष्ट स्थानों, आकर्षणों और ऐतिहासिक तथ्यों का नाम लें।",
        "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
        "write_guide": "के लिए एक विस्तृत यात्रा गाइड लिखें",
        "stay": "ठहराव", "nights": "रातें",
        "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे",
        "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
        "already_planned": "पहले से नियोजित गतिविधियां (दोहराएं नहीं)",
        "quality_instruction": (
            "विशिष्ट नामों, सिफारिशों और व्यावहारिक विवरणों के साथ विस्तृत, जानकारीपूर्ण पाठ लिखें। "
            "प्रत्येक अनुभाग में 2-3 पूर्ण अनुच्छेद होने चाहिए।"
        ),
        "intro_desc": "{region} के बारे में आमंत्रित, जीवंत परिचय (2-3 अनुच्छेद): इस स्थान को क्या खास बनाता है? आगंतुकों का पहला प्रभाव क्या होगा? विशेषता, माहौल और 2-3 ठोस हाइलाइट्स का नाम लें।",
        "history_desc": "इतिहास और सांस्कृतिक हाइलाइट्स (2-3 अनुच्छेद): प्रमुख ऐतिहासिक घटनाएं और युग, नाम सहित महत्वपूर्ण इमारतें और स्मारक, सांस्कृतिक विशेषताएं और स्थानीय परंपराएं।",
        "food_desc": "स्थानीय विशेषताएं और व्यंजन (2-3 अनुच्छेद): विशिष्ट व्यंजन और उनका इतिहास, नाम सहित अनुशंसित रेस्तरां या बाजार, स्थानीय पेय और विशेषताएं।",
        "tips_desc": "ठहरने के लिए व्यावहारिक सुझाव (2-3 अनुच्छेद): सर्वोत्तम परिवहन साधन, खुलने का समय, स्थानीय रीति-रिवाज और शिष्टाचार, उपयोगी ऐप्स या संसाधन।",
        "gems_desc": "पर्यटन पथ से हटकर छिपे रत्न (2-3 अनुच्छेद): कम ज्ञात स्थान जो स्थानीय लोग जानते हैं, छिपे व्यूपॉइंट या शांत कोने, भीड़ से दूर विशेष स्थानीय अनुभव।",
        "best_time_desc": "यात्रा का सबसे अच्छा समय और मौसमी सुझाव (1-2 अनुच्छेद): यात्रा के लिए आदर्श महीने, मौसम और जलवायु, मौसमी आयोजन।",
        "getting_around_desc": "आवागमन (1-2 अनुच्छेद): स्थानीय सार्वजनिक परिवहन, पार्किंग, साइकिल किराया, पैदल चलने के क्षेत्र, टैक्सी की उपलब्धता।",
        "nature_desc": "प्रकृति और परिदृश्य (2-3 अनुच्छेद): भौगोलिक विशेषताएं, नाम सहित सुंदर व्यूपॉइंट, प्रकृति पार्क और पैदल मार्ग, झीलें, नदियां, पहाड़ या तट।",
        "family_desc": "बच्चों वाले परिवारों के लिए सुझाव (2 अनुच्छेद): बच्चों के अनुकूल आकर्षण, खेल के मैदान और पार्क, पारिवारिक रेस्तरां, बच्चों के साथ यात्रा के लिए व्यावहारिक सुझाव।",
        "shopping_desc": "खरीदारी और बाजार (1-2 अनुच्छेद): साप्ताहिक बाजार और खुलने का समय, विशिष्ट स्मृति चिह्न और स्थानीय उत्पाद, प्रसिद्ध खरीदारी सड़कें।",
        "write_lang": "सभी पाठ हिंदी में लिखें।",
        "further": "पहले से नियोजित गतिविधियों से भिन्न 4-5 अतिरिक्त गतिविधियां लौटाएं। प्रत्येक गतिविधि में 2-3 वाक्यों का अर्थपूर्ण विवरण होना चाहिए।",
        "activities_header": "के लिए आगे की गतिविधियाँ सुझाएं",
        "with_children": "यात्रा समूह में बच्चे शामिल हैं",
    },
}


class TravelGuideAgent:
    """Agent that writes localized travel guide narratives and suggests further activities for a single stop.

    Runs two parallel Claude calls per stop (guide narratives + further activities) using Sonnet
    for high-quality prose, then merges results.
    """

    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict, existing_activity_names: list) -> dict:
        """Generate travel guide content and additional activities for one stop via two parallel Claude calls."""
        stop_id = stop.get("id", 1)

        # Fetch Wikipedia context once, shared by both calls — use 2000 chars for richer grounding
        region = stop.get("region", "")
        wiki = await get_city_summary(region)
        wiki_extract = wiki.get("extract", "")[:2000] if wiki else ""

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
        """Call Claude for the narrative travel guide fields."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        GL = _L.get(lang, _L["de"])

        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)
        has_children = bool(req.children)
        children_str = f", {len(req.children)} {GL['children']}" if req.children else ""

        if lang == "hi":
            guide_line = f"{region}, {country} {GL['write_guide']}:"
        else:
            guide_line = f"{GL['write_guide']} {region}, {country}:"

        desc_line = f"\n{GL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{GL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{GL['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""
        children_note = f"\n{GL['with_children']}: {len(req.children)}" if has_children else ""

        wiki_block = ""
        if wiki_extract:
            wiki_block = f"\n\n{GL['wiki_header'].format(region=region)}\n{wiki_extract}\n{GL['wiki_use']}\n"

        # Build family_highlights field only when children are present
        family_field = ""
        if has_children:
            family_field = f',\n    "family_highlights": "{GL["family_desc"]}"'

        prompt = f"""{guide_line}

{GL['stay']}: {nights} {GL['nights']}
{GL['travelers']}: {req.adults} {GL['adults']}{children_str}
{GL['styles']}: {', '.join(req.travel_styles) if req.travel_styles else GL['styles_default']}{mandatory_line}{pref_line}{desc_line}{children_note}

{GL['quality_instruction']}

{{
  "travel_guide": {{
    "intro_narrative": "{GL['intro_desc'].format(region=region)}",
    "history_culture": "{GL['history_desc']}",
    "food_specialties": "{GL['food_desc']}",
    "local_tips": "{GL['tips_desc']}",
    "insider_gems": "{GL['gems_desc']}",
    "best_time_to_visit": "{GL['best_time_desc']}",
    "getting_around": "{GL['getting_around_desc']}",
    "nature_landscape": "{GL['nature_desc']}"{family_field},
    "shopping_markets": "{GL['shopping_desc']}"
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
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TravelGuideAgent",
                                         token_accumulator=self.token_accumulator)
        return parse_agent_json(response.content[0].text)

    async def _run_further_activities(self, stop: dict, existing_activity_names: list, wiki_extract: str) -> dict:
        """Call Claude for 4-5 further activity suggestions with rich descriptions."""
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

{GL['write_lang']} {GL['further']}{wiki_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Weitere Aktivitäten: {region})",
            job_id=self.job_id, agent="TravelGuideAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="TravelGuideAgent",
                                         token_accumulator=self.token_accumulator)
        return parse_agent_json(response.content[0].text)
