import asyncio
import difflib
from collections import defaultdict
from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.image_fetcher import fetch_unsplash_images
from utils.brave_search import search_places
from utils.google_places import search_attractions, place_photo_url
from utils.weather import get_forecast
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "activities"

SYSTEM_PROMPT = (
    "Du bist ein erfahrener Aktivitätsberater für Reisende mit Expertise in "
    "altersgerechten Erlebnissen, lokalen Geheimtipps und saisonalen Empfehlungen. "
    "Du achtest darauf, eine ausgewogene Mischung aus Aktivitäten zu empfehlen: "
    "aktiv & interaktiv, kulturell, Naturerlebnis und kulinarisch. "
    "Bei Familien mit Kindern priorisierst du Erlebnisse, bei denen alle Altersgruppen "
    "Spass haben, und schlägst auch spezifische Kinderaktivitäten vor. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
)

# Altersgruppen-Mapping für Kinder
_AGE_GROUPS = [
    (0, 2, "Babys/Kleinkinder"),
    (3, 5, "Kindergarten"),
    (6, 11, "Schulkinder"),
    (12, 17, "Teenager"),
]

# Aktivitätshinweise pro Altersgruppe
_AGE_ACTIVITY_HINTS = {
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
}

# Aktivitätshinweise pro Reisestil
_STYLE_HINTS = {
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
}


def _describe_travelers(req: TravelRequest) -> str:
    """Beschreibt die Reisegruppe mit Altersgruppen der Kinder."""
    parts = [f"{req.adults} Erwachsene"]
    if not req.children:
        return parts[0]

    groups: dict[str, list[int]] = defaultdict(list)
    for child in req.children:
        for lo, hi, label in _AGE_GROUPS:
            if lo <= child.age <= hi:
                groups[label].append(child.age)
                break

    child_parts = []
    for _, _, label in _AGE_GROUPS:
        if label in groups:
            ages = sorted(groups[label])
            ages_str = ", ".join(str(a) for a in ages)
            child_parts.append(f"{label}: {ages_str} Jahre")

    total = len(req.children)
    parts.append(f"{total} Kind{'er' if total > 1 else ''} ({', '.join(child_parts)})")
    return ", ".join(parts)


def _build_style_guidance(req: TravelRequest) -> str:
    """Baut kontextabhängige Aktivitätshinweise basierend auf Reisestil und Altersgruppen."""
    blocks = []

    # Altersgruppen-spezifische Hinweise wenn Kinder dabei
    if req.children:
        seen_groups: set[str] = set()
        for child in req.children:
            for lo, hi, label in _AGE_GROUPS:
                if lo <= child.age <= hi and label not in seen_groups:
                    seen_groups.add(label)
                    blocks.append(_AGE_ACTIVITY_HINTS[label])
                    break

    # Reisestil-Hinweise
    for style in req.travel_styles:
        if style in _STYLE_HINTS:
            blocks.append(_STYLE_HINTS[style])

    # Familienaktiv-Stil: Extra-Hinweis
    if "kids" in req.travel_styles and req.children:
        blocks.append(
            "WICHTIG: Mindestens die Hälfte der Aktivitäten sollte speziell für Kinder "
            "geeignet sein. Bevorzuge interaktive, spielerische Erlebnisse."
        )

    if not blocks:
        return ""

    return "\n\nSpezifische Hinweise für diese Reisegruppe:\n" + "\n".join(f"- {b}" for b in blocks)


class ActivitiesAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    async def run_stop(self, stop: dict) -> dict:
        req = self.request
        stop_id = stop.get("id", 1)
        region = stop.get("region", "")
        country = stop.get("country", "")
        nights = stop.get("nights", req.min_nights_per_stop)

        budget_per_stop = req.budget_chf * (req.budget_activities_pct / 100) / max(1, req.total_days) * nights

        # Pre-fetch: echte Sehenswürdigkeiten und Wetter
        lat = stop.get("lat")
        lon = stop.get("lon")
        real_data_block = ""
        weather_block = ""

        if lat and lon:
            gp_results = await search_attractions(lat, lon, radius_m=req.activities_radius_km * 1000)
            if gp_results:
                lines = [f"- {a['name']} | ★{a.get('rating','?')} ({a.get('user_ratings_total',0)} Bewertungen) | {a.get('address','')}" for a in gp_results[:8]]
                real_data_block = "\n\nEchte Sehenswürdigkeiten in der Nähe (Google Places Daten):\n" + "\n".join(lines) + "\nBevorzuge diese echten Orte und ergänze mit deinem Wissen.\n"

            # Wetter für wetterangepasste Empfehlungen
            arrival_day = stop.get("arrival_day", 1)
            start_date = req.start_date
            if hasattr(start_date, "isoformat"):
                from datetime import timedelta
                arr_date = start_date + timedelta(days=arrival_day - 1)
                dep_date = arr_date + timedelta(days=nights)
                weather = await get_forecast(lat, lon, arr_date.isoformat(), dep_date.isoformat())
                if weather:
                    lines = [f"- {w['date']}: {w['description']}, {w['temp_max']}°C/{w['temp_min']}°C, Niederschlag: {w['precipitation_mm']}mm" for w in weather]
                    weather_block = "\n\nWettervorhersage für den Aufenthalt:\n" + "\n".join(lines) + "\nPasse Empfehlungen ans Wetter an (bei Regen: Indoor-Aktivitäten bevorzugen).\n"

        if not real_data_block:
            brave_results = await search_places(f"Sehenswürdigkeiten {region} {country}", count=5)
            if brave_results:
                lines = [f"- {r['name']} ({r.get('rating','?')}★) — {r.get('address','')}" for r in brave_results if r.get("name")]
                if lines:
                    real_data_block = "\n\nEchte Suchergebnisse für Aktivitäten:\n" + "\n".join(lines) + "\nBevorzuge diese echten Orte.\n"

        travelers_desc = _describe_travelers(req)
        style_guidance = _build_style_guidance(req)
        has_children = bool(req.children)

        # Optionale Kontextblöcke
        desc_line = f"\nReisebeschreibung: {req.travel_description}" if req.travel_description else ""
        pref_line = f"\nBevorzugte Aktivitäten: {', '.join(req.preferred_activities)}" if req.preferred_activities else ""
        mandatory_line = f"\nPflichtaktivitäten: {', '.join(a.name for a in req.mandatory_activities)}" if req.mandatory_activities else ""

        # JSON-Schema mit optionalen Kinderfeldern
        children_fields = ""
        if has_children:
            children_fields = """
      "min_age": 4,
      "age_group": "ab 4 Jahre","""

        prompt = f"""Finde die besten Aktivitäten in {region}, {country}:

Reisende: {travelers_desc}
Aufenthalt: {nights} Nächte
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Suchradius: {req.activities_radius_km} km
Max. Aktivitäten: {req.max_activities_per_stop}
Aktivitätenbudget: ca. CHF {budget_per_stop:.0f} für diesen Stopp — nutze das Budget möglichst aus{mandatory_line}{pref_line}{desc_line}{style_guidance}

WICHTIG: Alle Aktivitäten müssen innerhalb des Suchradius von {req.activities_radius_km} km vom Übernachtungsort in {region} liegen. Keine Ausnahmen — empfehle lieber weniger Aktivitäten als solche außerhalb des Radius.

Gib exakt dieses JSON zurück:
{{
  "stop_id": {stop_id},
  "region": "{region}",
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
}}{real_data_block}{weather_block}"""

        await debug_logger.log(
            LogLevel.API, f"→ Anthropic API call: {self.model} (Aktivitäten: {region})",
            job_id=self.job_id, agent="ActivitiesAgent",
        )
        await debug_logger.log_prompt("ActivitiesAgent", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
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

        result["top_activities"] = activities
        return result
