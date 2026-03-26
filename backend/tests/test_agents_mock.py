import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date


def _make_single_transit_req(**kwargs):
    """Create a TravelRequest with a single transit leg using new legs= format."""
    from models.travel_request import TravelRequest
    from models.trip_leg import TripLeg
    leg = TripLeg(
        leg_id="leg-0",
        start_location=kwargs.pop("start_location", "Liestal"),
        end_location=kwargs.pop("main_destination", "Paris"),
        start_date=kwargs.pop("start_date", date(2026, 6, 1)),
        end_date=kwargs.pop("end_date", date(2026, 6, 10)),
        mode="transit",
    )
    # Remove legacy flat fields that are no longer accepted
    kwargs.pop("total_days", None)
    return TravelRequest(legs=[leg], **kwargs)


# ---------------------------------------------------------------------------
# json_parser
# ---------------------------------------------------------------------------

def test_parse_agent_json_plain():
    from utils.json_parser import parse_agent_json
    raw = '{"stops": [], "total_drive_days": 2}'
    result = parse_agent_json(raw)
    assert result == {"stops": [], "total_drive_days": 2}


def test_parse_agent_json_strips_fences():
    from utils.json_parser import parse_agent_json
    raw = '```json\n{"stops": []}\n```'
    result = parse_agent_json(raw)
    assert result == {"stops": []}


def test_parse_agent_json_strips_plain_fences():
    from utils.json_parser import parse_agent_json
    raw = '```\n{"key": "value"}\n```'
    result = parse_agent_json(raw)
    assert result == {"key": "value"}


def test_parse_agent_json_whitespace():
    from utils.json_parser import parse_agent_json
    raw = '  \n  {"a": 1}  \n  '
    result = parse_agent_json(raw)
    assert result == {"a": 1}


def test_parse_agent_json_invalid():
    from utils.json_parser import parse_agent_json
    with pytest.raises(json.JSONDecodeError):
        parse_agent_json("not json")


# ---------------------------------------------------------------------------
# Route architect — JSON parsing
# ---------------------------------------------------------------------------

def test_route_architect_json_parsing(mocker):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"stops": [], "total_drive_days": 2, "total_rest_days": 8, "ferry_crossings": []}')]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_response

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('agents.route_architect.get_client', return_value=mock_client)
    mocker.patch('utils.retry_helper.asyncio.to_thread', new=AsyncMock(return_value=mock_response))

    request = _make_single_transit_req()

    from agents.route_architect import RouteArchitectAgent
    agent = RouteArchitectAgent(request, "test_job")
    # Verify agent instantiates without errors
    assert agent is not None


# ---------------------------------------------------------------------------
# Retry on rate limit
# ---------------------------------------------------------------------------

def test_retry_on_rate_limit(mocker):
    import asyncio
    from anthropic import RateLimitError
    from utils.retry_helper import call_with_retry

    call_count = 0
    mock_response = MagicMock()

    async def mock_to_thread(fn):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RateLimitError.__new__(RateLimitError)
        return mock_response

    mocker.patch('utils.retry_helper.asyncio.to_thread', side_effect=mock_to_thread)
    mocker.patch('utils.retry_helper.asyncio.sleep', new=AsyncMock())

    # Patch RateLimitError to be catchable
    async def _test():
        result = await call_with_retry(lambda: None, job_id="test", agent_name="test")
        return result

    asyncio.run(_test())
    assert call_count == 2


# ---------------------------------------------------------------------------
# Accommodation researcher — option structure
# ---------------------------------------------------------------------------

def test_accommodation_researcher_instantiation(mocker):
    from agents.accommodation_researcher import AccommodationResearcherAgent

    mock_client = MagicMock()
    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('agents.accommodation_researcher.get_client', return_value=mock_client)

    request = _make_single_transit_req(budget_chf=5000)
    agent = AccommodationResearcherAgent(request, "test_job")
    assert agent is not None
    assert agent.extra_instructions == ""

    agent2 = AccommodationResearcherAgent(request, "test_job", extra_instructions="am See")
    assert agent2.extra_instructions == "am See"


def test_accommodation_find_options_structure(mocker):
    import asyncio
    from agents.accommodation_researcher import AccommodationResearcherAgent

    mock_options = [
        {
            "id": "acc_1_1",
            "name": "Hotel Seeblick",
            "type": "hotel",
            "price_per_night_chf": 120,
            "total_price_chf": 240,
            "separate_rooms_available": False,
            "max_persons": 4,
            "rating": 8.0,
            "features": ["WiFi", "Parkplatz"],
            "teaser": "Gemütliches Hotel",
            "description": "Das Hotel Seeblick bietet komfortable Zimmer mit WiFi und Parkplatz.",
            "suitable_for_children": True,
            "is_geheimtipp": False,
            "preference_index": 0,
            "matched_must_haves": [],
            "hotel_website_url": None,
        },
        {
            "id": "acc_1_2",
            "name": "Ferienwohnung Alpenblick",
            "type": "apartment",
            "price_per_night_chf": 150,
            "total_price_chf": 300,
            "separate_rooms_available": True,
            "max_persons": 4,
            "rating": 8.5,
            "features": ["WiFi", "Küche", "Parkplatz"],
            "teaser": "Moderne Ferienwohnung",
            "description": "Moderne Ferienwohnung mit vollausgestatteter Küche und WiFi.",
            "suitable_for_children": True,
            "is_geheimtipp": False,
            "preference_index": 1,
            "matched_must_haves": [],
            "hotel_website_url": "https://example.com",
        },
        {
            "id": "acc_1_3",
            "name": "Naturhotel Alpental",
            "type": "hotel",
            "price_per_night_chf": 130,
            "total_price_chf": 260,
            "separate_rooms_available": True,
            "max_persons": 4,
            "rating": 8.8,
            "features": ["Natur", "Ruhig"],
            "teaser": "Naturnahes Hotel",
            "description": "Naturhotel mit Bergblick und ruhiger Lage.",
            "suitable_for_children": True,
            "is_geheimtipp": False,
            "preference_index": 2,
            "matched_must_haves": [],
            "hotel_website_url": None,
        },
        {
            "id": "acc_1_4",
            "name": "Bergbauernhof Sonnenschein",
            "type": "bauernhof",
            "price_per_night_chf": 100,
            "total_price_chf": 200,
            "separate_rooms_available": True,
            "max_persons": 6,
            "rating": 9.2,
            "features": ["Natur", "Authentisch"],
            "teaser": "Echter Bauernhof",
            "description": "Authentischer Bergbauernhof mit Direktkontakt zu Tieren.",
            "suitable_for_children": True,
            "is_geheimtipp": True,
            "preference_index": None,
            "matched_must_haves": [],
            "hotel_website_url": None,
            "geheimtipp_hinweis": "Direkt beim Hof buchen.",
        },
    ]

    mock_api_response = MagicMock()
    mock_api_response.content = [MagicMock(text=json.dumps({
        "stop_id": 1, "region": "Annecy", "options": mock_options
    }))]

    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_api_response
    mock_client = MagicMock()
    mock_client.messages = mock_messages
    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('agents.accommodation_researcher.get_client', return_value=mock_client)
    mocker.patch('utils.retry_helper.asyncio.to_thread', new=AsyncMock(return_value=mock_api_response))
    mocker.patch('utils.image_fetcher.fetch_unsplash_images', new=AsyncMock(
        return_value={"image_overview": None, "image_mood": None, "image_customer": None}
    ))

    request = _make_single_transit_req(
        budget_chf=5000,
        accommodation_preferences=["romantisches Hotel am See", "gemütliches Apartment"],
    )
    agent = AccommodationResearcherAgent(request, "test_job")

    stop = {"id": 1, "region": "Annecy", "country": "FR", "nights": 2, "arrival_day": 3}

    async def _run():
        return await agent.find_options(stop, budget_per_night=150.0)

    result = asyncio.run(_run())

    options = result.get("options", [])
    assert len(options) == 4

    # Check new fields present, old fields absent
    for opt in options:
        assert "description" in opt
        assert "matched_must_haves" in opt
        assert "is_geheimtipp" in opt
        assert "preference_index" in opt
        assert "option_type" not in opt
        assert "price_range" not in opt
        assert "price_source" not in opt
        assert "booking_hint" not in opt

    # First 3 options have preference_index set
    assert options[0]["preference_index"] == 0
    assert options[1]["preference_index"] == 1
    assert options[2]["preference_index"] == 2

    # Geheimtipp is option 4
    geheimtipp = options[3]
    assert geheimtipp["is_geheimtipp"] is True
    assert geheimtipp["preference_index"] is None
    assert "booking_search_url" in geheimtipp
    assert geheimtipp.get("booking_url") is None

    # Non-geheimtipp has booking_url
    normal = options[0]
    assert normal["is_geheimtipp"] is False
    assert normal.get("booking_url") is not None


# ---------------------------------------------------------------------------
# Activities agent — no enricher attribute
# ---------------------------------------------------------------------------

def test_activities_agent_no_enricher(mocker):
    from agents.activities_agent import ActivitiesAgent

    mock_client = MagicMock()
    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('agents._client.os.getenv', return_value='sk-ant-test')

    request = _make_single_transit_req()
    agent = ActivitiesAgent(request, "test_job")
    assert not hasattr(agent, 'enricher')


# ---------------------------------------------------------------------------
# image_fetcher — no key returns all None
# ---------------------------------------------------------------------------

def test_image_fetcher_stub():
    import asyncio
    from utils.image_fetcher import fetch_unsplash_images

    async def _run():
        return await fetch_unsplash_images("Paris hotel", "hotel")

    result = asyncio.run(_run())
    assert result == {"image_overview": None, "image_mood": None, "image_customer": None}



# ---------------------------------------------------------------------------
# Maps helper — build_maps_url
# ---------------------------------------------------------------------------

def test_build_maps_url_single():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["Paris"])
    assert "maps.google.com" in url
    assert "Paris" in url


def test_build_maps_url_multiple():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["Liestal", "Annecy", "Paris"])
    assert "maps/dir" in url
    assert "Liestal" in url
    assert "Paris" in url
    assert "waypoints" in url


def test_build_maps_url_empty():
    from utils.maps_helper import build_maps_url
    url = build_maps_url([])
    assert url is None


def test_build_maps_url_filters_empty():
    from utils.maps_helper import build_maps_url
    url = build_maps_url(["", "Paris", ""])
    assert url is not None
    assert "Paris" in url


# ---------------------------------------------------------------------------
# Debug logger
# ---------------------------------------------------------------------------

def test_debug_logger_singleton():
    from utils.debug_logger import debug_logger, DebugLogger
    from utils.debug_logger import debug_logger as dl2
    assert debug_logger is dl2


def test_debug_logger_subscribe_unsubscribe():
    import asyncio
    from utils.debug_logger import debug_logger

    async def _run():
        q = debug_logger.subscribe("test_job_123")
        assert q is not None
        debug_logger.unsubscribe("test_job_123")
        assert "test_job_123" not in debug_logger._subscribers

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# TravelGuideAgent — instantiation + JSON parsing
# ---------------------------------------------------------------------------

def test_travel_guide_agent_instantiation(mocker):
    from agents.travel_guide_agent import TravelGuideAgent

    mock_client = MagicMock()
    mocker.patch('anthropic.Anthropic', return_value=mock_client)
    mocker.patch('agents.travel_guide_agent.get_client', return_value=mock_client)

    request = _make_single_transit_req()
    agent = TravelGuideAgent(request, "test_job")
    assert agent is not None
    assert hasattr(agent, 'model')
    assert hasattr(agent, 'client')


def test_travel_guide_agent_json_parsing(mocker):
    import asyncio
    from agents.travel_guide_agent import TravelGuideAgent

    mock_guide_response = {
        "stop_id": 1,
        "travel_guide": {
            "intro_narrative": "Annecy ist eine bezaubernde Stadt.",
            "history_culture": "Die Stadt hat eine reiche Geschichte.",
            "food_specialties": "Tartiflette ist ein Muss.",
            "local_tips": "Früh aufstehen lohnt sich.",
            "insider_gems": "Der Gorge du Fier ist weniger bekannt.",
            "best_time_to_visit": "Mai bis September.",
        },
        "further_activities": [
            {
                "name": "Vélo-Tour am Lac d'Annecy",
                "description": "Rundfahrt am See",
                "duration_hours": 3.0,
                "price_chf": 20.0,
                "suitable_for_children": True,
                "notes": "Fahrradverleih vor Ort",
                "address": "Annecy",
                "google_maps_url": "https://maps.google.com/?q=Annecy",
            }
        ],
    }

    mock_api_response = MagicMock()
    mock_api_response.content = [MagicMock(text=json.dumps(mock_guide_response))]

    mock_client = MagicMock()
    mocker.patch('agents.travel_guide_agent.get_client', return_value=mock_client)
    mocker.patch('utils.retry_helper.asyncio.to_thread', new=AsyncMock(return_value=mock_api_response))

    request = _make_single_transit_req()
    agent = TravelGuideAgent(request, "test_job")
    stop = {"id": 1, "region": "Annecy", "country": "FR", "nights": 2, "arrival_day": 3}

    async def _run():
        return await agent.run_stop(stop, ["Bootsfahrt", "Schloss Annecy"])

    result = asyncio.run(_run())

    assert "travel_guide" in result
    assert result["travel_guide"]["intro_narrative"].startswith("Annecy")
    assert "further_activities" in result
    assert len(result["further_activities"]) == 1
    assert result["further_activities"][0]["name"] == "Vélo-Tour am Lac d'Annecy"


# RegionPlannerAgent — region-based route planning
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch, AsyncMock
from agents.region_planner import RegionPlannerAgent, _reorder_regions
from models.trip_leg import RegionPlan, RegionPlanItem
from models.travel_request import TravelRequest
from models.trip_leg import TripLeg
from datetime import date

def _make_req_with_explore_leg():
    leg = TripLeg(
        leg_id="leg-0",
        start_location="Zürich", end_location="Zürich",
        start_date=date(2026, 6, 15), end_date=date(2026, 7, 1),
        mode="explore",
        explore_description="Schweizer Alpen erkunden, Bergdörfer und Seen",
    )
    return TravelRequest(legs=[leg])

PLAN_JSON = """{
  "regions": [
    {"name": "Tessin", "lat": 46.2, "lon": 8.95, "reason": "Mediterranes Flair"},
    {"name": "Graubünden", "lat": 46.8, "lon": 9.8, "reason": "Alpenlandschaft"}
  ],
  "summary": "Rundreise durch die Schweizer Alpen"
}"""

REPLACE_JSON = """{
  "regions": [
    {"name": "Wallis", "lat": 46.3, "lon": 7.6, "reason": "Matterhorn-Region"},
    {"name": "Graubünden", "lat": 46.8, "lon": 9.8, "reason": "Alpenlandschaft"}
  ],
  "summary": "Angepasste Rundreise mit Wallis statt Tessin"
}"""


class TestRegionPlannerAgent:
    def _mock_response(self, text):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        msg.model = "claude-opus-4-5"
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        return msg

    @patch("agents.region_planner.geocode_google", new_callable=AsyncMock, return_value=(47.37, 8.54, "ch1"))
    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_plan_returns_region_plan(self, mock_retry, mock_get_client, mock_geo):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(PLAN_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        result = asyncio.run(agent.plan(
            description="Schweizer Alpen",
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert len(result.regions) == 2
        assert "Rundreise" in result.summary

    @patch("agents.region_planner.geocode_google", new_callable=AsyncMock, return_value=(47.37, 8.54, "ch1"))
    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_replace_region(self, mock_retry, mock_get_client, mock_geo):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(REPLACE_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        current_plan = RegionPlan(
            regions=[
                RegionPlanItem(name="Tessin", lat=46.2, lon=8.95, reason="Mediterranes Flair"),
                RegionPlanItem(name="Graubünden", lat=46.8, lon=9.8, reason="Alpenlandschaft"),
            ],
            summary="Original"
        )
        result = asyncio.run(agent.replace_region(
            index=0,
            instruction="Ersetze durch Wallis",
            current_plan=current_plan,
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert result.regions[0].name == "Wallis"

    @patch("agents.region_planner.geocode_google", new_callable=AsyncMock, return_value=(47.37, 8.54, "ch1"))
    @patch("agents.region_planner.get_client")
    @patch("agents.region_planner.call_with_retry")
    def test_recalculate(self, mock_retry, mock_get_client, mock_geo):
        import asyncio
        mock_get_client.return_value = MagicMock()
        mock_retry.return_value = self._mock_response(PLAN_JSON)
        req = _make_req_with_explore_leg()
        agent = RegionPlannerAgent(req, "job123")

        current_plan = RegionPlan(
            regions=[RegionPlanItem(name="X", lat=0, lon=0, reason="alt")],
            summary="Alt"
        )
        result = asyncio.run(agent.recalculate(
            instruction="Mehr Küste",
            current_plan=current_plan,
            leg_index=0,
        ))
        assert isinstance(result, RegionPlan)
        assert len(result.regions) == 2


# ---------------------------------------------------------------------------
# _reorder_regions — pure function tests (no mocks needed)
# ---------------------------------------------------------------------------

class TestReorderRegions:
    """Test the nearest-neighbor + 2-opt route optimization."""

    @staticmethod
    def _r(name: str, lat: float, lon: float) -> RegionPlanItem:
        return RegionPlanItem(name=name, lat=lat, lon=lon, reason="test")

    def test_circular_route_no_zigzag(self):
        """Regions in zigzag order should be reordered into a logical loop."""
        # Greece example: start in Athens, regions scattered around Greece
        athens = (37.98, 23.73)
        regions = [
            self._r("Thessalien", 39.6, 22.4),     # north-east
            self._r("Epirus", 39.6, 20.8),          # north-west
            self._r("Peloponnes", 37.5, 22.3),      # south
            self._r("Ionische Inseln", 38.5, 20.5),  # west
            self._r("Meteora", 39.7, 21.6),          # north-center
        ]
        result = _reorder_regions(regions, athens, None, circular=True)
        names = [r.name for r in result]
        # The exact order depends on the heuristic, but key properties:
        # 1. Peloponnes should be near start (closest to Athens)
        assert names[0] == "Peloponnes"
        # 2. No zigzag — consecutive regions should be geographically close
        # Verify total route distance is less than original zigzag
        from utils.maps_helper import haversine_km
        def route_dist(regs):
            d = haversine_km(athens, (regs[0].lat, regs[0].lon))
            for i in range(len(regs) - 1):
                d += haversine_km((regs[i].lat, regs[i].lon), (regs[i+1].lat, regs[i+1].lon))
            d += haversine_km((regs[-1].lat, regs[-1].lon), athens)
            return d
        assert route_dist(result) <= route_dist(regions)

    def test_oneway_route_anchors(self):
        """One-way: first region near start, last near end."""
        zurich = (47.37, 8.54)
        geneva = (46.20, 6.14)
        regions = [
            self._r("Bern", 46.95, 7.44),
            self._r("Luzern", 47.05, 8.31),
            self._r("Lausanne", 46.52, 6.63),
            self._r("Interlaken", 46.69, 7.85),
        ]
        result = _reorder_regions(regions, zurich, geneva, circular=False)
        # Luzern closest to Zürich → first
        assert result[0].name == "Luzern"
        # Lausanne closest to Geneva → last
        assert result[-1].name == "Lausanne"

    def test_single_region_unchanged(self):
        regions = [self._r("Tessin", 46.2, 8.95)]
        result = _reorder_regions(regions, (47.37, 8.54), None, circular=True)
        assert len(result) == 1
        assert result[0].name == "Tessin"

    def test_two_regions_unchanged(self):
        regions = [
            self._r("A", 46.0, 8.0),
            self._r("B", 47.0, 9.0),
        ]
        result = _reorder_regions(regions, (47.37, 8.54), None, circular=True)
        assert len(result) == 2

    def test_optimized_distance_shorter(self):
        """Optimized route should never be longer than original."""
        start = (47.37, 8.54)  # Zürich
        # Deliberately zigzag regions
        regions = [
            self._r("Süd", 45.5, 8.5),
            self._r("Nord", 48.0, 9.0),
            self._r("Mitte-Süd", 46.5, 8.0),
            self._r("Mitte-Nord", 47.5, 8.5),
        ]
        result = _reorder_regions(regions, start, None, circular=True)
        from utils.maps_helper import haversine_km
        def route_dist(regs):
            d = haversine_km(start, (regs[0].lat, regs[0].lon))
            for i in range(len(regs) - 1):
                d += haversine_km((regs[i].lat, regs[i].lon), (regs[i+1].lat, regs[i+1].lon))
            d += haversine_km((regs[-1].lat, regs[-1].lon), start)
            return d
        assert route_dist(result) <= route_dist(regions)


# ---------------------------------------------------------------------------
# StopOptionsFinder — style enforcement in SYSTEM_PROMPT
# ---------------------------------------------------------------------------

def test_stop_options_style_enforcement():
    """AIQ-03: StopOptionsFinder SYSTEM_PROMPT must enforce travel style matching."""
    from agents.stop_options_finder import SYSTEM_PROMPT
    assert "STIL-REGEL" in SYSTEM_PROMPT, "SYSTEM_PROMPT missing STIL-REGEL block"
    assert "matches_travel_style" in SYSTEM_PROMPT, "SYSTEM_PROMPT missing matches_travel_style field requirement"
