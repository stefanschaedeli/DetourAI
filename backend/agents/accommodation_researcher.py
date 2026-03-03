import asyncio
from datetime import timedelta
from urllib.parse import quote
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from agents._client import get_client, get_model


def _build_booking_url(region: str, checkin, nights: int, adults: int, children: int) -> str:
    checkout = checkin + timedelta(days=nights)
    return (
        f"https://www.booking.com/search.html"
        f"?ss={quote(region)}"
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
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5")

    async def find_options(self, stop: dict, budget_per_night: float,
                           semaphore: asyncio.Semaphore = None) -> dict:
        req = self.request
        buffer = 1 - req.budget_buffer_percent / 100
        effective_rate = budget_per_night * buffer

        budget_rate    = round(effective_rate * 0.65, 2)
        comfort_rate   = round(effective_rate, 2)
        premium_rate   = round(effective_rate * 1.6, 2)

        nights = stop.get("nights", req.min_nights_per_stop)
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        children_count = len(req.children)
        styles_str = ", ".join(req.accommodation_styles) if req.accommodation_styles else "hotel, apartment"
        must_haves_str = ", ".join(req.accommodation_must_haves) if req.accommodation_must_haves else "WiFi"
        preferred_type = req.accommodation_styles[0] if req.accommodation_styles else "hotel"

        prompt = f"""Finde 4 Unterkunftsoptionen (3 Standard + 1 Geheimtipp) in {region}, {country}:

Reisende: {req.adults} Erwachsene{f', {children_count} Kinder' if children_count else ''}
Nächte: {nights}
Unterkunftsstile: {styles_str}
Ausstattung gewünscht: {must_haves_str}
Suchradius: {req.hotel_radius_km} km

Preisrahmen pro Nacht:
- Budget:  CHF {budget_rate:.0f} (65%)
- Komfort: CHF {comfort_rate:.0f} (100%)
- Premium: CHF {premium_rate:.0f} (160%)

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "options": [
    {{
      "id": "acc_{stop_id}_budget",
      "option_type": "budget",
      "name": "...",
      "type": "{preferred_type}",
      "price_per_night_chf": {budget_rate:.0f},
      "total_price_chf": {budget_rate * nights:.0f},
      "price_range": "€",
      "separate_rooms_available": false,
      "max_persons": 4,
      "rating": 7.5,
      "features": ["WiFi", "Parkplatz"],
      "teaser": "...",
      "suitable_for_children": true,
      "booking_hint": "booking.com"
    }},
    {{
      "id": "acc_{stop_id}_comfort",
      "option_type": "comfort",
      "name": "...",
      "type": "{preferred_type}",
      "price_per_night_chf": {comfort_rate:.0f},
      "total_price_chf": {comfort_rate * nights:.0f},
      "price_range": "€€",
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 8.5,
      "features": ["WiFi", "Frühstück", "Parkplatz"],
      "teaser": "...",
      "suitable_for_children": true,
      "booking_hint": "booking.com"
    }},
    {{
      "id": "acc_{stop_id}_premium",
      "option_type": "premium",
      "name": "...",
      "type": "{preferred_type}",
      "price_per_night_chf": {premium_rate:.0f},
      "total_price_chf": {premium_rate * nights:.0f},
      "price_range": "€€€",
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 9.0,
      "features": ["WiFi", "Pool", "Spa", "Frühstück"],
      "teaser": "...",
      "suitable_for_children": true,
      "booking_hint": "booking.com"
    }},
    {{
      "id": "acc_{stop_id}_geheimtipp",
      "option_type": "geheimtipp",
      "name": "...",
      "type": "bauernhof",
      "price_per_night_chf": {comfort_rate:.0f},
      "total_price_chf": {comfort_rate * nights:.0f},
      "price_range": "€€",
      "separate_rooms_available": true,
      "max_persons": 4,
      "rating": 9.2,
      "features": ["Natur", "Authentisch", "Ruhig"],
      "teaser": "...",
      "suitable_for_children": true,
      "booking_hint": "",
      "geheimtipp_hinweis": "Buche direkt beim Hof oder über lokales Tourismusbüro."
    }}
  ]
}}

Der Geheimtipp soll etwas Besonderes/Ungewöhnliches für die Region sein (Bauernhof, Glamping, Baumhaus, Boutique-Hotel, Weingut, etc.). Geheimtipp hat KEINEN booking_hint."""

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
                            max_tokens=1500,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": prompt}],
                        )
                    return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")
            else:
                def call():
                    return self.client.messages.create(
                        model=self.model,
                        max_tokens=1500,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": prompt}],
                    )
                return await call_with_retry(call, job_id=self.job_id, agent_name="AccommodationResearcher")

        response = await _call_with_semaphore()
        text = response.content[0].text
        result = parse_agent_json(text)

        arrival_day = stop.get("arrival_day", 1)
        checkin = req.start_date + timedelta(days=arrival_day - 1)

        for opt in result.get("options", []):
            if opt.get("option_type") != "geheimtipp":
                opt["booking_url"] = _build_booking_url(
                    region=region,
                    checkin=checkin,
                    nights=nights,
                    adults=req.adults,
                    children=children_count,
                )
            else:
                opt["booking_url"] = None
            actual_type = opt.get("type") or preferred_type
            images = await fetch_unsplash_images(f"{region} {actual_type}", preferred_type)
            opt.update(images)

        return result
