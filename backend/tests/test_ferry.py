"""Tests fuer Faehr-Erkennung und Insel-Routing Hilfsfunktionen."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from utils.ferry_ports import (
    ISLAND_GROUPS,
    FERRY_SPEED_KMH,
    is_island_destination,
    validate_island_coordinates,
    ferry_estimate,
    get_ferry_ports,
)


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
