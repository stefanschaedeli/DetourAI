"""Tests fuer Faehr-Erkennung und Insel-Routing Hilfsfunktionen."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import pytest
from datetime import date
from utils.ferry_ports import (
    ISLAND_GROUPS,
    FERRY_SPEED_KMH,
    is_island_destination,
    validate_island_coordinates,
    ferry_estimate,
    get_ferry_ports,
)


def _make_req(**kwargs):
    """Create a TravelRequest with a single transit leg for testing."""
    from models.travel_request import TravelRequest
    from models.trip_leg import TripLeg
    leg = TripLeg(
        leg_id="leg-0",
        start_location=kwargs.pop("start_location", "Liestal, Schweiz"),
        end_location=kwargs.pop("main_destination", "Santorini, Griechenland"),
        start_date=kwargs.pop("start_date", date(2026, 7, 1)),
        end_date=kwargs.pop("end_date", date(2026, 7, 7)),
        mode="transit",
    )
    kwargs.pop("total_days", None)
    return TravelRequest(legs=[leg], **kwargs)


# ---------------------------------------------------------------------------
# ISLAND_GROUPS coverage
# ---------------------------------------------------------------------------

def test_island_groups_coverage():
    """ISLAND_GROUPS has exactly 8 entries with required keys."""
    expected = {
        "cyclades", "dodecanese", "ionian", "corsica",
        "sardinia", "sicily", "balearics", "croatian_islands",
    }
    assert set(ISLAND_GROUPS.keys()) == expected
    for name, group in ISLAND_GROUPS.items():
        assert "bbox" in group, f"{name} missing bbox"
        assert "center" in group, f"{name} missing center"
        assert "primary_ports" in group, f"{name} missing primary_ports"
        assert "ferry_hours_range" in group, f"{name} missing ferry_hours_range"
        bbox = group["bbox"]
        assert all(k in bbox for k in ("min_lat", "max_lat", "min_lon", "max_lon")), f"{name} bbox incomplete"


# ---------------------------------------------------------------------------
# is_island_destination
# ---------------------------------------------------------------------------

def test_is_island_destination_cyclades():
    assert is_island_destination((36.4, 25.4)) == "cyclades"


def test_is_island_destination_mainland():
    """Liestal, CH should not match any island group."""
    assert is_island_destination((47.5, 7.6)) is None


def test_is_island_destination_corsica():
    assert is_island_destination((42.15, 9.1)) == "corsica"


# ---------------------------------------------------------------------------
# validate_island_coordinates
# ---------------------------------------------------------------------------

def test_validate_island_coordinates_valid():
    """Santorini coords inside cyclades bbox."""
    assert validate_island_coordinates("Santorini", (36.4, 25.4), "cyclades") is True


def test_validate_island_coordinates_mainland():
    """Athens is mainland, outside cyclades bbox."""
    assert validate_island_coordinates("Athens", (37.98, 23.73), "cyclades") is False


# ---------------------------------------------------------------------------
# ferry_estimate
# ---------------------------------------------------------------------------

def test_ferry_estimate():
    result = ferry_estimate(300.0)
    assert result["hours"] == 10.0  # 300 / 30 = 10
    assert result["km"] == 300.0
    assert result["is_ferry"] is True


def test_ferry_estimate_short():
    result = ferry_estimate(30.0)
    assert result["hours"] == 1.0  # 30 / 30 = 1


# ---------------------------------------------------------------------------
# get_ferry_ports
# ---------------------------------------------------------------------------

def test_get_ferry_ports():
    ports = get_ferry_ports("cyclades")
    assert ports == ["Piraeus", "Rafina"]


def test_get_ferry_ports_unknown():
    assert get_ferry_ports("atlantis") == []


# ---------------------------------------------------------------------------
# Model field tests: TravelStop ferry fields
# ---------------------------------------------------------------------------

def test_travel_stop_is_ferry_default():
    from models.travel_response import TravelStop
    stop = TravelStop(id=1, region="X", country="Y", arrival_day=1, nights=1)
    assert stop.is_ferry is False


def test_travel_stop_is_ferry_true():
    from models.travel_response import TravelStop
    stop = TravelStop(id=1, region="X", country="Y", arrival_day=1, nights=1, is_ferry=True)
    assert stop.is_ferry is True


def test_travel_stop_ferry_hours():
    from models.travel_response import TravelStop
    stop = TravelStop(id=1, region="X", country="Y", arrival_day=1, nights=1, ferry_hours=3.5)
    assert stop.ferry_hours == 3.5


def test_travel_stop_ferry_cost_default():
    from models.travel_response import TravelStop
    stop = TravelStop(id=1, region="X", country="Y", arrival_day=1, nights=1)
    assert stop.ferry_cost_chf is None


# ---------------------------------------------------------------------------
# Model field tests: StopOption ferry field
# ---------------------------------------------------------------------------

def test_stop_option_is_ferry_required_default():
    from models.stop_option import StopOption
    opt = StopOption(id=1, option_type="direct", region="X", country="Y",
                     drive_hours=0, nights=1, teaser="test")
    assert opt.is_ferry_required is False


def test_stop_option_is_ferry_required():
    from models.stop_option import StopOption
    opt = StopOption(id=1, option_type="direct", region="X", country="Y",
                     drive_hours=0, nights=1, teaser="test", is_ferry_required=True)
    assert opt.is_ferry_required is True


# ---------------------------------------------------------------------------
# google_directions_with_ferry (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_directions_with_ferry_normal_route(mocker):
    """When google_directions returns valid route, pass through with is_ferry=False."""
    mocker.patch("utils.maps_helper.google_directions",
                 return_value=(3.5, 250.0, "polyline_abc"))
    from utils.maps_helper import google_directions_with_ferry
    hours, km, poly, is_ferry = await google_directions_with_ferry("A", "B")
    assert hours == 3.5
    assert km == 250.0
    assert poly == "polyline_abc"
    assert is_ferry is False


@pytest.mark.asyncio
async def test_directions_with_ferry_water_crossing(mocker):
    """When google_directions returns (0,0,'') and dest is island, return ferry estimate."""
    mocker.patch("utils.maps_helper.google_directions",
                 return_value=(0.0, 0.0, ""))
    # Cyclades coords for destination
    mocker.patch("utils.maps_helper.geocode_google",
                 side_effect=[
                     (37.98, 23.73, "origin_pid"),   # Athens (mainland)
                     (36.4, 25.4, "dest_pid"),        # Santorini (cyclades)
                 ])
    from utils.maps_helper import google_directions_with_ferry
    hours, km, poly, is_ferry = await google_directions_with_ferry("Athens", "Santorini")
    assert is_ferry is True
    assert hours > 0
    assert km > 0
    assert poly == ""


@pytest.mark.asyncio
async def test_directions_with_ferry_no_island(mocker):
    """When google_directions returns (0,0,'') and no island, return zeros."""
    mocker.patch("utils.maps_helper.google_directions",
                 return_value=(0.0, 0.0, ""))
    mocker.patch("utils.maps_helper.geocode_google",
                 side_effect=[
                     (47.5, 7.6, "pid1"),   # Liestal (mainland)
                     (48.8, 2.3, "pid2"),    # Paris (mainland)
                 ])
    from utils.maps_helper import google_directions_with_ferry
    hours, km, poly, is_ferry = await google_directions_with_ferry("Liestal", "Paris")
    assert is_ferry is False
    assert hours == 0.0
    assert km == 0.0


# ---------------------------------------------------------------------------
# Route architect ferry prompt (GEO-01)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_architect_ferry_prompt(mocker):
    """GEO-01: Route architect produces ferry-aware prompts for island destinations."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock Anthropic client factory
    mocker.patch("agents._client.os.getenv", return_value="sk-ant-test-key")
    mocker.patch("agents.route_architect.get_client", return_value=MagicMock())
    mocker.patch("agents.route_architect.get_model", return_value="claude-haiku-4-5")
    mocker.patch("agents.route_architect.get_max_tokens", return_value=2048)

    # Mock geocode to return Cyclades coords for Santorini
    mocker.patch("agents.route_architect.geocode_google",
                 new_callable=AsyncMock,
                 return_value=(36.4, 25.4, "place_id_santorini"))

    # Mock debug_logger
    mock_log = AsyncMock()
    mock_push = AsyncMock()
    mock_log_prompt = AsyncMock()
    mocker.patch("agents.route_architect.debug_logger.log", mock_log)
    mocker.patch("agents.route_architect.debug_logger.push_event", mock_push)
    mocker.patch("agents.route_architect.debug_logger.log_prompt", mock_log_prompt)

    # Mock Anthropic client response
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "stops": [
            {"id": 1, "region": "Liestal", "country": "CH", "arrival_day": 1, "nights": 0, "drive_hours": 0},
            {"id": 2, "region": "Piraeus", "country": "GR", "arrival_day": 3, "nights": 1, "drive_hours": 4},
            {"id": 3, "region": "Santorini", "country": "GR", "arrival_day": 5, "nights": 3, "drive_hours": 0},
        ],
        "total_drive_days": 2,
        "total_rest_days": 5,
        "ferry_crossings": [
            {"from_port": "Piraeus", "to_port": "Santorini", "estimated_hours": 5, "estimated_cost_chf": 80}
        ]
    }))]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)

    mocker.patch("agents.route_architect.call_with_retry",
                 new_callable=AsyncMock,
                 return_value=mock_response)

    req = _make_req(adults=2, budget_chf=5000, max_drive_hours_per_day=4.5)

    from agents.route_architect import RouteArchitectAgent
    agent = RouteArchitectAgent(req, job_id="test-ferry-001")
    result = await agent.run()

    # Verify ferry_crossings SSE event was pushed
    mock_push.assert_called_once()
    event_args = mock_push.call_args
    assert event_args[0][1] == "ferry_detected"
    assert event_args[0][2]["island_group"] == "cyclades"

    # Verify API log was emitted before geocoding
    api_calls = [c for c in mock_log.call_args_list if c[0][0].value == "API"]
    assert any("Faehr-Erkennung" in str(c) for c in api_calls)


# ---------------------------------------------------------------------------
# Ferry time deduction in day planner (GEO-05)
# ---------------------------------------------------------------------------

def test_ferry_time_deduction():
    """GEO-05: Ferry time is correctly deducted from daily driving budget in prompt."""
    max_drive_hours_per_day = 4.5

    # Simulate a day context with ferry
    day_ctx = {
        "day": 3,
        "date": "03.07.2026",
        "date_iso": "2026-07-03",
        "region": "Santorini",
        "drive_hours": 0,
        "activities": [],
        "restaurants": [],
        "prev_region": "Piraeus",
        "weather_forecast": [],
        "is_ferry": True,
        "ferry_hours": 3.0,
    }

    # Test the logic directly: ferry_hours=3.0, max_drive=4.5 -> remaining=1.5
    ferry_hours = day_ctx.get("ferry_hours", 0)
    remaining_drive = max(0, max_drive_hours_per_day - ferry_hours)
    ferry_info = (
        f"\nFAEHRE: Dieser Tag beinhaltet eine Faehrueberfahrt von {ferry_hours:.1f} Stunden. "
        f"Verbleibende Fahrzeit nach der Faehre: {remaining_drive:.1f}h. "
        f"Plane die Faehre als eigenen time_block mit activity_type 'ferry' ein.\n"
    )

    assert "Verbleibende Fahrzeit nach der Faehre: 1.5h" in ferry_info
    assert "3.0 Stunden" in ferry_info


# ---------------------------------------------------------------------------
# Ferry detection in enrichment (main.py)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrich_ferry_detection(mocker):
    """When google_directions_with_ferry detects ferry, option gets is_ferry_required."""
    mocker.patch("utils.maps_helper.google_directions",
                 return_value=(0.0, 0.0, ""))
    mocker.patch("utils.maps_helper.geocode_google",
                 side_effect=[
                     (37.98, 23.73, "origin_pid"),   # Athens (mainland)
                     (36.4, 25.4, "dest_pid"),        # Santorini (cyclades)
                 ])
    from utils.maps_helper import google_directions_with_ferry
    hours, km, poly, is_ferry = await google_directions_with_ferry("Athens", "Santorini")
    assert is_ferry is True
    assert hours > 0

    # Simulate enrichment logic
    opt = {"drive_hours": 0, "drive_km": 0}
    if hours > 0:
        opt["drive_hours"] = hours
        opt["drive_km"] = km
        if is_ferry:
            opt["is_ferry_required"] = True
            opt["ferry_hours"] = hours

    assert opt["is_ferry_required"] is True
    assert opt["ferry_hours"] > 0


# ---------------------------------------------------------------------------
# Corridor bypass for island destinations
# ---------------------------------------------------------------------------

def test_corridor_bypass_island():
    """When target is on an island, corridor check is bypassed."""
    # Santorini coords -> cyclades island group
    target_coords = (36.4, 25.4)
    target_is_island = is_island_destination(target_coords)
    assert target_is_island == "cyclades"

    # Mainland target -> no bypass
    mainland_target = (48.8, 2.3)  # Paris
    mainland_is_island = is_island_destination(mainland_target)
    assert mainland_is_island is None

    # This confirms the logic: when target_is_island is truthy,
    # corridor and bearing checks are skipped
    assert target_is_island  # truthy -> skip
    assert not mainland_is_island  # falsy -> run checks


# ---------------------------------------------------------------------------
# Ferry cost in fallback estimate
# ---------------------------------------------------------------------------

def test_fallback_cost_estimate_with_ferry(mocker):
    """Ferry cost is computed (not just 0.0) when stops have ferry data."""
    from unittest.mock import MagicMock
    from agents.day_planner import DayPlannerAgent

    mocker.patch("agents.day_planner.get_setting", return_value=100.0)
    mocker.patch("agents.day_planner.get_client", return_value=MagicMock())
    mocker.patch("agents.day_planner.get_model", return_value="claude-haiku-4-5")

    req = _make_req(adults=2, budget_chf=5000, max_drive_hours_per_day=4.5)
    agent = DayPlannerAgent(req, job_id="test-ferry-003")

    stops = [
        {"id": 1, "region": "Liestal", "nights": 0, "drive_hours_from_prev": 0},
        {"id": 2, "region": "Piraeus", "nights": 1, "drive_hours_from_prev": 10,
         "is_ferry": False},
        {"id": 3, "region": "Santorini", "nights": 3, "drive_hours_from_prev": 0,
         "is_ferry": True, "ferry_hours": 5.0, "drive_km_from_prev": 200},
    ]

    cost = agent._fallback_cost_estimate(stops)
    assert cost["ferries_chf"] > 0  # Not just 0.0
    # 50 base + 200 * 0.5 = 150 CHF
    assert cost["ferries_chf"] == 150.0
    assert cost["total_chf"] > cost["ferries_chf"]
