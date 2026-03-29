from models.travel_request import TravelRequest
from utils.debug_logger import debug_logger, LogLevel
from utils.retry_helper import call_with_retry
from utils.json_parser import parse_agent_json
from agents._client import get_client, get_model, get_max_tokens
from utils.ferry_ports import is_island_destination, get_ferry_ports, ISLAND_GROUPS
from utils.maps_helper import geocode_google

AGENT_KEY = "route_architect"

SYSTEM_PROMPT = (
    "Du bist ein Reiseplaner für Familien. "
    "Du pruefst die Plausibilitaet von Reisewuenschen und planst optimale Routen. "
    "Antworte AUSSCHLIESSLICH als valides JSON-Objekt. "
    "Kein Markdown, keine Erklärungen, nur JSON."
)


class RouteArchitectAgent:
    def __init__(self, request: TravelRequest, job_id: str, token_accumulator: list = None):
        self.request = request
        self.job_id = job_id
        self.token_accumulator = token_accumulator
        self.client = get_client()
        self.model = get_model("claude-opus-4-5", AGENT_KEY)

    async def run(self) -> dict:
        await debug_logger.log(
            LogLevel.AGENT, "RouteArchitect startet",
            job_id=self.job_id, agent="RouteArchitect",
        )

        req = self.request
        children_ages = [c.age for c in req.children]
        via_str = ""
        if req.via_points:
            parts = []
            for vp in req.via_points:
                s = vp.location
                if vp.fixed_date:
                    s += f" (Fixdatum: {vp.fixed_date})"
                if vp.notes:
                    s += f" [{vp.notes}]"
                parts.append(s)
            via_str = f"Via-Punkte: {', '.join(parts)}\n"

        mandatory_str = ""
        if req.mandatory_activities:
            acts = [f"{a.name}" + (f" ({a.location})" if a.location else "") for a in req.mandatory_activities]
            mandatory_str = f"Pflichtaktivitäten: {', '.join(acts)}\n"

        pref_str = f"Bevorzugte Aktivitäten: {', '.join(req.preferred_activities)}\n" if req.preferred_activities else ""

        # Travel style routing block (D-06)
        style_block = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            style_block = (
                f"\nROUTENPLANUNG NACH REISESTIL: Die Route soll durch Regionen fuehren, die zum "
                f"Reisestil \"{styles_str}\" passen. Beispiel: Bei \"Strand\" -> Kuestenroute bevorzugen. "
                f"Bei \"Kultur\" -> Route durch historisch bedeutsame Regionen. "
                f"Bei \"Berge\" -> Alpenuebergaenge und Bergregionen. "
                f"Bei \"Natur\" -> Nationalparks und Naturschutzgebiete.\n"
            )

        # Plausibility check block (D-11, D-12)
        plausibility_block = ""
        if req.travel_styles:
            styles_str = ", ".join(req.travel_styles)
            plausibility_block = (
                f"\nPLAUSIBILITAETSPRUEFUNG: Pruefe ob die angegebenen Reisestile ({styles_str}) "
                f"geographisch zum Zielgebiet ({req.main_destination}) passen. Wenn ein Reisestil "
                f"im Zielgebiet nicht umsetzbar ist (z.B. \"Vulkane\" in Frankreich, \"Strand\" in den Alpen), "
                f"fuege ein \"plausibility_warning\" Feld zum JSON hinzu mit:\n"
                f"- \"warning\": Erklaerung auf Deutsch warum der Stil nicht zum Ziel passt\n"
                f"- \"suggestions\": Liste von 2-3 alternativen Reisestilen die besser passen\n"
                f"Wenn alle Stile zum Ziel passen, KEIN plausibility_warning Feld einfuegen.\n"
            )

        # Ferry detection block (D-02, D-04)
        ferry_block = ""
        island_group = None
        await debug_logger.log(
            LogLevel.API,
            f"Geocoding Ziel fuer Faehr-Erkennung: {req.main_destination}",
            job_id=self.job_id, agent="RouteArchitect",
        )
        dest_geo = await geocode_google(req.main_destination)
        if dest_geo:
            island_group = is_island_destination((dest_geo[0], dest_geo[1]))
            if island_group:
                ports = get_ferry_ports(island_group)
                ferry_block = (
                    f"\nINSEL-ZIEL ERKANNT: {req.main_destination} liegt auf einer Insel ({island_group}). "
                    f"Die Route MUSS einen Faehrhafen als eigenen Stopp beinhalten. "
                    f"Uebliche Faehrhaefen fuer diese Region: {', '.join(ports)}. "
                    f"Fuege den Faehrhafen als eigenen Stopp in die Route ein. "
                    f"Trage die Faehrueberfahrt in ferry_crossings ein mit: "
                    f"from_port, to_port, estimated_hours, estimated_cost_chf.\n"
                )
                await debug_logger.log(
                    LogLevel.INFO,
                    f"Insel-Ziel erkannt: {req.main_destination} ({island_group}), Haefen: {', '.join(ports)}",
                    job_id=self.job_id, agent="RouteArchitect",
                )

        drive_limit_block = (
            f"\nFAHRZEITLIMIT (KRITISCH — MUSS eingehalten werden):\n"
            f"- Maximale Fahrzeit pro Tag: {req.max_drive_hours_per_day}h (NUR reine Fahrzeit, OHNE Fährüberfahrten)\n"
            f"- Fährzeit zählt NICHT als Fahrzeit. Wenn ein Tag 2h Fahrt + 4h Fähre hat, ist die Fahrzeit = 2h.\n"
            f"- Jeder Stop muss ein drive_hours Feld haben, das NUR die Fahrzeit (ohne Fähre) angibt.\n"
            f"- KEIN Stop darf drive_hours > {req.max_drive_hours_per_day}h haben.\n"
            f"- Bei Inselzielen oder Fährüberfahrten: Plane einen Stopp VOR dem Fährhafen, damit die Fahrzeit zum Hafen unter dem Limit bleibt.\n"
            f"- Wenn die Distanz zwischen zwei sinnvollen Stopps zu gross ist, füge einen zusätzlichen Zwischenstopp ein.\n"
        )

        prompt = f"""Plane eine Reiseroute mit Zwischenstopps:

Start: {req.start_location}
{via_str}Hauptziel: {req.main_destination}
Reisedauer: {req.total_days} Tage ({req.start_date} – {req.end_date})
Reisende: {req.adults} Erwachsene{f', Kinder im Alter {children_ages}' if children_ages else ''}
Reisestile: {', '.join(req.travel_styles) if req.travel_styles else 'allgemein'}
{f'Reisebeschreibung: {req.travel_description}' if req.travel_description else ''}
Maximale Fahrzeit pro Tag: {req.max_drive_hours_per_day}h (STRIKT — siehe FAHRZEITLIMIT unten)
Nächte pro Stop: {req.min_nights_per_stop}–{req.max_nights_per_stop}
Budget: CHF {req.budget_chf:,.0f}
{mandatory_str}{pref_str}{style_block}{plausibility_block}{ferry_block}{drive_limit_block}
Erstelle eine optimale Route. Der erste Stop MUSS der Startort sein, der letzte Stop MUSS das Hauptziel sein.
Dazwischen plane 2–5 sinnvolle Zwischenstopps. Verteile die Tage sinnvoll.
Gib genau dieses JSON zurück:
{{
  "stops": [
    {{"id": 1, "region": "{req.start_location}", "country": "CH", "arrival_day": 1, "nights": 0, "drive_hours": 0, "ferry_hours": 0, "is_fixed": false, "notes": "Startort"}},
    {{"id": 2, "region": "Annecy", "country": "FR", "arrival_day": 2, "nights": 2, "drive_hours": 3.5, "ferry_hours": 0, "is_fixed": false, "notes": "..."}},
    {{"id": 3, "region": "{req.main_destination}", "country": "FR", "arrival_day": 8, "nights": 3, "drive_hours": 4.0, "ferry_hours": 0, "is_fixed": false, "notes": "Hauptziel"}}
  ],
  "total_drive_days": 3,
  "total_rest_days": 7,
  "ferry_crossings": []
}}"""

        await debug_logger.log(LogLevel.API, f"→ Anthropic API call: {self.model}", job_id=self.job_id, agent="RouteArchitect")
        await debug_logger.log_prompt("RouteArchitect", self.model, prompt, job_id=self.job_id)

        def call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=get_max_tokens(AGENT_KEY, 2048),
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await call_with_retry(call, job_id=self.job_id, agent_name="RouteArchitect",
                                         token_accumulator=self.token_accumulator)
        text = response.content[0].text

        await debug_logger.log(
            LogLevel.SUCCESS, "RouteArchitect abgeschlossen",
            job_id=self.job_id, agent="RouteArchitect",
        )

        parsed = parse_agent_json(text)

        # Plausibility challenge -- fire-and-forget SSE warning (per D-13)
        if parsed.get("plausibility_warning"):
            pw = parsed["plausibility_warning"]
            await debug_logger.push_event(self.job_id, "style_mismatch_warning", {
                "warning": pw.get("warning", ""),
                "suggestions": pw.get("suggestions", []),
                "original_styles": req.travel_styles,
            })
            await debug_logger.log(
                LogLevel.INFO,
                f"Plausibilitaetswarnung: {pw.get('warning', '')}",
                job_id=self.job_id, agent="RouteArchitect",
            )

        # Ferry detection SSE event
        if parsed.get("ferry_crossings"):
            await debug_logger.push_event(self.job_id, "ferry_detected", {
                "crossings": parsed["ferry_crossings"],
                "island_group": island_group,
            })

        return parsed
