"""Agent that researches accommodation options for each trip stop, enriched with Google Places data, images, and Booking.com links."""

import asyncio
from datetime import timedelta
from urllib.parse import quote
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.google_places import search_hotels, place_photo_url, find_place_from_text, place_details
from utils.currency import detect_currency, get_chf_rate
from utils.maps_helper import haversine_km
from agents._client import get_client, get_model, get_max_tokens
from utils.settings_store import get_setting

AGENT_KEY = "accommodation_researcher"


def _booking_lang(language: str) -> str:
    """Map travel language to Booking.com lang code (Hindi falls back to English)."""
    return {"de": "de", "en": "en", "hi": "en"}.get(language, "de")


def _build_booking_url(hotel_name: str, region: str, checkin, nights: int, adults: int, children: int, language: str = "de") -> str:
    """Build a Booking.com deep-link URL pre-filled with hotel name, dates, and guest count."""
    checkout = checkin + timedelta(days=nights)
    search_term = f"{hotel_name}, {region}"
    return (
        f"https://www.booking.com/searchresults.html"
        f"?ss={quote(search_term)}"
        f"&ss_raw={quote(search_term)}"
        f"&checkin={checkin.isoformat()}"
        f"&checkout={checkout.isoformat()}"
        f"&group_adults={adults}"
        f"&group_children={children}"
        f"&no_rooms=1"
        f"&lang={_booking_lang(language)}"
    )


def _build_booking_search_url(city: str, country: str, checkin, nights: int, adults: int, children: int, language: str = "de") -> str:
    """Build a Booking.com search URL for a city/region without a specific hotel name (used for Geheimtipp options)."""
    checkout = checkin + timedelta(days=nights)
    search_term = f"{city}, {country}"
    return (
        f"https://www.booking.com/searchresults.html"
        f"?ss={quote(search_term)}"
        f"&checkin={checkin.isoformat()}"
        f"&checkout={checkout.isoformat()}"
        f"&group_adults={adults}"
        f"&group_children={children}"
        f"&no_rooms=1"
        f"&lang={_booking_lang(language)}"
    )


SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Unterkunftsberater. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are an accommodation advisor. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक आवास सलाहकार हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class AccommodationResearcherAgent:
    """Agent that generates 4 accommodation options per stop (3 preference-matched + 1 Geheimtipp), enriched with Google Places data and Booking.com links."""

    def __init__(self, request: TravelRequest, job_id: str, extra_instructions: str = ""):
        self.request = request
        self.job_id = job_id
        self.extra_instructions = extra_instructions
        self.client = get_client()
        # Haiku is sufficient for structured accommodation selection; much faster generation.
        self.model = get_model("claude-haiku-4-5", AGENT_KEY)

    async def find_options(self, stop: dict, budget_per_night: float,
                           semaphore: asyncio.Semaphore = None) -> dict:
        """Research and return accommodation options for one stop, respecting the nightly budget and optional concurrency semaphore."""
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        nights = stop.get("nights", req.min_nights_per_stop)
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        children_count = len(req.children)
        preferences = req.accommodation_preferences

        _pref_defaults = {
            "de": ["komfortables Hotel", "gemütliches Apartment", "naturnahe Unterkunft"],
            "en": ["comfortable hotel", "cozy apartment", "nature-close accommodation"],
            "hi": ["आरामदायक होटल", "आरामदायक अपार्टमेंट", "प्रकृति के करीब आवास"],
        }
        defaults = _pref_defaults.get(lang, _pref_defaults["de"])
        pref0 = preferences[0] if len(preferences) > 0 else defaults[0]
        pref1 = preferences[1] if len(preferences) > 1 else defaults[1]
        pref2 = preferences[2] if len(preferences) > 2 else defaults[2]

        budget_min = round(budget_per_night * get_setting("budget.acc_multiplier_min"), 0)
        budget_max = round(budget_per_night * get_setting("budget.acc_multiplier_max"), 0)

        _L = {
            "de": {
                "children_hint": "Kinder: {n} — erwähne bitte Kindermenüs, Spielbereiche, Kinderanimation oder familienfreundliche Aktivitäten in der Beschreibung.",
                "extra_hint": "Zusätzliche Wünsche des Gastes",
                "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
                "currency_note": "Das Land verwendet {c}. Gib Preise trotzdem in CHF an.\nAktueller Kurs: 1 {c} = {r} CHF",
                "coord_hint": "Stopzentrum: {lat}N, {lon}E — alle Unterkuenfte muessen innerhalb von {r} km davon liegen.",
                "find": "Finde genau 4 Unterkunftsoptionen in",
                "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder",
                "nights": "Nächte", "search_radius": "Suchradius",
                "price_range": "Preisrahmen pro Nacht",
                "rules": "REGELN",
                "rule1": 'Option 1 (preference_index: 0): Entspricht diesem Wunsch des Gastes: "{p}"',
                "rule2": 'Option 2 (preference_index: 1): Entspricht diesem Wunsch des Gastes: "{p}"',
                "rule3": 'Option 3 (preference_index: 2): Entspricht diesem Wunsch des Gastes: "{p}"',
                "rule4": "Option 4 (is_geheimtipp: true, preference_index: null): Ein echter Geheimtipp — etwas Besonderes oder Ungewöhnliches für die Region. MUSS innerhalb von {r} km vom Zentrum von {region} liegen.",
                "rule5": "Verwende realistische, tatsächlich existierende Unterkunftsnamen für {region}.",
                "rule6": "Beschreibung: 1-2 Absätze mit Zimmerausstattung, Aktivitäten und spezifischen Services.",
                "rule7": "matched_must_haves: Immer leeres Array [].",
                "rule8": "hotel_website_url: Echte Hotelwebseite falls bekannt, sonst null.",
                "json_instruction": "Gib exakt dieses JSON-Format zurück (4 Objekte im options-Array, jedes mit denselben Feldern):",
            },
            "en": {
                "children_hint": "Children: {n} — please mention children's menus, play areas, kids' animation, or family-friendly activities in the description.",
                "extra_hint": "Additional guest requests",
                "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
                "currency_note": "The country uses {c}. Still provide prices in CHF.\nCurrent rate: 1 {c} = {r} CHF",
                "coord_hint": "Stop center: {lat}N, {lon}E — all accommodations must be within {r} km of this.",
                "find": "Find exactly 4 accommodation options in",
                "travelers": "Travelers", "adults": "adults", "children": "children",
                "nights": "Nights", "search_radius": "Search radius",
                "price_range": "Price range per night",
                "rules": "RULES",
                "rule1": 'Option 1 (preference_index: 0): Matches this guest preference: "{p}"',
                "rule2": 'Option 2 (preference_index: 1): Matches this guest preference: "{p}"',
                "rule3": 'Option 3 (preference_index: 2): Matches this guest preference: "{p}"',
                "rule4": "Option 4 (is_geheimtipp: true, preference_index: null): A real hidden gem — something special or unusual for the region. MUST be within {r} km of the center of {region}.",
                "rule5": "Use realistic, actually existing accommodation names for {region}.",
                "rule6": "Description: 1-2 paragraphs with room amenities, activities, and specific services.",
                "rule7": "matched_must_haves: Always empty array [].",
                "rule8": "hotel_website_url: Real hotel website if known, otherwise null.",
                "json_instruction": "Return exactly this JSON format (4 objects in the options array, each with the same fields):",
            },
            "hi": {
                "children_hint": "बच्चे: {n} — कृपया विवरण में बच्चों का मेनू, खेल क्षेत्र, या परिवार-अनुकूल गतिविधियों का उल्लेख करें।",
                "extra_hint": "अतिथि के अतिरिक्त अनुरोध",
                "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
                "currency_note": "यह देश {c} का उपयोग करता है। फिर भी CHF में कीमतें दें।\nवर्तमान दर: 1 {c} = {r} CHF",
                "coord_hint": "स्टॉप केंद्र: {lat}N, {lon}E — सभी आवास इससे {r} km के भीतर होने चाहिए।",
                "find": "में बिल्कुल 4 आवास विकल्प खोजें",
                "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे",
                "nights": "रातें", "search_radius": "खोज दायरा",
                "price_range": "प्रति रात मूल्य सीमा",
                "rules": "नियम",
                "rule1": 'विकल्प 1 (preference_index: 0): इस अतिथि वरीयता से मेल खाता है: "{p}"',
                "rule2": 'विकल्प 2 (preference_index: 1): इस अतिथि वरीयता से मेल खाता है: "{p}"',
                "rule3": 'विकल्प 3 (preference_index: 2): इस अतिथि वरीयता से मेल खाता है: "{p}"',
                "rule4": "विकल्प 4 (is_geheimtipp: true, preference_index: null): एक वास्तविक छिपा रत्न — क्षेत्र के लिए कुछ विशेष या असामान्य। {region} के केंद्र से {r} km के भीतर होना चाहिए।",
                "rule5": "{region} के लिए यथार्थवादी, वास्तव में मौजूद आवास नामों का उपयोग करें।",
                "rule6": "विवरण: कमरे की सुविधाओं, गतिविधियों और विशिष्ट सेवाओं के साथ 1-2 पैराग्राफ।",
                "rule7": "matched_must_haves: हमेशा खाली सरणी []।",
                "rule8": "hotel_website_url: वास्तविक होटल वेबसाइट यदि ज्ञात हो, अन्यथा null।",
                "json_instruction": "बिल्कुल इस JSON प्रारूप को लौटाएं (options array में 4 ऑब्जेक्ट, प्रत्येक में समान फ़ील्ड):",
            },
        }
        AL = _L.get(lang, _L["de"])

        children_hint = ""
        if children_count > 0:
            children_hint = "\n" + AL["children_hint"].format(n=children_count)

        extra_hint = ""
        if self.extra_instructions:
            extra_hint = f"\n{AL['extra_hint']}: {self.extra_instructions}"

        # Optionale Wunsch-Kontextblöcke (CTX-02, CTX-03)
        desc_line = f"\n{AL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{AL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{AL['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        # Pre-fetch: echte Hoteldaten + Wechselkurse
        lat = stop.get("lat")
        lon = stop.get("lon")
        currency_block = ""
        gp_results: list = []

        arrival_day = stop.get("arrival_day", 1)
        checkin = req.start_date + timedelta(days=arrival_day - 1)

        if lat and lon:
            gp_results = await search_hotels(lat, lon, radius_m=req.hotel_radius_km * 1000)

        local_currency = detect_currency(country)
        if local_currency != "CHF":
            rate = await get_chf_rate(local_currency)
            currency_block = "\n" + AL["currency_note"].format(c=local_currency, r=f"{rate:.4f}") + "\n"

        coord_hint = ""
        if lat and lon:
            coord_hint = "\n" + AL["coord_hint"].format(lat=f"{lat:.4f}", lon=f"{lon:.4f}", r=req.hotel_radius_km)

        children_str = f", {children_count} {AL['children']}" if children_count else ""
        if lang == "hi":
            find_line = f"{region}, {country} {AL['find']}."
        else:
            find_line = f"{AL['find']} {region}, {country}."

        prompt = f"""{find_line}

{AL['travelers']}: {req.adults} {AL['adults']}{children_str}
{AL['nights']}: {nights}
{AL['search_radius']}: {req.hotel_radius_km} km{coord_hint}
{AL['price_range']}: CHF {budget_min:.0f} – CHF {budget_max:.0f}{children_hint}{extra_hint}{mandatory_line}{pref_line}{desc_line}{currency_block}

{AL['rules']}:
1. {AL['rule1'].format(p=pref0)}
2. {AL['rule2'].format(p=pref1)}
3. {AL['rule3'].format(p=pref2)}
4. {AL['rule4'].format(r=req.hotel_radius_km, region=region)}
5. {AL['rule5'].format(region=region)}
6. {AL['rule6']}
7. {AL['rule7']}
8. {AL['rule8']}

{AL['json_instruction']}
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "options": [
    {{
      "id": "acc_{stop_id}_N",
      "name": "...",
      "type": "...",
      "price_per_night_chf": {budget_per_night:.0f},
      "total_price_chf": {budget_per_night * nights:.0f},
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 8.5,
      "features": ["...", "..."],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": false,
      "preference_index": 0,
      "matched_must_haves": [],
      "hotel_website_url": null
    }}
  ]
}}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Stop {stop_id}: {region})",
            job_id=self.job_id, agent="AccommodationResearcher",
        )
        await debug_logger.log_prompt("AccommodationResearcher", self.model, prompt, job_id=self.job_id)

        async def _call_with_semaphore():
            if semaphore:
                async with semaphore:
                    def call():
                        return self.client.messages.create(
                            model=self.model,
                            max_tokens=get_max_tokens(AGENT_KEY, 2048),
                            system=system_prompt,
                            messages=[{"role": "user", "content": prompt}],
                        )
                    return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")
            else:
                def call():
                    return self.client.messages.create(
                        model=self.model,
                        max_tokens=get_max_tokens(AGENT_KEY, 2048),
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}],
                    )
                return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")

        response = await _call_with_semaphore()
        text = response.content[0].text
        result = parse_agent_json(text)

        # Tag AI options with their source before enrichment
        for opt in result.get("options", []):
            opt["source"] = "ai_geheimtipp" if opt.get("is_geheimtipp") else "ai"

        async def enrich_option(opt: dict, cached_gp: list) -> dict:
            # Google options are already fully enriched — skip redundant processing
            if opt.get("source") == "google":
                return opt

            hotel_name = opt.get("name", "")
            is_geheimtipp = opt.get("is_geheimtipp", False)

            if hotel_name and not is_geheimtipp:
                opt["booking_url"] = _build_booking_url(
                    hotel_name=hotel_name,
                    region=region,
                    checkin=checkin,
                    nights=nights,
                    adults=req.adults,
                    children=children_count,
                    language=lang,
                )
            else:
                opt["booking_url"] = None

            if is_geheimtipp:
                opt["booking_search_url"] = _build_booking_search_url(
                    city=region,
                    country=country,
                    checkin=checkin,
                    nights=nights,
                    adults=req.adults,
                    children=children_count,
                    language=lang,
                )

            # ACC-03: Look up AI hotels in Google Places by name to get real place_id,
            # coordinates, rating, and photo. First try the pre-fetched cache by name;
            # if not found, call find_place_from_text (cheapest Places API endpoint).
            hotel_name_lower = hotel_name.lower()
            gp_match = None
            if cached_gp:
                gp_match = next((h for h in cached_gp if h["name"].lower() == hotel_name_lower), None)

            # For non-geheimtipp AI options: try Google lookup if not already in cache
            if not gp_match and not is_geheimtipp and hotel_name:
                found = await find_place_from_text(f"{hotel_name}, {region}, {country}")
                if found and found.get("place_id"):
                    # Check if place_id matches something in cache (avoid duplicate API call)
                    cached_by_id = next(
                        (h for h in cached_gp if h.get("place_id") == found["place_id"]), None
                    )
                    if cached_by_id:
                        gp_match = cached_by_id
                    else:
                        # Fetch details for photo + real rating
                        details = await place_details(found["place_id"])
                        photos = details.get("photos", [])
                        photo_ref = photos[0].get("photo_reference") if photos else None
                        gp_match = {
                            "place_id": found["place_id"],
                            "name": found.get("name", hotel_name),
                            "lat": found.get("lat"),
                            "lon": found.get("lon"),
                            "rating": details.get("rating"),
                            "photo_reference": photo_ref,
                        }
                        await debug_logger.log(
                            LogLevel.DEBUG,
                            f"ACC-03: '{hotel_name}' in Google Places gefunden — place_id={found['place_id']}",
                            job_id=self.job_id, agent=AGENT_KEY,
                        )

            # Overwrite AI-estimated rating with real Google rating if available
            if gp_match and gp_match.get("rating") is not None and not is_geheimtipp:
                real_rating = gp_match["rating"]
                # Google rating is 0-5; convert to app's 0-10 scale only if it looks like 0-5
                if real_rating <= 5.0:
                    opt["rating"] = round(real_rating * 2, 1)
                else:
                    opt["rating"] = real_rating

            # ACC-01: haversine distance check for Geheimtipp
            if is_geheimtipp and lat and lon and gp_match and gp_match.get("lat") and gp_match.get("lon"):
                dist_km = haversine_km((lat, lon), (gp_match["lat"], gp_match["lon"]))
                if dist_km > req.hotel_radius_km:
                    await debug_logger.log(
                        LogLevel.DEBUG,
                        f"Geheimtipp '{hotel_name}' zu weit entfernt ({dist_km:.1f} km > {req.hotel_radius_km} km) — entfernt",
                        job_id=self.job_id, agent=AGENT_KEY,
                    )
                    opt["_geheimtipp_too_far"] = True

            if gp_match and gp_match.get("photo_reference"):
                opt["image_overview"] = place_photo_url(gp_match["photo_reference"])
                opt["image_mood"] = None
                opt["image_customer"] = None
            else:
                actual_type = opt.get("type") or "unterkunft"
                images = await fetch_unsplash_images(f"{region} {actual_type}", actual_type)
                opt.update(images)
            if gp_match and gp_match.get("place_id"):
                opt["place_id"] = gp_match["place_id"]
            return opt

        # Enrich all AI options with Google Places data (rating, photos, place_id) post-call
        options = list(await asyncio.gather(*[enrich_option(opt, gp_results) for opt in result.get("options", [])]))

        # ACC-01: drop geheimtipps that are too far from stop center
        options = [o for o in options if not o.pop("_geheimtipp_too_far", False)]

        # ACC-02: name-based dedup — remove duplicate names from AI output
        seen_names: set = set()
        deduped = []
        for opt in options:
            key = opt.get("name", "").strip().lower()
            if key and key not in seen_names:
                seen_names.add(key)
                deduped.append(opt)
            elif not key:
                deduped.append(opt)  # keep options without names
        options = deduped

        result["options"] = options

        return result
