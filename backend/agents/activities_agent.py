"""Agent that researches and recommends activities for each trip stop, enriched with Google Places data and weather forecasts."""

import asyncio
import difflib
from collections import defaultdict
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_attractions, place_photo_url, find_place_from_text
from utils.weather import get_forecast
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "activities"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein erfahrener Aktivitätsberater für Reisende mit Expertise in "
        "altersgerechten Erlebnissen, lokalen Geheimtipps und saisonalen Empfehlungen. "
        "Du achtest darauf, eine ausgewogene Mischung aus Aktivitäten zu empfehlen: "
        "aktiv & interaktiv, kulturell, Naturerlebnis und kulinarisch. "
        "Bei Familien mit Kindern priorisierst du Erlebnisse, bei denen alle Altersgruppen "
        "Spass haben, und schlägst auch spezifische Kinderaktivitäten vor. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are an experienced activity advisor for travelers with expertise in "
        "age-appropriate experiences, local hidden gems, and seasonal recommendations. "
        "You make sure to recommend a balanced mix of activities: "
        "active & interactive, cultural, nature experiences, and culinary. "
        "For families with children, you prioritize experiences where all age groups "
        "can have fun, and also suggest specific children's activities. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप यात्रियों के लिए एक अनुभवी गतिविधि सलाहकार हैं जिन्हें "
        "आयु-उपयुक्त अनुभवों, स्थानीय छिपे रत्नों और मौसमी सिफारिशों में विशेषज्ञता है। "
        "आप गतिविधियों का संतुलित मिश्रण सुझाते हैं: "
        "सक्रिय और इंटरैक्टिव, सांस्कृतिक, प्रकृति अनुभव और पाक-कला। "
        "बच्चों वाले परिवारों के लिए, आप ऐसे अनुभवों को प्राथमिकता देते हैं जहां सभी आयु वर्ग "
        "आनंद ले सकें, और विशिष्ट बच्चों की गतिविधियां भी सुझाते हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}

# Altersgruppen-Mapping für Kinder
_AGE_GROUPS = {
    "de": [
        (0, 2, "Babys/Kleinkinder"),
        (3, 5, "Kindergarten"),
        (6, 11, "Schulkinder"),
        (12, 17, "Teenager"),
    ],
    "en": [
        (0, 2, "Babies/Toddlers"),
        (3, 5, "Preschool"),
        (6, 11, "School children"),
        (12, 17, "Teenagers"),
    ],
    "hi": [
        (0, 2, "शिशु/बच्चे"),
        (3, 5, "पूर्वस्कूली"),
        (6, 11, "स्कूली बच्चे"),
        (12, 17, "किशोर"),
    ],
}

# Aktivitätshinweise pro Altersgruppe
_AGE_ACTIVITY_HINTS = {
    "de": {
        "Babys/Kleinkinder": (
            "Für Kleinkinder (0-2): Kurze Aktivitäten (max 1h), Spielplätze, "
            "Streichelzoos, ruhige Parks, babytaugliche Orte mit Wickelmöglichkeiten."
        ),
        "Kindergarten": (
            "Für Kindergartenkinder (3-5): Streichelzoos, Naturspielplätze, Wasserspielplätze, "
            "Kindermuseen mit Anfassstationen, einfache Naturpfade, Bauernhöfe zum Anfassen, "
            "Tierparks, Miniaturwelten. Interaktive und spielerische Erlebnisse bevorzugen."
        ),
        "Schulkinder": (
            "Für Schulkinder (6-11): Abenteuerparks, leichte Wanderungen, Tierparks, "
            "interaktive Museen, Kletterparks (ab 8J), Velofahren, Schatzsuchen, "
            "Naturerlebnispfade, Höhlenbesichtigungen."
        ),
        "Teenager": (
            "Für Teenager (12-17): Kletterparks, Kajak/Kanu, Escape Rooms, "
            "Zip-Lines, Stadttouren, Wassersport, E-Bike-Touren, "
            "Geocaching, kulturelle Highlights mit Erlebnischarakter."
        ),
    },
    "en": {
        "Babies/Toddlers": (
            "For toddlers (0-2): Short activities (max 1h), playgrounds, "
            "petting zoos, quiet parks, baby-friendly places with changing facilities."
        ),
        "Preschool": (
            "For preschoolers (3-5): Petting zoos, nature playgrounds, water playgrounds, "
            "children's museums with hands-on stations, easy nature trails, farms to visit, "
            "animal parks, miniature worlds. Prefer interactive and playful experiences."
        ),
        "School children": (
            "For school children (6-11): Adventure parks, easy hikes, animal parks, "
            "interactive museums, climbing parks (8+), cycling, treasure hunts, "
            "nature experience trails, cave tours."
        ),
        "Teenagers": (
            "For teenagers (12-17): Climbing parks, kayak/canoe, escape rooms, "
            "zip-lines, city tours, water sports, e-bike tours, "
            "geocaching, cultural highlights with experiential character."
        ),
    },
    "hi": {
        "शिशु/बच्चे": (
            "छोटे बच्चों (0-2) के लिए: छोटी गतिविधियां (अधिकतम 1 घंटा), खेल के मैदान, "
            "पालतू चिड़ियाघर, शांत पार्क, बच्चों के अनुकूल स्थान।"
        ),
        "पूर्वस्कूली": (
            "पूर्वस्कूली बच्चों (3-5) के लिए: पालतू चिड़ियाघर, प्रकृति खेल के मैदान, "
            "बच्चों के संग्रहालय, सरल प्रकृति पगडंडियां, फार्म भ्रमण। "
            "इंटरैक्टिव और खेल अनुभवों को प्राथमिकता दें।"
        ),
        "स्कूली बच्चे": (
            "स्कूली बच्चों (6-11) के लिए: साहसिक पार्क, आसान पैदल यात्रा, "
            "इंटरैक्टिव संग्रहालय, क्लाइंबिंग पार्क (8+), साइकिल चलाना, "
            "खजाने की खोज, प्रकृति पगडंडियां।"
        ),
        "किशोर": (
            "किशोरों (12-17) के लिए: क्लाइंबिंग पार्क, कायाक/कैनो, एस्केप रूम, "
            "ज़िप-लाइन, शहर के दौरे, वाटर स्पोर्ट्स, ई-बाइक टूर, "
            "जियोकैशिंग, अनुभवात्मक सांस्कृतिक हाइलाइट्स।"
        ),
    },
}

# Aktivitätshinweise pro Reisestil
_STYLE_HINTS = {
    "de": {
        "adventure": "Abenteuer: Aktive, physische Erlebnisse wie Klettern, Rafting, Paragliding, Canyoning.",
        "nature": "Natur: Wanderwege, Naturreservate, Tierbeobachtung, Nationalparks, Seen, Wasserfälle.",
        "culture": "Kultur: Museen, historische Stätten, lokale Traditionen, Architektur, Führungen.",
        "culinary": "Kulinarisch: Food-Touren, lokale Märkte, Kochkurse, Weingüter, Käsereien.",
        "wellness": "Wellness: Thermen, Spas, Yoga, Meditationsorte, heisse Quellen.",
        "sport": "Sport: Velofahren, Klettern, Wassersport, Skifahren, Laufen, Golf.",
        "city": "Stadt: Stadttouren, Shopping, Street Art, Nachtleben, lokale Szene.",
        "romantic": "Romantik: Aussichtspunkte, Bootsfahrten, Picknick-Spots, besondere Restaurants.",
        "slow_travel": "Slow Travel: Gemütliche Spaziergänge, lokale Cafés, Handwerksmärkte, Dorfleben.",
        "road_trip": "Road Trip: Aussichtspunkte, Fotostopps, lokale Raststätten, Panoramastrassen.",
        "relaxation": "Entspannung: Ruhige Parks, Strände, Picknick-Plätze, gemütliche Cafés.",
    },
    "en": {
        "adventure": "Adventure: Active, physical experiences like climbing, rafting, paragliding, canyoning.",
        "nature": "Nature: Hiking trails, nature reserves, wildlife watching, national parks, lakes, waterfalls.",
        "culture": "Culture: Museums, historical sites, local traditions, architecture, guided tours.",
        "culinary": "Culinary: Food tours, local markets, cooking classes, wineries, cheese dairies.",
        "wellness": "Wellness: Thermal baths, spas, yoga, meditation spots, hot springs.",
        "sport": "Sport: Cycling, climbing, water sports, skiing, running, golf.",
        "city": "City: City tours, shopping, street art, nightlife, local scene.",
        "romantic": "Romance: Viewpoints, boat rides, picnic spots, special restaurants.",
        "slow_travel": "Slow Travel: Leisurely walks, local cafes, craft markets, village life.",
        "road_trip": "Road Trip: Viewpoints, photo stops, local rest stops, panoramic roads.",
        "relaxation": "Relaxation: Quiet parks, beaches, picnic spots, cozy cafes.",
    },
    "hi": {
        "adventure": "रोमांच: चढ़ाई, राफ्टिंग, पैराग्लाइडिंग, कैन्योनिंग जैसे सक्रिय अनुभव।",
        "nature": "प्रकृति: पैदल यात्रा पगडंडियां, प्रकृति अभयारण्य, वन्यजीव अवलोकन, राष्ट्रीय उद्यान, झीलें, झरने।",
        "culture": "संस्कृति: संग्रहालय, ऐतिहासिक स्थल, स्थानीय परंपराएं, वास्तुकला, गाइडेड टूर।",
        "culinary": "पाक-कला: फूड टूर, स्थानीय बाजार, कुकिंग क्लास, वाइनरी, पनीर डेयरी।",
        "wellness": "कल्याण: थर्मल बाथ, स्पा, योग, ध्यान स्थल, गर्म पानी के झरने।",
        "sport": "खेल: साइकिल चलाना, चढ़ाई, वाटर स्पोर्ट्स, स्कीइंग, दौड़, गोल्फ।",
        "city": "शहर: शहर के दौरे, खरीदारी, स्ट्रीट आर्ट, नाइटलाइफ, स्थानीय दृश्य।",
        "romantic": "रोमांस: व्यूपॉइंट, नाव की सवारी, पिकनिक स्थल, विशेष रेस्तरां।",
        "slow_travel": "धीमी यात्रा: आराम से सैर, स्थानीय कैफे, शिल्प बाजार, ग्रामीण जीवन।",
        "road_trip": "रोड ट्रिप: व्यूपॉइंट, फोटो स्टॉप, स्थानीय विश्राम स्थल, पैनोरमिक सड़कें।",
        "relaxation": "विश्राम: शांत पार्क, समुद्र तट, पिकनिक स्थल, आरामदायक कैफे।",
    },
}


_LABELS = {
    "de": {"adults": "Erwachsene", "children": "Kinder", "child": "Kind", "years": "Jahre"},
    "en": {"adults": "adults", "children": "children", "child": "child", "years": "years"},
    "hi": {"adults": "वयस्क", "children": "बच्चे", "child": "बच्चा", "years": "वर्ष"},
}


def _describe_travelers(req: TravelRequest, lang: str = None) -> str:
    """Return a localized string describing the travel group, including children's age groups."""
    if lang is None:
        lang = getattr(req, 'language', 'de')
    lbl = _LABELS.get(lang, _LABELS["de"])
    age_groups = _AGE_GROUPS.get(lang, _AGE_GROUPS["de"])

    parts = [f"{req.adults} {lbl['adults']}"]
    if not req.children:
        return parts[0]

    groups: dict[str, list[int]] = defaultdict(list)
    for child in req.children:
        for lo, hi, label in age_groups:
            if lo <= child.age <= hi:
                groups[label].append(child.age)
                break

    child_parts = []
    for _, _, label in age_groups:
        if label in groups:
            ages = sorted(groups[label])
            ages_str = ", ".join(str(a) for a in ages)
            child_parts.append(f"{label}: {ages_str} {lbl['years']}")

    total = len(req.children)
    child_word = lbl['children'] if total > 1 else lbl['child']
    parts.append(f"{total} {child_word} ({', '.join(child_parts)})")
    return ", ".join(parts)


_KIDS_HINT = {
    "de": "WICHTIG: Mindestens die Hälfte der Aktivitäten sollte speziell für Kinder geeignet sein. Bevorzuge interaktive, spielerische Erlebnisse.",
    "en": "IMPORTANT: At least half of the activities should be specifically suitable for children. Prefer interactive, playful experiences.",
    "hi": "महत्वपूर्ण: कम से कम आधी गतिविधियां विशेष रूप से बच्चों के लिए उपयुक्त होनी चाहिए। इंटरैक्टिव, खेल अनुभवों को प्राथमिकता दें।",
}
_STYLE_GUIDANCE_HEADER = {
    "de": "\n\nSpezifische Hinweise für diese Reisegruppe:\n",
    "en": "\n\nSpecific tips for this travel group:\n",
    "hi": "\n\nइस यात्रा समूह के लिए विशिष्ट सुझाव:\n",
}


def _build_style_guidance(req: TravelRequest, lang: str = None) -> str:
    """Build context-aware activity guidance text based on travel styles and children's age groups."""
    if lang is None:
        lang = getattr(req, 'language', 'de')
    age_groups = _AGE_GROUPS.get(lang, _AGE_GROUPS["de"])
    age_hints = _AGE_ACTIVITY_HINTS.get(lang, _AGE_ACTIVITY_HINTS["de"])
    style_hints = _STYLE_HINTS.get(lang, _STYLE_HINTS["de"])
    blocks = []

    # Altersgruppen-spezifische Hinweise wenn Kinder dabei
    if req.children:
        seen_groups: set[str] = set()
        for child in req.children:
            for lo, hi, label in age_groups:
                if lo <= child.age <= hi and label not in seen_groups:
                    seen_groups.add(label)
                    if label in age_hints:
                        blocks.append(age_hints[label])
                    break

    # Reisestil-Hinweise
    for style in req.travel_styles:
        if style in style_hints:
            blocks.append(style_hints[style])

    # Familienaktiv-Stil: Extra-Hinweis
    if "kids" in req.travel_styles and req.children:
        blocks.append(_KIDS_HINT.get(lang, _KIDS_HINT["de"]))

    if not blocks:
        return ""

    header = _STYLE_GUIDANCE_HEADER.get(lang, _STYLE_GUIDANCE_HEADER["de"])
    return header + "\n".join(f"- {b}" for b in blocks)


class ActivitiesAgent:
    """Agent that generates activity recommendations for a single trip stop, enriched with Google Places, weather, and image data."""

    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict) -> dict:
        """Research and return activity recommendations for one stop, merging Claude output with real Places data and images."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)

        budget_per_stop = req.budget_chf * (req.budget_activities_pct / 100) / max(1, req.total_days) * nights

        _L = {
            "de": {
                "reviews": "Bewertungen", "real_attractions": "Echte Sehenswürdigkeiten in der Nähe (Google Places Daten):",
                "prefer_real": "Bevorzuge diese echten Orte und ergänze mit deinem Wissen.",
                "precipitation": "Niederschlag", "weather_title": "Wettervorhersage für den Aufenthalt:",
                "weather_adapt": "Passe Empfehlungen ans Wetter an (bei Regen: Indoor-Aktivitäten bevorzugen).",
                "search_query": "Sehenswürdigkeiten", "real_search": "Echte Suchergebnisse für Aktivitäten:",
                "prefer_real2": "Bevorzuge diese echten Orte.",
                "travelers": "Reisende", "stay": "Aufenthalt", "nights": "Nächte",
                "styles": "Reisestile", "styles_default": "allgemein",
                "search_radius": "Suchradius", "max_act": "Max. Aktivitäten",
                "act_budget": "Aktivitätenbudget", "for_stop": "für diesen Stopp — nutze das Budget möglichst aus",
                "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
                "find_best": "Finde die besten Aktivitäten in",
                "age_group_ex": "ab 4 Jahre",
                "tags_hint": "tags: 2-3 kurze Schlagworte basierend auf den gefundenen Aktivitaeten (z.B. \"Wandern\", \"Kultur\", \"Wassersport\", \"Natur\", \"Geschichte\")",
            },
            "en": {
                "reviews": "reviews", "real_attractions": "Real attractions nearby (Google Places data):",
                "prefer_real": "Prefer these real places and supplement with your knowledge.",
                "precipitation": "Precipitation", "weather_title": "Weather forecast for the stay:",
                "weather_adapt": "Adapt recommendations to the weather (in case of rain: prefer indoor activities).",
                "search_query": "attractions", "real_search": "Real search results for activities:",
                "prefer_real2": "Prefer these real places.",
                "travelers": "Travelers", "stay": "Stay", "nights": "nights",
                "styles": "Travel styles", "styles_default": "general",
                "search_radius": "Search radius", "max_act": "Max. activities",
                "act_budget": "Activities budget", "for_stop": "for this stop — use the budget as much as possible",
                "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
                "find_best": "Find the best activities in",
                "age_group_ex": "from age 4",
                "tags_hint": "tags: 2-3 short keywords based on the found activities (e.g. \"Hiking\", \"Culture\", \"Water Sports\", \"Nature\", \"History\")",
            },
            "hi": {
                "reviews": "समीक्षाएं", "real_attractions": "पास के वास्तविक आकर्षण (Google Places डेटा):",
                "prefer_real": "इन वास्तविक स्थानों को प्राथमिकता दें और अपने ज्ञान से पूरक करें।",
                "precipitation": "वर्षा", "weather_title": "ठहरने के लिए मौसम पूर्वानुमान:",
                "weather_adapt": "मौसम के अनुसार सिफारिशें अनुकूलित करें (बारिश में: इनडोर गतिविधियों को प्राथमिकता दें)।",
                "search_query": "आकर्षण", "real_search": "गतिविधियों के लिए वास्तविक खोज परिणाम:",
                "prefer_real2": "इन वास्तविक स्थानों को प्राथमिकता दें।",
                "travelers": "यात्रीगण", "stay": "ठहराव", "nights": "रातें",
                "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
                "search_radius": "खोज दायरा", "max_act": "अधिकतम गतिविधियां",
                "act_budget": "गतिविधि बजट", "for_stop": "इस स्टॉप के लिए — बजट का अधिकतम उपयोग करें",
                "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
                "find_best": "में सर्वश्रेष्ठ गतिविधियां खोजें",
                "age_group_ex": "4 वर्ष से",
                "tags_hint": "tags: गतिविधियों के आधार पर 2-3 छोटे कीवर्ड",
            },
        }
        AL = _L.get(lang, _L["de"])

        # Pre-fetch: echte Sehenswürdigkeiten und Wetter
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""
        weather_block = ""

        if lat and lon:
            gp_results = await search_attractions(lat, lon, radius_m=req.activities_radius_km * 1000)
            if gp_results:
                lines = [f"- {a['name']} | \u2605{a.get('rating','?')} ({a.get('user_ratings_total',0)} {AL['reviews']}) | {a.get('address','')}" for a in gp_results[:8]]
                real_data_block = f"\n\n{AL['real_attractions']}\n" + "\n".join(lines) + f"\n{AL['prefer_real']}\n"

            # Wetter für wetterangepasste Empfehlungen
            arrival_day = stop.get("arrival_day", 1)
            start_date = req.start_date
            if hasattr(start_date, "isoformat"):
                from datetime import timedelta
                arr_date = start_date + timedelta(days=arrival_day - 1)
                dep_date = arr_date + timedelta(days=nights)
                weather = await get_forecast(lat, lon, arr_date.isoformat(), dep_date.isoformat())
                if weather:
                    lines = [f"- {w['date']}: {w['description']}, {w['temp_max']}\u00b0C/{w['temp_min']}\u00b0C, {AL['precipitation']}: {w['precipitation_mm']}mm" for w in weather]
                    weather_block = f"\n\n{AL['weather_title']}\n" + "\n".join(lines) + f"\n{AL['weather_adapt']}\n"

        if not real_data_block:
            brave_results = await search_places(f"{AL['search_query']} {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}\u2605) \u2014 {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = f"\n\n{AL['real_search']}\n" + "\n".join(lines) + f"\n{AL['prefer_real2']}\n"

        travelers_desc = _describe_travelers(req, lang)
        style_guidance = _build_style_guidance(req, lang)
        has_children = bool(req.children)

        # Optionale Kontextblöcke
        desc_line = f"\n{AL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{AL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{AL['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        # JSON-Schema mit optionalen Kinderfeldern
        children_fields = ""
        if has_children:
            children_fields = f"""
      "min_age": 4,
      "age_group": "{AL['age_group_ex']}","""

        styles_display = ', '.join(req.travel_styles) if req.travel_styles else AL['styles_default']
        if lang == "hi":
            find_line = f"{region}, {country} {AL['find_best']}:"
        else:
            find_line = f"{AL['find_best']} {region}, {country}:"

        prompt = f"""{find_line}

{AL['travelers']}: {travelers_desc}
{AL['stay']}: {nights} {AL['nights']}
{AL['styles']}: {styles_display}
{AL['search_radius']}: {req.activities_radius_km} km
{AL['max_act']}: {req.max_activities_per_stop}
{AL['act_budget']}: ca. CHF {budget_per_stop:.0f} {AL['for_stop']}{mandatory_line}{pref_line}{desc_line}{style_guidance}

{{
  "stop_id": {stop_id},
  "region": "{region}",
  "tags": ["Hiking", "Nature"],
  "top_activities": [
    {{
      "name": "...",
      "description": "...",
      "duration_hours": 2.0,
      "price_chf": 25.0,
      "suitable_for_children": true,{children_fields}
      "notes": "...",
      "address": "...",
      "google_maps_url": "https://maps.google.com/?q=..."
    }}
  ]
}}

- {AL['tags_hint']}{real_data_block}{weather_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Aktivitäten: {region})",
            job_id=self.job_id, agent="ActivitiesAgent",
        )
        await debug_logger.log_prompt("ActivitiesAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="ActivitiesAgent",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text
        result = parse_agent_json(text)

        activities = result.get("top_activities", [])
        if lat and lon and gp_results:
            gp_map = {a["name"].lower(): a for a in gp_results}
        else:
            gp_map = {}
        gp_names = list(gp_map.keys())

        for activity in activities:
            name_lower = activity.get("name", "").lower()

            # Exact match first, then fuzzy fallback
            matched = gp_map.get(name_lower)
            if not matched and gp_names:
                close = difflib.get_close_matches(name_lower, gp_names, n=1, cutoff=0.6)
                if close:
                    matched = gp_map[close[0]]

            if matched:
                if matched.get("photo_reference"):
                    activity["image_overview"] = place_photo_url(matched["photo_reference"])
                    activity["image_mood"] = None
                    activity["image_customer"] = None
                else:
                    images = await fetch_unsplash_images(
                        f"{activity.get('name', '')} {region}", "activity"
                    )
                    activity.update(images)
                if matched.get("place_id"):
                    activity["place_id"] = matched["place_id"]
                    activity["google_maps_url"] = f"https://www.google.com/maps/place/?q=place_id:{matched['place_id']}"
                if matched.get("lat") and matched.get("lon"):
                    activity["lat"] = matched["lat"]
                    activity["lon"] = matched["lon"]
            else:
                images = await fetch_unsplash_images(
                    f"{activity.get('name', '')} {region}", "activity"
                )
                activity.update(images)

        # Fallback: geocode unmatched activities via Find Place API
        unresolved = [a for a in activities if not a.get("place_id")]
        if unresolved:
            geo_tasks = [find_place_from_text(f"{a['name']}, {region}") for a in unresolved]
            geo_results = await asyncio.gather(*geo_tasks)
            for act, geo in zip(unresolved, geo_results):
                if geo:
                    act["place_id"] = geo.get("place_id")
                    if geo.get("lat") and geo.get("lon"):
                        act["lat"] = geo["lat"]
                        act["lon"] = geo["lon"]
                    if geo.get("place_id"):
                        act["google_maps_url"] = f"https://www.google.com/maps/place/?q=place_id:{geo['place_id']}"

        result["top_activities"] = activities
        return result
