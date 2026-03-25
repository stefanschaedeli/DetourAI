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
