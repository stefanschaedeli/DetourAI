import asyncio
from datetime import timedelta
from urllib.parse import quote
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_hotels, place_photo_url
from utils.currency import detect_currency, get_chf_rate
from agents._client import get_client, get_model, get_max_tokens
from utils.settings_store import get_setting

AGENT_KEY = "accommodation_researcher"


def _build_booking_url(hotel_name: str, region: str, checkin, nights: int, adults: int, children: int) -> str:
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
        f"&lang=de"
    )


def _build_booking_search_url(city: str, country: str, checkin, nights: int, adults: int, children: int) -> str:
    """Geheimtipp: Suchlink nur mit Stadt/Region, kein konkreter Hotelname."""
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
        f"&lang=de"
    )


SYSTEM_PROMPT = (
    "Du bist ein Unterkunftsberater. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)


class AccommodationResearcherAgent:
    def __init__(self, request: TravelRequest, job_id: str, extra_instructions: str = ""):
        self.request = request
        self.job_id = job_id
        self.extra_instructions = extra_instructions
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def find_options(self, stop: dict, budget_per_night: float,
                           semaphore: asyncio.Semaphore = None) -> dict:
        req = self.request
        nights = stop.get("nights", req.min_nights_per_stop)
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        children_count = len(req.children)
        preferences = req.accommodation_preferences
        pref0 = preferences[0] if len(preferences) > 0 else "komfortables Hotel"
        pref1 = preferences[1] if len(preferences) > 1 else "gemütliches Apartment"
        pref2 = preferences[2] if len(preferences) > 2 else "naturnahe Unterkunft"

        budget_min = round(budget_per_night * get_setting("budget.acc_multiplier_min"), 0)
        budget_max = round(budget_per_night * get_setting("budget.acc_multiplier_max"), 0)

        children_hint = ""
        if children_count > 0:
            children_hint = f"\nKinder: {children_count} — erwähne bitte Kindermenüs, Spielbereiche, Kinderanimation oder familienfreundliche Aktivitäten in der Beschreibung."

        extra_hint = ""
        if self.extra_instructions:
            extra_hint = f"\nZusätzliche Wünsche des Gastes: {self.extra_instructions}"

        # Pre-fetch: echte Hoteldaten + Wechselkurse
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""
        currency_block = ""

        if lat and lon:
            gp_results = await search_hotels(lat, lon, radius_m=req.hotel_radius_km * 1000)
            if gp_results:
                lines = [f"- {h['name']} | ★{h.get('rating','?')} ({h.get('user_ratings_total',0)} Bewertungen) | {h.get('address','')}" for h in gp_results[:8]]
                real_data_block = "\n\nEchte Hotels in der Nähe (Google Places Daten):\n" + "\n".join(lines) + "\nBevorzuge diese echten Unterkünfte und ergänze mit deinem Wissen.\n"

        if not real_data_block:
            brave_results = await search_places(f"Hotel Unterkunft {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}★) — {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = "\n\nEchte Suchergebnisse für Unterkünfte:\n" + "\n".join(lines) + "\nBevorzuge diese echten Unterkünfte.\n"

        local_currency = detect_currency(country)
        if local_currency != "CHF":
            rate = await get_chf_rate(local_currency)
            currency_block = f"\nDas Land verwendet {local_currency}. Gib Preise trotzdem in CHF an.\nAktueller Kurs: 1 {local_currency} = {rate:.4f} CHF\n"

        prompt = f"""Finde genau 4 Unterkunftsoptionen in {region}, {country}.

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Nächte: {nights}
Suchradius: {req.hotel_radius_km} km
Preisrahmen pro Nacht: CHF {budget_min:.0f} – CHF {budget_max:.0f}{children_hint}{extra_hint}{currency_block}

REGELN:
1. Option 1 (preference_index: 0): Entspricht diesem Wunsch des Gastes: "{pref0}"
2. Option 2 (preference_index: 1): Entspricht diesem Wunsch des Gastes: "{pref1}"
3. Option 3 (preference_index: 2): Entspricht diesem Wunsch des Gastes: "{pref2}"
4. Option 4 (is_geheimtipp: true, preference_index: null): Ein echter Geheimtipp — etwas Besonderes/Ungewöhnliches für die Region (Glamping, Baumhaus, Boutique-Hotel, Weingut, Bauernhof, etc.)
5. Verwende realistische, tatsächlich existierende Unterkunftsnamen für {region}.
6. Beschreibung: 1-2 Absätze auf Deutsch mit Zimmerausstattung, Aktivitäten und spezifischen Services.
7. matched_must_haves: Immer leeres Array [].
8. hotel_website_url: Echte Hotelwebseite falls bekannt, sonst null.

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "options": [
    {{
      "id": "acc_{stop_id}_1",
      "name": "...",
      "type": "...",
      "price_per_night_chf": {budget_min:.0f},
      "total_price_chf": {budget_min * nights:.0f},
      "separate_rooms_available": false,
      "max_persons": 4,
      "rating": 8.0,
      "features": ["WiFi", "Parkplatz"],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": false,
      "preference_index": 0,
      "matched_must_haves": [],
      "hotel_website_url": null
    }},
    {{
      "id": "acc_{stop_id}_2",
      "name": "...",
      "type": "...",
      "price_per_night_chf": {budget_per_night:.0f},
      "total_price_chf": {budget_per_night * nights:.0f},
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 8.5,
      "features": ["WiFi", "Frühstück", "Parkplatz"],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": false,
      "preference_index": 1,
      "matched_must_haves": [],
      "hotel_website_url": null
    }},
    {{
      "id": "acc_{stop_id}_3",
      "name": "...",
      "type": "...",
      "price_per_night_chf": {budget_per_night:.0f},
      "total_price_chf": {budget_per_night * nights:.0f},
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 8.8,
      "features": ["Natur", "Ruhig"],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": false,
      "preference_index": 2,
      "matched_must_haves": [],
      "hotel_website_url": null
    }},
    {{
      "id": "acc_{stop_id}_4",
      "name": "...",
      "type": "...",
      "price_per_night_chf": {budget_per_night:.0f},
      "total_price_chf": {budget_per_night * nights:.0f},
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 9.0,
      "features": ["Einzigartig", "Authentisch", "Ruhig"],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": true,
      "preference_index": null,
      "matched_must_haves": [],
      "hotel_website_url": null,
      "geheimtipp_hinweis": "Buche direkt beim Betrieb oder über lokales Tourismusbüro."
    }}
  ]
}}{real_data_block}"""

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
                            max_tokens=get_max_tokens(AGENT_KEY, 3500),
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": prompt}],
                        )
                    return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")
            else:
                def call():
                    return self.client.messages.create(
                        model=self.model,
                        max_tokens=get_max_tokens(AGENT_KEY, 3500),
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": prompt}],
                    )
                return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")

        response = await _call_with_semaphore()
        text = response.content[0].text
        result = parse_agent_json(text)

        arrival_day = stop.get("arrival_day", 1)
        checkin = req.start_date + timedelta(days=arrival_day - 1)

        async def enrich_option(opt: dict) -> dict:
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
                )

            # Bilder: Google Places wenn verfügbar
            hotel_name_lower = hotel_name.lower()
            if lat and lon:
                gp_hotels = await search_hotels(lat, lon, radius_m=req.hotel_radius_km * 1000)
                gp_match = next((h for h in gp_hotels if h["name"].lower() == hotel_name_lower), None)
            else:
                gp_match = None

            if gp_match and gp_match.get("photo_reference"):
                opt["image_overview"] = place_photo_url(gp_match["photo_reference"])
                opt["image_mood"] = None
                opt["image_customer"] = None
            else:
                actual_type = opt.get("type") or "unterkunft"
                images = await fetch_unsplash_images(f"{region} {actual_type}", actual_type)
                opt.update(images)
            return opt

        options = await asyncio.gather(*[enrich_option(opt) for opt in result.get("options", [])])
        result["options"] = list(options)

        return result
