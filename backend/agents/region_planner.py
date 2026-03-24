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

SYSTEM_PROMPT = (
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
)

REGION_SCHEMA = """{
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
}"""


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

    def _leg_context(self, leg_index: int) -> str:
        req = self.request
        leg = req.legs[leg_index]
        styles = ", ".join(req.travel_styles) if req.travel_styles else "keine Angabe"
        lines = []
        if leg.start_location:
            lines.append(f"Startort: {leg.start_location}")
        if leg.end_location:
            lines.append(f"Endort: {leg.end_location}")
        lines.append(f"Verfügbare Tage: {leg.total_days}")
        lines.append(f"Max. Fahrzeit/Tag: {req.max_drive_hours_per_day}h")
        lines.append(f"Reisestile: {styles}")
        travellers = f"Reisende: {req.adults} Erwachsene"
        if req.children:
            travellers += f", Kinder: {len(req.children)}"
        lines.append(travellers)
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
        context = self._leg_context(leg_index)
        leg = self.request.legs[leg_index]
        end_loc = leg.end_location or leg.start_location

        prompt = (
            f"{context}\n\n"
            f"Beschreibung des Reisenden:\n{description}\n\n"
            f"Erstelle einen Regionen-Plan: eine geordnete Liste von Regionen, "
            f"die der Reisende auf einer Rundreise besuchen soll.\n"
            f"- Jede Region = ein Gebiet mit mehreren möglichen Stopps\n"
            f"- Logistisch sinnvolle Reihenfolge (minimale Rückwege)\n"
            f"- Anzahl Regionen passend zur verfügbaren Zeit\n"
            f"- WICHTIG: Die Route startet bei {leg.start_location} und endet bei {end_loc}. "
            f"Ordne die Regionen geographisch logisch von dort aus — keine Zickzack-Muster!\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
        )

        await debug_logger.log(
            LogLevel.API, f"→ RegionPlannerAgent (Plan) {description[:50]}",
            job_id=self.job_id, agent="RegionPlannerAgent",
        )

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 4096),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)

    async def replace_region(
        self, index: int, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Aktueller Regionen-Plan:\n{regions_str}\n\n"
            f"Der Reisende möchte Region {index+1} ({current_plan.regions[index].name}) ersetzen:\n"
            f'"{instruction}"\n\n'
            f"Erstelle den aktualisierten Plan. Ersetze NUR Region {index+1}, "
            f"behalte alle anderen Regionen bei. Passe die Reihenfolge an falls nötig.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
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
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)

    async def recalculate(
        self, instruction: str,
        current_plan: RegionPlan, leg_index: int,
    ) -> RegionPlan:
        context = self._leg_context(leg_index)
        regions_str = "\n".join(
            f"{i+1}. {r.name} — {r.reason}" for i, r in enumerate(current_plan.regions)
        )

        prompt = (
            f"{context}\n\n"
            f"Bisheriger Regionen-Plan:\n{regions_str}\n"
            f"Zusammenfassung: {current_plan.summary}\n\n"
            f"Korrektur des Reisenden:\n\"{instruction}\"\n\n"
            f"Erstelle einen komplett neuen Regionen-Plan unter Berücksichtigung "
            f"der Korrektur. Der bisherige Plan dient als Kontext.\n\n"
            f"Antwortformat:\n{REGION_SCHEMA}"
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
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RegionPlannerAgent",
                                         token_accumulator=self.token_accumulator)
        return await self._build_plan(response, leg_index)
