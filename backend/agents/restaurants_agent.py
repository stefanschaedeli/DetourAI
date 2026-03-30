from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_restaurants as gp_search_restaurants, place_photo_url
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "restaurants"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Restaurantberater für Reisende. "
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a restaurant advisor for travelers. "
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप यात्रियों के लिए एक रेस्तरां सलाहकार हैं। "
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}


class RestaurantsAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict) -> dict:
        req = self.request
        lang = getattr(req, 'language', 'de')
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")

        persons = req.adults + len(req.children)
        total_days = req.total_days if req.total_days > 0 else 1
        budget_per_meal = round(req.budget_chf * 0.15 / persons / total_days, 2)
        children_count = len(req.children)

        _L = {
            "de": {
                "reviews": "Bewertungen", "price_level": "Preisniveau",
                "real_restaurants": "Echte Restaurants in der Nähe (Google Places Daten):",
                "choose_real": "Wähle aus diesen echten Restaurants und ergänze mit deinem Wissen.",
                "real_search": "Echte Suchergebnisse für Restaurants in der Region:",
                "prefer_real": "Bevorzuge diese echten Orte in deiner Empfehlung.",
                "recommend": "Empfehle Restaurants in",
                "travelers": "Reisende", "adults": "Erwachsene", "children": "Kinder",
                "styles": "Reisestile", "styles_default": "allgemein",
                "search_radius": "Suchradius", "max_rest": "Max. Restaurants",
                "budget_meal": "Budget pro Mahlzeit/Person",
                "important": "WICHTIG: Alle Restaurants müssen innerhalb des Suchradius von {r} km vom Übernachtungsort in {region} liegen. Keine Ausnahmen.",
                "return_json": "Gib exakt dieses JSON zurück:",
                "desc_label": "Reisebeschreibung", "pref_label": "Bevorzugte Aktivitäten", "mandatory_label": "Pflichtaktivitäten",
            },
            "en": {
                "reviews": "reviews", "price_level": "Price level",
                "real_restaurants": "Real restaurants nearby (Google Places data):",
                "choose_real": "Choose from these real restaurants and supplement with your knowledge.",
                "real_search": "Real search results for restaurants in the region:",
                "prefer_real": "Prefer these real places in your recommendation.",
                "recommend": "Recommend restaurants in",
                "travelers": "Travelers", "adults": "adults", "children": "children",
                "styles": "Travel styles", "styles_default": "general",
                "search_radius": "Search radius", "max_rest": "Max. restaurants",
                "budget_meal": "Budget per meal/person",
                "important": "IMPORTANT: All restaurants must be within the search radius of {r} km from the accommodation in {region}. No exceptions.",
                "return_json": "Return exactly this JSON:",
                "desc_label": "Travel description", "pref_label": "Preferred activities", "mandatory_label": "Mandatory activities",
            },
            "hi": {
                "reviews": "समीक्षाएं", "price_level": "मूल्य स्तर",
                "real_restaurants": "पास के वास्तविक रेस्तरां (Google Places डेटा):",
                "choose_real": "इन वास्तविक रेस्तरां में से चुनें और अपने ज्ञान से पूरक करें।",
                "real_search": "क्षेत्र में रेस्तरां के लिए वास्तविक खोज परिणाम:",
                "prefer_real": "अपनी सिफारिश में इन वास्तविक स्थानों को प्राथमिकता दें।",
                "recommend": "में रेस्तरां की सिफारिश करें",
                "travelers": "यात्रीगण", "adults": "वयस्क", "children": "बच्चे",
                "styles": "यात्रा शैलियां", "styles_default": "सामान्य",
                "search_radius": "खोज दायरा", "max_rest": "अधिकतम रेस्तरां",
                "budget_meal": "प्रति भोजन/व्यक्ति बजट",
                "important": "महत्वपूर्ण: सभी रेस्तरां {region} में आवास से {r} km के खोज दायरे के भीतर होने चाहिए। कोई अपवाद नहीं।",
                "return_json": "बिल्कुल यह JSON लौटाएं:",
                "desc_label": "यात्रा विवरण", "pref_label": "पसंदीदा गतिविधियां", "mandatory_label": "अनिवार्य गतिविधियां",
            },
        }
        RL = _L.get(lang, _L["de"])

        # Pre-fetch: echte Restaurantdaten
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""

        if lat and lon:
            gp_results = await gp_search_restaurants(lat, lon, radius_m=req.activities_radius_km * 1000)
            if gp_results:
                lines = []
                for r in gp_results[:8]:
                    price = "\u20ac" * r.get("price_level", 2) if r.get("price_level") else "?"
                    lines.append(f"- {r['name']} | \u2605{r.get('rating','?')} ({r.get('user_ratings_total',0)} {RL['reviews']}) | {r.get('address','')} | {RL['price_level']}: {price}")
                real_data_block = f"\n\n{RL['real_restaurants']}\n" + "\n".join(lines) + f"\n{RL['choose_real']}\n"

        if not real_data_block:
            brave_results = await search_places(f"restaurants {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}\u2605) \u2014 {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = f"\n\n{RL['real_search']}\n" + "\n".join(lines) + f"\n{RL['prefer_real']}\n"

        # Optionale Wunsch-Kontextblöcke (CTX-02, CTX-03)
        desc_line = f"\n{RL['desc_label']}: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\n{RL['pref_label']}: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\n{RL['mandatory_label']}: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        children_str = f", {children_count} {RL['children']}" if children_count else ""
        if lang == "hi":
            rec_line = f"{region}, {country} {RL['recommend']}:"
        else:
            rec_line = f"{RL['recommend']} {region}, {country}:"

        prompt = f"""{rec_line}

{RL['travelers']}: {req.adults} {RL['adults']}{children_str}
{RL['styles']}: {', '.join(req.travel_styles) if req.travel_styles else RL['styles_default']}
{RL['search_radius']}: {req.activities_radius_km} km
{RL['max_rest']}: {req.max_restaurants_per_stop}
{RL['budget_meal']}: ca. CHF {budget_per_meal:.0f}{mandatory_line}{pref_line}{desc_line}

{RL['important'].format(r=req.activities_radius_km, region=region)}

{RL['return_json']}
{{
  "stop_id": {stop_id},
  "region": "{region}",
  "restaurants": [
    {{
      "name": "...",
      "cuisine": "French",
      "price_range": "\u20ac\u20ac",
      "family_friendly": true,
      "notes": "..."
    }}
  ]
}}{real_data_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Restaurants: {region})",
            job_id=self.job_id, agent="RestaurantsAgent",
        )
        await debug_logger.log_prompt("RestaurantsAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RestaurantsAgent",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text
        result = parse_agent_json(text)

        # Bilder: Google Places Photo wenn verfügbar, sonst Stub
        if lat and lon:
            gp_results = await gp_search_restaurants(lat, lon, radius_m=req.activities_radius_km * 1000)
            gp_map = {r["name"].lower(): r for r in gp_results} if gp_results else {}
        else:
            gp_map = {}

        for restaurant in result.get("restaurants", []):
            matched = gp_map.get(restaurant.get("name", "").lower())
            if matched and matched.get("photo_reference"):
                restaurant["image_overview"] = place_photo_url(matched["photo_reference"])
                restaurant["image_mood"] = None
                restaurant["image_customer"] = None
            else:
                images = await fetch_unsplash_images(
                    f"{restaurant.get('name', '')} {region} {restaurant.get('cuisine', '')}",
                    "restaurant",
                )
                restaurant.update(images)
            if matched and matched.get("place_id"):
                restaurant["place_id"] = matched["place_id"]

        return result
