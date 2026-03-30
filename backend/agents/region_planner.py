from __future__ import annotations
from typing import Optional
from models.travel_request import TravelRequest
from models.trip_leg import RegionPlan, RegionPlanItem, TripLeg
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.maps_helper import geocode_google, haversine_km
from agents._client import get_client, get_model, get_max_tokens

AGENT_KEY = "region_planner"

SYSTEM_PROMPTS = {
    "de": (
        "Du bist ein Reiserouten-Stratege. Plane eine Rundreise durch Regionen basierend auf der "
        "Beschreibung des Reisenden. Ordne Regionen in einer logistisch sinnvollen Reihenfolge "
        "(minimale Rückwege, geografische Effizienz). Jede Region soll ein Gebiet repräsentieren, "
        "in dem der Reisende konkrete Stopps machen kann.\n"
        "WICHTIG zur Reihenfolge: Die Regionen müssen eine geographisch logische Route bilden — "
        "KEINE Zickzack-Muster! Die Route soll vom Startort aus in eine Richtung verlaufen und "
        "nicht unnötig hin- und herspringen. Bei Rundreisen: im Uhrzeigersinn oder gegen den "
        "Uhrzeigersinn, aber niemals kreuz und quer.\n"
        "Für jede Region liefere:\n"
        "- name: Name der Region\n"
        "- lat/lon: Zentrale Koordinaten der Region\n"
        "- reason: Warum diese Region zur Reise passt (1 Satz)\n"
        "- teaser: Kurzer, einladender Satz der die Region beschreibt und Lust auf den Besuch macht\n"
        "- highlights: 3-5 konkrete Sehenswürdigkeiten, Aktivitäten oder Besonderheiten der Region\n\n"
        "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON."
    ),
    "en": (
        "You are a travel route strategist. Plan a round trip through regions based on the "
        "traveler's description. Arrange regions in a logistically sensible order "
        "(minimal backtracking, geographic efficiency). Each region should represent an area "
        "where the traveler can make specific stops.\n"
        "IMPORTANT regarding order: The regions must form a geographically logical route — "
        "NO zigzag patterns! The route should proceed from the starting point in one direction "
        "and not jump back and forth unnecessarily. For round trips: clockwise or counter-clockwise, "
        "but never crisscross.\n"
        "For each region provide:\n"
        "- name: Name of the region\n"
        "- lat/lon: Central coordinates of the region\n"
        "- reason: Why this region fits the trip (1 sentence)\n"
        "- teaser: Short, inviting sentence describing the region and making you want to visit\n"
        "- highlights: 3-5 specific sights, activities, or special features of the region\n\n"
        "Reply ONLY with a valid JSON object. No markdown, no explanations, only JSON."
    ),
    "hi": (
        "आप एक यात्रा मार्ग रणनीतिकार हैं। यात्री के विवरण के आधार पर क्षेत्रों के माध्यम से "
        "एक दौरे की योजना बनाएं। क्षेत्रों को तार्किक क्रम में व्यवस्थित करें "
        "(न्यूनतम वापसी, भौगोलिक दक्षता)। प्रत्येक क्षेत्र एक ऐसा क्षेत्र होना चाहिए "
        "जहां यात्री विशिष्ट स्टॉप बना सकें।\n"
        "महत्वपूर्ण: क्षेत्रों को भौगोलिक रूप से तार्किक मार्ग बनाना चाहिए — "
        "कोई ज़िगज़ैग पैटर्न नहीं! मार्ग प्रारंभ स्थान से एक दिशा में आगे बढ़ना चाहिए। "
        "गोलाकार यात्राओं के लिए: दक्षिणावर्त या वामावर्त, लेकिन कभी भी आड़ा-तिरछा नहीं।\n"
        "प्रत्येक क्षेत्र के लिए प्रदान करें:\n"
        "- name: क्षेत्र का नाम\n"
        "- lat/lon: क्षेत्र के केंद्रीय निर्देशांक\n"
        "- reason: यह क्षेत्र यात्रा के लिए क्यों उपयुक्त है (1 वाक्य)\n"
        "- teaser: क्षेत्र का वर्णन करने वाला छोटा, आमंत्रित वाक्य\n"
        "- highlights: क्षेत्र के 3-5 विशिष्ट दर्शनीय स्थल, गतिविधियां या विशेषताएं\n\n"
        "केवल एक वैध JSON ऑब्जेक्ट के साथ उत्तर दें। कोई मार्कडाउन नहीं, कोई व्याख्या नहीं, केवल JSON।"
    ),
}

_REGION_SCHEMAS = {
    "de": """{
  "regions": [
    {
      "name": "Regionsname",
      "lat": 0.0,
      "lon": 0.0,
      "reason": "Warum diese Region zur Reise passt",
      "teaser": "Ein Satz der die Region beschreibt und Lust macht",
      "highlights": ["Sehenswürdigkeit 1", "Aktivität 2", "Besonderheit 3"]
    }
  ],
  "summary": "Zusammenfassung der Rundreise"
}""",
    "en": """{
  "regions": [
    {
      "name": "Region name",
      "lat": 0.0,
      "lon": 0.0,
      "reason": "Why this region fits the trip",
      "teaser": "One sentence describing the region and making you want to visit",
      "highlights": ["Sight 1", "Activity 2", "Special feature 3"]
    }
  ],
  "summary": "Summary of the round trip"
}""",
    "hi": """{
  "regions": [
    {
      "name": "क्षेत्र का नाम",
      "lat": 0.0,
      "lon": 0.0,
      "reason": "यह क्षेत्र यात्रा के लिए क्यों उपयुक्त है",
      "teaser": "क्षेत्र का वर्णन करने वाला एक वाक्य",
      "highlights": ["दर्शनीय स्थल 1", "गतिविधि 2", "विशेषता 3"]
    }
  ],
  "summary": "दौरे का सारांश"
}""",
}
# Keep backward compat
REGION_SCHEMA = _REGION_SCHEMAS["de"]


def _reorder_regions(
    regions: list[RegionPlanItem],
    start_coords: tuple[float, float],
    end_coords: tuple[float, float] | None,
    circular: bool,
) -> list[RegionPlanItem]:
    """Reorder regions using nearest-neighbor heuristic + 2-opt improvement.

    Pure function — no I/O, no geocoding. Testable without mocks.
    """
    n = len(regions)
    if n <= 2:
        return regions

    coords = [(r.lat, r.lon) for r in regions]

    # Find anchor: region nearest to start
    start_idx = min(range(n), key=lambda i: haversine_km(start_coords, coords[i]))

    if not circular and end_coords:
        # One-way: reserve the region nearest to end_coords
        end_idx = min(range(n), key=lambda i: haversine_km(end_coords, coords[i]))
        if end_idx == start_idx:
            # Same region nearest to both — pick second-nearest for end
            candidates = sorted(range(n), key=lambda i: haversine_km(end_coords, coords[i]))
            end_idx = candidates[1] if len(candidates) > 1 else candidates[0]
    else:
        end_idx = None

    # Nearest-neighbor from start_idx
    visited = [start_idx]
    remaining = set(range(n)) - {start_idx}
    if end_idx is not None:
        remaining.discard(end_idx)

    current = start_idx
    while remaining:
        nearest = min(remaining, key=lambda i: haversine_km(coords[current], coords[i]))
        visited.append(nearest)
        remaining.discard(nearest)
        current = nearest

    if end_idx is not None:
        visited.append(end_idx)

    # 2-opt improvement pass
    def total_dist(order: list[int]) -> float:
        d = haversine_km(start_coords, coords[order[0]])
        for i in range(len(order) - 1):
            d += haversine_km(coords[order[i]], coords[order[i + 1]])
        if circular:
            d += haversine_km(coords[order[-1]], start_coords)
        elif end_coords:
            d += haversine_km(coords[order[-1]], end_coords)
        return d

    improved = True
    while improved:
        improved = False
        # Keep first fixed (start anchor); keep last fixed if one-way
        lo = 1
        hi = len(visited) - 1 if end_idx is not None else len(visited)
        for i in range(lo, hi - 1):
            for j in range(i + 1, hi):
                new_order = visited[:i] + visited[i:j + 1][::-1] + visited[j + 1:]
                if total_dist(new_order) < total_dist(visited):
                    visited = new_order
                    improved = True

    return [regions[i] for i in visited]


class RegionPlannerAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    def _get_lang(self) -> str:
        return getattr(self.request, 'language', 'de')

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        lang = self._get_lang()
        leg = req.legs[leg_index]

        _L = {
            "de": {"start": "Startort", "end": "Endort", "days": "Verfügbare Tage",
                   "max_drive": "Max. Fahrzeit/Tag", "styles": "Reisestile",
                   "no_style": "keine Angabe", "travelers": "Reisende",
                   "adults": "Erwachsene", "children": "Kinder",
                   "desc": "Reisebeschreibung", "pref": "Bevorzugte Aktivitäten",
                   "mandatory": "Pflichtaktivitäten"},
            "en": {"start": "Start location", "end": "End location", "days": "Available days",
                   "max_drive": "Max. drive time/day", "styles": "Travel styles",
                   "no_style": "not specified", "travelers": "Travelers",
                   "adults": "adults", "children": "children",
                   "desc": "Travel description", "pref": "Preferred activities",
                   "mandatory": "Mandatory activities"},
            "hi": {"start": "प्रारंभ स्थान", "end": "अंतिम स्थान", "days": "उपलब्ध दिन",
                   "max_drive": "अधिकतम ड्राइव समय/दिन", "styles": "यात्रा शैलियां",
                   "no_style": "निर्दिष्ट नहीं", "travelers": "यात्रीगण",
                   "adults": "वयस्क", "children": "बच्चे",
                   "desc": "यात्रा विवरण", "pref": "पसंदीदा गतिविधियां",
                   "mandatory": "अनिवार्य गतिविधियां"},
        }
        L = _L.get(lang, _L["de"])

        styles = ", ".join(req.travel_styles) if req.travel_styles else L["no_style"]
        lines = []
        if leg.start_location:
            lines.append(f"{L['start']}: {leg.start_location}")
        if leg.end_location:
            lines.append(f"{L['end']}: {leg.end_location}")
        lines.append(f"{L['days']}: {leg.total_days}")
        lines.append(f"{L['max_drive']}: {req.max_drive_hours_per_day}h")
        lines.append(f"{L['styles']}: {styles}")
        travellers = f"{L['travelers']}: {req.adults} {L['adults']}"
        if req.children:
            travellers += f", {L['children']}: {len(req.children)}"
        lines.append(travellers)
        if req.travel_description:
            lines.append(f"{L['desc']}: {req.travel_description}")
        if req.preferred_activities:
            lines.append(f"{L['pref']}: {', '.join(req.preferred_activities)}")
        if req.mandatory_activities:
            acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
            lines.append(f"{L['mandatory']}: {', '.join(acts)}")
        return "\n".join(lines)

    async def _extract_json(self, response) -> dict:
        """Extract JSON from response, warning on truncation."""
        if response.stop_reason == "max_tokens":
            await debug_logger.log(
                LogLevel.WARNING,
                "RegionPlannerAgent Antwort wurde abgeschnitten (max_tokens erreicht)",
                job_id=self.job_id, agent="RegionPlannerAgent",
            )
        text = response.content[0].text
        return parse_agent_json(text)

    async def _optimize_route_order(
        self, regions: list[RegionPlanItem], leg: TripLeg,
    ) -> list[RegionPlanItem]:
        """Reorder regions for geographic efficiency using nearest-neighbor + 2-opt."""
        if len(regions) <= 2:
            return regions

        if not leg.start_location:
            return regions

        start_geo = await geocode_google(leg.start_location)
        if not start_geo:
            await debug_logger.log(
                LogLevel.WARNING,
                f"Geocoding fehlgeschlagen für '{leg.start_location}' — Route nicht optimiert",
                job_id=self.job_id, agent="RegionPlannerAgent",
            )
            return regions

        start_coords = (start_geo[0], start_geo[1])
        circular = not leg.end_location or leg.end_location == leg.start_location
        end_coords = None

        if not circular:
            end_geo = await geocode_google(leg.end_location)
            if end_geo:
                end_coords = (end_geo[0], end_geo[1])
            else:
                await debug_logger.log(
                    LogLevel.WARNING,
                    f"Geocoding fehlgeschlagen für '{leg.end_location}' — behandle als Rundreise",
                    job_id=self.job_id, agent="RegionPlannerAgent",
                )
                circular = True

        original_names = [r.name for r in regions]
        optimized = _reorder_regions(regions, start_coords, end_coords, circular)
        optimized_names = [r.name for r in optimized]

        if original_names != optimized_names:
            await debug_logger.log(
                LogLevel.INFO,
                f"Route optimiert: {' → '.join(original_names)} => {' → '.join(optimized_names)}",
                job_id=self.job_id, agent="RegionPlannerAgent",
            )

        return optimized

    async def _build_plan(self, response, leg_index: int) -> RegionPlan:
        """Extract JSON, build RegionPlan, and optimize route order."""
        data = await self._extract_json(response)
        plan = RegionPlan(**data)
        leg = self.request.legs[leg_index]
        plan.regions = await self._optimize_route_order(plan.regions, leg)
        return plan

    async def plan(self, description: str, leg_index: int) -> RegionPlan:
        lang = self._get_lang()
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        region_schema = _REGION_SCHEMAS.get(lang, _REGION_SCHEMAS["de"])
        context = self._leg_context(leg_index)
        leg = self.request.legs[leg_index]
        end_loc = leg.end_location or leg.start_location

        _L = {
            "de": {
                "desc_header": "Beschreibung des Reisenden:",
                "create": "Erstelle einen Regionen-Plan: eine geordnete Liste von Regionen, die der Reisende auf einer Rundreise besuchen soll.",
                "each_region": "Jede Region = ein Gebiet mit mehreren möglichen Stopps",
                "order": "Logistisch sinnvolle Reihenfolge (minimale Rückwege)",
                "count": "Anzahl Regionen passend zur verfügbaren Zeit",
                "important": "WICHTIG: Die Route startet bei {s} und endet bei {e}. Ordne die Regionen geographisch logisch von dort aus — keine Zickzack-Muster!",
                "format": "Antwortformat:",
            },
            "en": {
                "desc_header": "Traveler's description:",
                "create": "Create a region plan: an ordered list of regions the traveler should visit on a round trip.",
                "each_region": "Each region = an area with multiple possible stops",
                "order": "Logistically sensible order (minimal backtracking)",
                "count": "Number of regions appropriate for the available time",
                "important": "IMPORTANT: The route starts at {s} and ends at {e}. Arrange the regions geographically logically from there — no zigzag patterns!",
                "format": "Response format:",
            },
            "hi": {
                "desc_header": "यात्री का विवरण:",
                "create": "एक क्षेत्र योजना बनाएं: क्षेत्रों की एक क्रमबद्ध सूची जिन्हें यात्री को दौरे पर जाना चाहिए।",
                "each_region": "प्रत्येक क्षेत्र = कई संभावित स्टॉप वाला एक क्षेत्र",
                "order": "तार्किक रूप से समझदार क्रम (न्यूनतम वापसी)",
                "count": "उपलब्ध समय के अनुसार क्षेत्रों की संख्या",
                "important": "महत्वपूर्ण: मार्ग {s} से शुरू होता है और {e} पर समाप्त होता है। क्षेत्रों को वहां से भौगोलिक रूप से तार्किक रूप से व्यवस्थित करें — कोई ज़िगज़ैग पैटर्न नहीं!",
                "format": "उत्तर प्रारूप:",
            },
        }
        L = _L.get(lang, _L["de"])

        prompt = (
            f"{context}\n\n"
            f"{L['desc_header']}\n{description}\n\n"
            f"{L['create']}\n"
            f"- {L['each_region']}\n"
            f"- {L['order']}\n"
            f"- {L['count']}\n"
            f"- {L['important'].format(s=leg.start_location, e=end_loc)}\n\n"
            f"{L['format']}\n{region_schema}"
        )

        await debug_logger.log(
            LogLevel.API, f"→ RegionPlannerAgent (Plan) {description[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)

    async def replace_region(
        self, index: int, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        lang = self._get_lang()
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        region_schema = _REGION_SCHEMAS.get(lang, _REGION_SCHEMAS["de"])
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        _L = {
            "de": {
                "current": "Aktueller Regionen-Plan:",
                "wants_replace": "Der Reisende möchte Region {n} ({name}) ersetzen:",
                "create_updated": "Erstelle den aktualisierten Plan. Ersetze NUR Region {n}, behalte alle anderen Regionen bei. Passe die Reihenfolge an falls nötig.",
                "format": "Antwortformat:",
            },
            "en": {
                "current": "Current region plan:",
                "wants_replace": "The traveler wants to replace region {n} ({name}):",
                "create_updated": "Create the updated plan. Replace ONLY region {n}, keep all other regions. Adjust the order if necessary.",
                "format": "Response format:",
            },
            "hi": {
                "current": "वर्तमान क्षेत्र योजना:",
                "wants_replace": "यात्री क्षेत्र {n} ({name}) को बदलना चाहता है:",
                "create_updated": "अद्यतन योजना बनाएं। केवल क्षेत्र {n} को बदलें, अन्य सभी क्षेत्रों को रखें। आवश्यकतानुसार क्रम समायोजित करें।",
                "format": "उत्तर प्रारूप:",
            },
        }
        L = _L.get(lang, _L["de"])

        prompt = (
            f"{context}\n\n"
            f"{L['current']}\n{regions_str}\n\n"
            f"{L['wants_replace'].format(n=index+1, name=current_plan.regions[index].name)}\n"
            f'"{instruction}"\n\n'
            f"{L['create_updated'].format(n=index+1)}\n\n"
            f"{L['format']}\n{region_schema}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Ersetzen #{index+1}) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)

    async def recalculate(
        self, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        lang = self._get_lang()
        system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["de"])
        region_schema = _REGION_SCHEMAS.get(lang, _REGION_SCHEMAS["de"])
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        _L = {
            "de": {
                "previous": "Bisheriger Regionen-Plan:",
                "summary": "Zusammenfassung",
                "correction": "Korrektur des Reisenden:",
                "create_new": "Erstelle einen komplett neuen Regionen-Plan unter Berücksichtigung der Korrektur. Der bisherige Plan dient als Kontext.",
                "format": "Antwortformat:",
            },
            "en": {
                "previous": "Previous region plan:",
                "summary": "Summary",
                "correction": "Traveler's correction:",
                "create_new": "Create a completely new region plan taking the correction into account. The previous plan serves as context.",
                "format": "Response format:",
            },
            "hi": {
                "previous": "पिछली क्षेत्र योजना:",
                "summary": "सारांश",
                "correction": "यात्री का सुधार:",
                "create_new": "सुधार को ध्यान में रखते हुए एक पूरी तरह से नई क्षेत्र योजना बनाएं। पिछली योजना संदर्भ के रूप में कार्य करती है।",
                "format": "उत्तर प्रारूप:",
            },
        }
        L = _L.get(lang, _L["de"])

        prompt = (
            f"{context}\n\n"
            f"{L['previous']}\n{regions_str}\n"
            f"{L['summary']}: {current_plan.summary}\n\n"
            f"{L['correction']}\n\"{instruction}\"\n\n"
            f"{L['create_new']}\n\n"
            f"{L['format']}\n{region_schema}"
        )

        await debug_logger.log(
            LogLevel.API,
            f"→ RegionPlannerAgent (Neu berechnen) {instruction[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)
