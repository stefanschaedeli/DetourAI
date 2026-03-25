"""Tests for AI quality validation utilities (Phase 01)."""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, patch

import pytest
from utils.maps_helper import bearing_degrees, bearing_deviation, proportional_corridor_buffer
from models.stop_option import StopOption


class TestBearingDegrees:
    def test_due_north(self):
        assert abs(bearing_degrees((0, 0), (1, 0)) - 0.0) < 1.0

    def test_due_east(self):
        assert abs(bearing_degrees((0, 0), (0, 1)) - 90.0) < 1.0

    def test_due_south(self):
        assert abs(bearing_degrees((0, 0), (-1, 0)) - 180.0) < 1.0

    def test_due_west(self):
        assert abs(bearing_degrees((0, 0), (0, -1)) - 270.0) < 1.0

    def test_northeast(self):
        b = bearing_degrees((0, 0), (1, 1))
        assert 40 < b < 50  # ~44.99 degrees

    def test_same_point(self):
        # Same point should return 0 (or any value, not crash)
        bearing_degrees((47.0, 8.0), (47.0, 8.0))


class TestBearingDeviation:
    def test_same_bearing(self):
        assert bearing_deviation(90, 90) == 0

    def test_opposite(self):
        assert bearing_deviation(0, 180) == 180

    def test_wrap_around(self):
        assert abs(bearing_deviation(350, 10) - 20) < 0.01

    def test_large_wrap(self):
        assert abs(bearing_deviation(10, 350) - 20) < 0.01

    def test_right_angle(self):
        assert abs(bearing_deviation(0, 90) - 90) < 0.01


class TestProportionalCorridorBuffer:
    def test_normal_200km(self):
        assert proportional_corridor_buffer(200) == 40.0

    def test_floor_50km(self):
        assert proportional_corridor_buffer(50) == 15.0

    def test_ceiling_600km(self):
        assert proportional_corridor_buffer(600) == 100.0

    def test_zero_km(self):
        assert proportional_corridor_buffer(0) == 15.0

    def test_exact_floor_boundary(self):
        assert proportional_corridor_buffer(75) == 15.0  # 75*0.2=15

    def test_exact_ceiling_boundary(self):
        assert proportional_corridor_buffer(500) == 100.0  # 500*0.2=100


class TestStopOptionNewFields:
    def test_defaults(self):
        opt = StopOption(
            id=1, option_type="direct", region="Annecy",
            country="FR", drive_hours=3.0, nights=2, teaser="test"
        )
        assert opt.outside_corridor is False
        assert opt.corridor_distance_km is None
        assert opt.travel_style_match is True

    def test_explicit_values(self):
        opt = StopOption(
            id=1, option_type="direct", region="Annecy",
            country="FR", drive_hours=3.0, nights=2, teaser="test",
            outside_corridor=True, corridor_distance_km=25.3,
            travel_style_match=False
        )
        assert opt.outside_corridor is True
        assert opt.corridor_distance_km == 25.3
        assert opt.travel_style_match is False

    def test_corridor_flag(self):
        """AIQ-02: StopOption with outside_corridor=True round-trips via .model_dump()."""
        opt = StopOption(
            id=2, option_type="detour", region="Nice",
            country="FR", drive_hours=4.0, nights=1, teaser="Kueste",
            outside_corridor=True, corridor_distance_km=42.7,
        )
        assert opt.outside_corridor is True
        assert opt.corridor_distance_km == 42.7
        dumped = opt.model_dump()
        assert dumped["outside_corridor"] is True
        assert dumped["corridor_distance_km"] == 42.7
        # Reconstruct from dict -- proves JSON serialization round-trip
        opt2 = StopOption(**dumped)
        assert opt2.outside_corridor is True
        assert opt2.corridor_distance_km == 42.7


class TestBacktrackingDetection:
    def test_backtracking_detection(self):
        """AIQ-05: bearing deviation > 90 means backtracking."""
        liestal = (47.48, 7.73)
        paris = (48.86, 2.35)
        route_bearing = bearing_degrees(liestal, paris)

        # A point clearly behind (south-east of Liestal)
        behind = (46.5, 8.5)
        stop_bearing = bearing_degrees(liestal, behind)
        deviation = bearing_deviation(route_bearing, stop_bearing)
        assert deviation > 90, f"Expected backtracking (>90), got {deviation}"

    def test_no_backtracking_forward(self):
        """Stops in the forward direction should NOT be flagged."""
        liestal = (47.48, 7.73)
        paris = (48.86, 2.35)
        route_bearing = bearing_degrees(liestal, paris)

        # Dijon is roughly on the way to Paris
        dijon = (47.32, 5.04)
        stop_bearing = bearing_degrees(liestal, dijon)
        deviation = bearing_deviation(route_bearing, stop_bearing)
        assert deviation <= 90, f"Expected forward (<= 90), got {deviation}"


class TestStopOptionsFinderModel:
    def test_prod_model_is_sonnet(self):
        """AIQ-01: StopOptionsFinder must use claude-sonnet-4-5 as production model."""
        agent_file = os.path.join(
            os.path.dirname(__file__), "..", "agents", "stop_options_finder.py"
        )
        with open(agent_file) as f:
            source = f.read()
        assert 'get_model("claude-sonnet-4-5"' in source
        assert 'get_model("claude-haiku-4-5"' not in source


class TestQualityValidationReject:
    """AIQ-04: validate_stop_quality rejects low-quality stops."""

    @pytest.mark.asyncio
    async def test_quality_validation_reject_no_place(self):
        """Reject when Google Places finds no results for the region."""
        with patch("utils.google_places.find_place_from_text", new_callable=AsyncMock, return_value=None):
            from utils.google_places import validate_stop_quality
            is_quality, reason = await validate_stop_quality("FakeVillage", "XX", 0.0, 0.0)
            assert is_quality is False
            assert "Kein Google Places Ergebnis" in reason

    @pytest.mark.asyncio
    async def test_quality_validation_reject_few_attractions(self):
        """Reject when too few tourist attractions nearby."""
        with patch("utils.google_places.find_place_from_text", new_callable=AsyncMock, return_value={"name": "Test"}), \
             patch("utils.google_places.nearby_search", new_callable=AsyncMock, return_value=[{"name": "one"}]):
            from utils.google_places import validate_stop_quality
            is_quality, reason = await validate_stop_quality("SmallVillage", "FR", 47.0, 7.0)
            assert is_quality is False
            assert "Zu wenige" in reason

    @pytest.mark.asyncio
    async def test_quality_validation_reject_low_rating(self):
        """Reject when average attraction rating is below 3.0."""
        attractions = [
            {"name": "A", "rating": 2.0},
            {"name": "B", "rating": 2.5},
            {"name": "C", "rating": 2.8},
        ]
        with patch("utils.google_places.find_place_from_text", new_callable=AsyncMock, return_value={"name": "Test"}), \
             patch("utils.google_places.nearby_search", new_callable=AsyncMock, return_value=attractions):
            from utils.google_places import validate_stop_quality
            is_quality, reason = await validate_stop_quality("BadTown", "DE", 48.0, 8.0)
            assert is_quality is False
            assert "Niedrige" in reason

    @pytest.mark.asyncio
    async def test_quality_validation_accept(self):
        """Accept when place has sufficient high-rated attractions."""
        attractions = [
            {"name": "A", "rating": 4.5},
            {"name": "B", "rating": 4.2},
            {"name": "C", "rating": 3.8},
        ]
        with patch("utils.google_places.find_place_from_text", new_callable=AsyncMock, return_value={"name": "Annecy"}), \
             patch("utils.google_places.nearby_search", new_callable=AsyncMock, return_value=attractions):
            from utils.google_places import validate_stop_quality
            is_quality, reason = await validate_stop_quality("Annecy", "FR", 45.9, 6.13)
            assert is_quality is True
            assert reason == "OK"


class TestSilentReask:
    """AIQ-04/D-08: Quality rejection returns None from _enrich_one, triggering re-ask."""

    def test_silent_reask_pipeline_design(self):
        """Verify that validate_stop_quality returning False leads to None return in _enrich_one.

        This is a design-level test: we verify that main.py contains the pattern where
        validate_stop_quality failure returns None (which triggers the existing retry loop).
        Integration testing of the full _enrich_one pipeline requires a running server,
        so we verify the code pattern statically."""
        main_file = os.path.join(os.path.dirname(__file__), "..", "main.py")
        with open(main_file) as f:
            source = f.read()
        # Verify the quality check pattern: call validate_stop_quality, return None on failure
        assert "validate_stop_quality" in source, "main.py must call validate_stop_quality"
        assert "is_quality" in source or "not is_quality" in source, "main.py must check quality result"
        # Verify the silent rejection pattern (return None after quality failure)
        # The pattern: if not is_quality: ... return None
        lines = source.split("\n")
        found_quality_reject = False
        for i, line in enumerate(lines):
            if "not is_quality" in line:
                # Look for return None within the next 10 lines
                for j in range(i + 1, min(i + 11, len(lines))):
                    if "return None" in lines[j]:
                        found_quality_reject = True
                        break
        assert found_quality_reject, "main.py must return None after quality validation failure (silent rejection per D-08)"
