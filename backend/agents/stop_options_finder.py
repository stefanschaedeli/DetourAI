import asyncio
import json
import re
from typing import AsyncIterator

from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from utils.wikipedia import get_city_summary
from agents._client import get_client, get_model, get_max_tokens
from utils.ferry_ports import is_island_destination, validate_island_coordinates

AGENT_KEY = "stop_options_finder"

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner der Zwischenstopps entlang einer konkreten Fahrroute vorschlägt. "
    "KRITISCH — Regeln für das Feld 'region': "
    "Immer eine konkrete Ortschaft (Stadt, Dorf, Kleinstadt) angeben — NIEMALS Regionen, Gebirge, Länder oder Gebiete "
    "(z.B. NICHT 'Toskana', 'Alpen', 'Provence', 'Schwarzwald', sondern 'Siena', 'Annecy', 'Aix-en-Provence', 'Freiburg im Breisgau'). "
    "KRITISCH — Geographie: Vorgeschlagene Stopps müssen ZWISCHEN dem aktuellen Standort und dem Ziel liegen, "
    "nicht hinter dem Ziel oder in eine andere Richtung. Orientiere dich an den Referenzorten entlang der Route. "
    "KRITISCH — Fahrzeiten: Jede Option muss drive_hours ≤ dem angegebenen Maximum einhalten. "
    "Wähle nähere Zwischenstopps wenn nötig — lieber einen kürzeren Etappenstopp als das Limit zu überschreiten. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. Kein Markdown, keine Erklärungen, nur JSON. "
    "STIL-REGEL: Wenn Reisestile angegeben sind, muessen mindestens 2 der 3 Optionen "
    "dem Reisestil entsprechen. Die 3. Option darf ein interessanter Wildcard-Vorschlag sein. "
    "Kennzeichne in jedem Vorschlag: \"matches_travel_style\": true/false. "
)


class StopOptionsFinderAgent:
    def __init__(self, request: TravelRequest, job_id: str):
        self.request = request
        self.job_id = job_id
        self.client = get_client()
        self.model = get_model("claude-sonnet-4-5", AGENT_KEY)

    def _build_prompt(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int,
        segment_count: int,
        extra_instructions: str,
        route_geometry: dict,
    ) -> str:
        req = self.request
        geo = route_geometry or {}
        is_rundreise = geo.get("rundreise_mode", False)

        prev_stop = selected_stops[-1]["region"] if selected_stops else req.start_location

        stops_str = ""
        if selected_stops:
            parts = [
                f"Stop {s['id']}: {s['region']} ({s.get('country','?')}, {s.get('nights',1)} Nächte, {s.get('drive_km','?')} km vom Vorgänger)"
                for s in selected_stops
            ]
            stops_str = "Bisherige Stopps: " + ", ".join(parts) + "\n"

        complete_hint = ""
        if route_could_be_complete:
            complete_hint = (
                f"\nHinweis: Die Route könnte mit diesem Stop abgeschlossen werden "
                f"(Ziel: {segment_target}). Mindestens eine Option sollte direkt zum Ziel führen.\n"
            )

        has_children = bool(req.children)
        family_field = '"family_friendly": true,' if has_children else ""

        extra_hint = ""
        if extra_instructions:
            extra_hint = f"\nSonderwunsch des Nutzers: {extra_instructions}\n"

        # Build geometry context block
        geo_lines = []
        if geo.get("segment_total_km"):
            geo_lines.append(
                f"Gesamtstrecke {prev_stop} → {segment_target}: ~{geo['segment_total_km']:.0f} km / ~{geo.get('segment_total_hours', 0):.1f}h Fahrzeit"
            )
        if geo.get("stops_remaining") is not None:
            geo_lines.append(f"Empfohlene Anzahl weiterer Stopps bis {segment_target}: {geo['stops_remaining']}")
        if geo.get("ideal_km_from_prev"):
            geo_lines.append(
                f"Ideale Distanz dieses Stops vom letzten Stop: ~{geo['ideal_km_from_prev']:.0f} km / ~{geo.get('ideal_hours_from_prev', 0):.1f}h"
                f" (gleichmässig verteilt zwischen Start und Ziel — Stop soll ZWISCHEN den beiden liegen)"
            )
            if not is_rundreise:
                geo_lines.append(
                    f"→ Wähle Orte die ca. {geo['ideal_km_from_prev']:.0f} km von {prev_stop} entfernt liegen, "
                    f"NICHT direkt am Start und NICHT direkt am Ziel."
                )

        # Corridor reference cities for transit mode
        ref_cities = geo.get("corridor_reference_cities", [])
        if ref_cities and not is_rundreise:
            geo_lines.append(
                f"ROUTE-KORRIDOR: Die Fahrroute verläuft durch/nahe: {', '.join(ref_cities)}. "
                f"Suche Stopps in diesem Bereich oder in der unmittelbaren Umgebung dieser Route."
            )

        # Bounding box as hard limit
        box = geo.get("corridor_box")
        if box and not is_rundreise:
            geo_lines.append(
                f"SUCHBEREICH (±30 km entlang der Fahrroute): "
                f"Lat {box['min_lat']:.2f}–{box['max_lat']:.2f}, Lon {box['min_lon']:.2f}–{box['max_lon']:.2f}. "
                f"Alle 3 Optionen MÜSSEN in diesem geographischen Bereich liegen."
            )

        geo_block = "\n".join(geo_lines) + "\n" if geo_lines else ""

        # Bearing context for backtracking prevention (D-10)
        prev_coords = geo.get("_from_coords")
        target_coords = geo.get("_to_coords")
        bearing_block = ""
        if prev_coords and target_coords and not is_rundreise:
            from utils.maps_helper import bearing_degrees
            prev_lat, prev_lon = prev_coords if prev_coords else (None, None)
            target_lat, target_lon = target_coords if target_coords else (None, None)
            if prev_lat and target_lat:
                route_bearing = bearing_degrees((prev_lat, prev_lon), (target_lat, target_lon))
                bearing_block = (
                    f"\nRICHTUNGSKONTEXT: Vom letzten Stopp ({prev_stop}) zum Ziel ({segment_target}) "
                    f"betraegt die Fahrtrichtung ca. {route_bearing:.0f} Grad. "
                    f"WICHTIG: Schlage NUR Orte vor, die grob in dieser Richtung liegen. "
                    f"Keine Rueckwaertsfahrten oder starke Umwege (> 90 Grad Abweichung).\n"
                )

        # Option-type block
        if is_rundreise:
            option_block = (
                f"RUNDREISE-MODUS AKTIV: Wir haben viel Zeit — suche Orte die einen bewussten Umweg "
                f"darstellen, d.h. NICHT auf der direkten Strecke nach {segment_target} liegen, "
                f"sondern interessante Regionen seitlich oder in anderer Richtung erkunden.\n"
                f"Schlage genau 3 verschiedene Optionen vor:\n"
                f'- option_type "umweg_links": Umweg links/westlich der Direktroute\n'
                f'- option_type "umweg_rechts": Umweg rechts/östlich der Direktroute\n'
                f'- option_type "abenteuer": überraschende andere Richtung, maximaler Kontrast zur Direktroute\n'
            )
        else:
            ref_cities = geo.get("corridor_reference_cities", [])
            if ref_cities:
                ref_str = ", ".join(ref_cities)
                option_block = (
                    f"Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor "
                    f"(im Bereich der Route durch {ref_str}):\n"
                    f'- option_type "direct": direkt an der Hauptroute Richtung {segment_target}\n'
                    f'- option_type "scenic": landschaftlich schöne Alternative nahe der Route\n'
                    f'- option_type "cultural": kulturell interessante Alternative nahe der Route\n'
                )
            else:
                option_block = (
                    f"Schlage genau 3 verschiedene Optionen für den nächsten Zwischenstopp vor:\n"
                    f'- option_type "direct": kürzeste Route Richtung {segment_target}\n'
                    f'- option_type "scenic": landschaftlich schöne Alternative\n'
                    f'- option_type "cultural": kulturell interessante Alternative\n'
                )

        # Rules block
        if is_rundreise:
            rules_block = (
                f"PFLICHT — alle 4 Regeln einhalten:\n"
                f"1. drive_hours von {prev_stop} zu diesem Stop: ≤ {req.max_drive_hours_per_day}h\n"
                f"2. Distanz: ~{geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80):.0f} km von {prev_stop}\n"
                f"   (Toleranz ±40% — bewusst größerer Bereich als normal)\n"
                f"3. NICHT zu nahe am Reise-Startpunkt {geo.get('origin_location', req.start_location)}: "
                f"min {geo.get('min_km_from_origin', 0):.0f} km Luftlinie\n"
                f"4. Gehe BEWUSST NICHT Richtung {segment_target} — wähle Orte seitlich oder entgegengesetzt\n"
            )
        else:
            rules_block = (
                f"PFLICHT — alle 7 Regeln einhalten:\n"
                f"1. drive_hours von {prev_stop} zu diesem Stop: ≤ {req.max_drive_hours_per_day}h\n"
                f"2. Distanz: ~{geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80):.0f} km von {prev_stop}\n"
                f"   (Toleranz ±30%; NICHT unter {geo.get('ideal_km_from_prev', req.max_drive_hours_per_day * 80) * 0.5:.0f} km — zu nahe am letzten Stop)\n"
                f"3. NICHT zu nahe am Reise-Startpunkt {geo.get('origin_location', req.start_location)}: min {geo.get('min_km_from_origin', 0):.0f} km Luftlinie\n"
                f"4. NICHT zu nahe am Ziel {segment_target}: min {geo.get('min_km_from_target', 0):.0f} km Luftlinie\n"
                f"5. Teile lange Strecken auf — niemals direkt zum Ziel springen wenn noch {geo.get('stops_remaining', 1)} Etappe(n) geplant sind\n"
                f"6. RICHTUNG: Der Stop muss geographisch ZWISCHEN {prev_stop} und {segment_target} liegen — "
                f"NICHT hinter dem Ziel und NICHT in die entgegengesetzte Richtung. "
                f"Nutze die Route-Referenzorte als Orientierung.\n"
                f"7. SUCHBEREICH: Wenn ein geographischer Suchbereich (Lat/Lon) angegeben ist, "
                f"müssen alle Optionen innerhalb dieses Bereichs liegen. "
                f"Prüfe die lat/lon-Koordinaten deiner Vorschläge gegen den angegebenen Bereich.\n"
            )

        # Travel style emphasis (D-05)
        style_emphasis = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            style_emphasis = (
                f"\nREISESTIL-PRAEFERENZ: Der Nutzer bevorzugt \"{styles_str}\". "
                f"Mindestens 2 von 3 Optionen muessen diesem Stil entsprechen. "
                f"Die 3. Option darf ein ueberraschender Geheimtipp sein.\n"
            )

        # JSON example option_types
        if is_rundreise:
            ex1_type = "umweg_links"
            ex2_type = "umweg_rechts"
            ex3_type = "abenteuer"
        else:
            ex1_type = "direct"
            ex2_type = "scenic"
            ex3_type = "cultural"

        return f"""Segment {segment_index + 1} von {segment_count} Richtung: {segment_target}

Start der Gesamtreise: {req.start_location}
Letzter Stop (Abfahrtspunkt): {prev_stop}
Endziel dieses Segments: {segment_target}
Aktueller Stop #{stop_number}
{stops_str}
{geo_block}{bearing_block}Verbleibende Tage im Segment: {days_remaining}
Maximale Fahrzeit pro Etappe: {req.max_drive_hours_per_day}h
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
Reisende: {req.adults} Erwachsene{', ' + str(len(req.children)) + ' Kinder (Alter: ' + ', '.join(str(c) for c in req.children) + ')' if req.children else ''}
{complete_hint}{extra_hint}
{option_block}{style_emphasis}
{rules_block}Nächte: {req.min_nights_per_stop}–{req.max_nights_per_stop}.

Befülle folgende Felder kontextabhängig:
- population: Einwohnerzahl als lesbarer String (z.B. "45'000 Einwohner"), falls bekannt
- altitude_m: Meereshöhe in Metern, besonders relevant für Bergregionen
- language: Hauptsprache der Region
- climate_note: Klimahinweis passend zur Reisezeit ({getattr(req, 'start_date', 'unbekannt')})
- must_see: Top 2-3 Sehenswürdigkeiten passend zu den Reisestilen {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
{('- family_friendly: true/false (Kinder reisen mit)' if has_children else '')}
- teaser: WICHTIG — 3-4 Sätze (~100-150 Wörter). Erkläre WARUM dieser Stopp perfekt zur Reise passt.
  Beziehe dich konkret auf die Reisestile ({', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}),
  die Reisenden ({req.adults} Erwachsene{', Kinder' if req.children else ''}) und was diesen Ort besonders macht.
  Keine generischen Floskeln — überzeugend und spezifisch begründen.

Gib exakt dieses JSON zurück. lat/lon = WGS84-Koordinaten des Stadtzentrums (PFLICHT – keine null):
{{
  "options": [
    {{"id": 1, "option_type": "{ex1_type}", "region": "...", "country": "FR", "lat": 45.7640, "lon": 4.8357, "drive_hours": 3.5, "drive_km": 280, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 2, "option_type": "{ex2_type}", "region": "...", "country": "FR", "lat": 45.9237, "lon": 6.8694, "drive_hours": 4.0, "drive_km": 320, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": 1200, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true{', ' + family_field[:-1] if family_field else ''}}},
    {{"id": 3, "option_type": "{ex3_type}", "region": "...", "country": "FR", "lat": 43.2965, "lon": 5.3698, "drive_hours": 3.0, "drive_km": 250, "nights": 2, "highlights": ["...", "..."], "teaser": "Ausführliche Begründung in 3-4 Sätzen warum dieser Stop perfekt zur Reise passt, mit Bezug auf Reisestile und Reisende...", "population": "...", "altitude_m": null, "language": "Französisch", "climate_note": "...", "must_see": ["...", "..."], "matches_travel_style": true{', ' + family_field[:-1] if family_field else ''}}}
  ],
  "estimated_total_stops": 4,
  "route_could_be_complete": false
}}"""

    async def find_options(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int = 0,
        segment_count: int = 1,
        extra_instructions: str = "",
        route_geometry: dict = None,
    ) -> dict:
        prompt = self._build_prompt(
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=days_remaining,
            route_could_be_complete=route_could_be_complete,
            segment_target=segment_target,
            segment_index=segment_index,
            segment_count=segment_count,
            extra_instructions=extra_instructions,
            route_geometry=route_geometry,
        )

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")
        await debug_logger.log_prompt("StopOptionsFinder", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2500),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="StopOptionsFinder")
        text = response.content[0].text
        # Return Claude's result immediately — drive_hours/drive_km are placeholders.
        # Authoritative Google Directions enrichment runs in main.py after this call.
        result = parse_agent_json(text)

        # Wikipedia-Anreicherung: echte Beschreibungen und Einwohnerzahlen
        for option in result.get("options", []):
            region = option.get("region", "")
            if region:
                wiki = await get_city_summary(region)
                if wiki:
                    if wiki.get("extract"):
                        option.setdefault("description", wiki["extract"][:200])
                    if wiki.get("thumbnail_url"):
                        option["wikipedia_image"] = wiki["thumbnail_url"]

            # Island coordinate validation (D-10, GEO-02)
            opt_lat = option.get("lat")
            opt_lon = option.get("lon")
            if opt_lat is not None and opt_lon is not None:
                coords = (opt_lat, opt_lon)
                island_group = is_island_destination(coords)
                if island_group:
                    if not validate_island_coordinates(region, coords, island_group):
                        await debug_logger.log(
                            LogLevel.WARNING,
                            f"Insel-Koordinaten-Validierung fehlgeschlagen: {region} "
                            f"({coords[0]:.4f}, {coords[1]:.4f}) nicht in {island_group} bbox",
                            job_id=self.job_id, agent="StopOptionsFinder",
                        )
                        # Coordinates resolved to mainland instead of island -- flag for review
                        # but do not discard (graceful degradation)

        return result

    async def find_options_streaming(
        self,
        selected_stops: list,
        stop_number: int,
        days_remaining: int,
        route_could_be_complete: bool,
        segment_target: str,
        segment_index: int = 0,
        segment_count: int = 1,
        extra_instructions: str = "",
        route_geometry: dict = None,
    ) -> AsyncIterator[dict]:
        """
        Calls Claude with streaming and yields individual option dicts as soon
        as each complete JSON object becomes detectable in the stream.
        Also yields a final dict {"_all_options": [...], "estimated_total_stops": int,
        "route_could_be_complete": bool} once the full response is parsed.
        """
        prompt = self._build_prompt(
            selected_stops=selected_stops,
            stop_number=stop_number,
            days_remaining=days_remaining,
            route_could_be_complete=route_could_be_complete,
            segment_target=segment_target,
            segment_index=segment_index,
            segment_count=segment_count,
            extra_instructions=extra_instructions,
            route_geometry=route_geometry,
        )

        await debug_logger.log(LogLevel.API, f"→ Anthropic API stream: {self.model}", job_id=self.job_id, agent="StopOptionsFinder")

        accumulated = ""
        emitted_count = 0

        def _extract_next_option(text: str, already_emitted: int):
            """Find the next complete option object in the accumulated JSON text."""
            # Locate the "options" array
            arr_match = re.search(r'"options"\s*:\s*\[', text)
            if not arr_match:
                return None, already_emitted
            arr_start = arr_match.end()
            # Find each complete {...} block after arr_start
            depth = 0
            obj_start = None
            count = 0
            i = arr_start
            while i < len(text):
                ch = text[i]
                if ch == '{':
                    if depth == 0:
                        obj_start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and obj_start is not None:
                        count += 1
                        if count > already_emitted:
                            try:
                                obj = json.loads(text[obj_start:i + 1])
                                return obj, count
                            except json.JSONDecodeError:
                                pass
                i += 1
            return None, already_emitted

        def _do_stream():
            nonlocal accumulated, emitted_count
            results = []
            with self.client.messages.stream(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2500),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text_chunk in stream.text_stream:
                    accumulated += text_chunk
                    opt, new_count = _extract_next_option(accumulated, emitted_count)
                    if opt is not None:
                        emitted_count = new_count
                        results.append(("option", opt))
                full_text = stream.get_final_text()
            return results, full_text

        import time as _time
        t0 = _time.monotonic()
        try:
            partial_results, final_text = await asyncio.to_thread(_do_stream)
        except Exception as exc:
            import traceback
            await debug_logger.log(
                LogLevel.ERROR,
                f"Stream-Fehler: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                job_id=self.job_id, agent="StopOptionsFinder",
            )
            raise
        elapsed = _time.monotonic() - t0

        await debug_logger.log(
            LogLevel.SUCCESS,
            f"← Stream fertig in {elapsed:.1f}s — {len(partial_results)} Option(en) im Stream erkannt",
            job_id=self.job_id, agent="StopOptionsFinder",
        )

        for kind, payload in partial_results:
            if kind == "option":
                yield payload

        # Parse the complete response for metadata + any options not yet emitted
        try:
            full_parsed = parse_agent_json(final_text)
        except (ValueError, json.JSONDecodeError) as exc:
            await debug_logger.log(
                LogLevel.WARNING,
                f"JSON-Antwort abgeschnitten, verwende {emitted_count} im Stream erkannte Optionen. Fehler: {exc}",
                job_id=self.job_id, agent="StopOptionsFinder",
            )
            # Fall back to streamed options — already yielded above
            yield {
                "_all_options": [p for k, p in partial_results if k == "option"],
                "estimated_total_stops": 4,
                "route_could_be_complete": False,
            }
            return

        all_options = full_parsed.get("options", [])
        # Emit any options that weren't caught during streaming (edge cases)
        for opt in all_options[emitted_count:]:
            yield opt

        # Final sentinel with complete metadata
        yield {
            "_all_options": all_options,
            "estimated_total_stops": full_parsed.get("estimated_total_stops", 4),
            "route_could_be_complete": full_parsed.get("route_could_be_complete", False),
        }

