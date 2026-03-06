import asyncio
from datetime import timedelta
from urllib.parse import quote
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from agents._client import get_client, get_model


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
        self.model = get_model("claude-sonnet-4-5")

    async def find_options(self, stop: dict, budget_per_night: float,
                           semaphore: asyncio.Semaphore = None) -> dict:
        req = self.request
        nights = stop.get("nights", req.min_nights_per_stop)
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        children_count = len(req.children)
        styles_str = ", ".join(req.accommodation_styles) if req.accommodation_styles else "hotel, apartment"
        must_haves_str = ", ".join(req.accommodation_must_haves) if req.accommodation_must_haves else "WiFi"

        budget_min = round(budget_per_night * 0.75, 0)
        budget_max = round(budget_per_night * 1.30, 0)

        children_hint = ""
        if children_count > 0:
            children_hint = f"\nKinder: {children_count} — erwähne bitte Kindermenüs, Spielbereiche, Kinderanimation oder familienfreundliche Aktivitäten in der Beschreibung."

        extra_hint = ""
        if self.extra_instructions:
            extra_hint = f"\nZusätzliche Wünsche des Gastes: {self.extra_instructions}"

        prompt = f"""Finde genau 3 Unterkunftsoptionen in {region}, {country}.

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Nächte: {nights}
Gewünschte Unterkunftstypen: {styles_str}
Pflichtausstattung (must-haves): {must_haves_str}
Suchradius: {req.hotel_radius_km} km
Preisrahmen pro Nacht: CHF {budget_min:.0f} – CHF {budget_max:.0f}{children_hint}{extra_hint}

REGELN:
1. Alle 3 Optionen müssen vom Typ in [{styles_str}] sein — keine anderen Typen.
2. Versuche, alle must-haves zu erfüllen. Falls nicht möglich, erkläre es kurz im Teaser.
3. Die dritte Option (is_geheimtipp: true) soll etwas Besonderes/Ungewöhnliches für die Region sein (Glamping, Baumhaus, Boutique-Hotel, Weingut, Bauernhof, etc.) — aber ebenfalls vom erlaubten Typ.
4. Verwende realistische, tatsächlich existierende Hotelnamen für {region}.
5. Beschreibung: 1-2 Absätze auf Deutsch mit Zimmerausstattung, Hotelaktivitäten und spezifischen Services.
6. matched_must_haves: Array mit den must-haves, die diese Unterkunft konkret erfüllt.
7. hotel_website_url: Echte Hotelwebseite falls bekannt, sonst null.

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
      "matched_must_haves": ["WiFi"],
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
      "matched_must_haves": ["WiFi", "Frühstück"],
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
      "rating": 9.0,
      "features": ["Natur", "Authentisch", "Ruhig"],
      "teaser": "...",
      "description": "...",
      "suitable_for_children": true,
      "is_geheimtipp": true,
      "matched_must_haves": [],
      "hotel_website_url": null,
      "geheimtipp_hinweis": "Buche direkt beim Betrieb oder über lokales Tourismusbüro."
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
                            max_tokens=2500,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": prompt}],
                        )
                    return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")
            else:
                def call():
                    return self.client.messages.create(
                        model=self.model,
                        max_tokens=2500,
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

            actual_type = opt.get("type") or (req.accommodation_styles[0] if req.accommodation_styles else "hotel")
            images = await fetch_unsplash_images(f"{region} {actual_type}", actual_type)
            opt.update(images)
            return opt

        options = await asyncio.gather(*[enrich_option(opt) for opt in result.get("options", [])])
        result["options"] = list(options)

        return result
