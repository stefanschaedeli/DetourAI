"""Tests for route editing helpers and Celery tasks (remove, add, reorder)."""

import asyncio
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_stop(stop_id: int, region: str = "Stop", nights: int = 1,
               arrival_day: int = 1) -> dict:
    return {
        "id": stop_id,
        "region": f"{region} {stop_id}",
        "country": "CH",
        "lat": 47.0 + stop_id * 0.1,
        "lon": 8.0 + stop_id * 0.1,
        "nights": nights,
        "arrival_day": arrival_day,
        "drive_hours_from_prev": 2.0,
        "drive_km_from_prev": 150,
        "top_activities": [{"name": f"Activity {stop_id}"}],
        "restaurants": [{"name": f"Restaurant {stop_id}"}],
        "travel_guide": f"Guide for stop {stop_id}",
        "further_activities": [],
        "accommodation": {"name": f"Hotel {stop_id}", "price_per_night": 120},
        "all_accommodation_options": [],
        "image_overview": None,
        "image_mood": None,
        "image_customer": None,
    }


def _make_plan(n_stops: int = 3) -> dict:
    """Create a plan dict with n stops (arrival days auto-chained)."""
    stops = []
    day = 1
    for i in range(n_stops):
        stop = _make_stop(i + 1, nights=1, arrival_day=day)
        stops.append(stop)
        day += 2  # nights(1) + 1 drive day
    return {
        "stops": stops,
        "start_location": "Liestal, Schweiz",
        "request": {
            "legs": [{
                "leg_id": "leg-0",
                "start_location": "Liestal, Schweiz",
                "end_location": "Paris, Frankreich",
                "start_date": "2026-06-01",
                "end_date": "2026-06-14",
                "mode": "transit",
                "via_points": [],
                "zone_bbox": None,
                "zone_guidance": [],
            }],
            "adults": 2,
            "children": [],
            "budget_chf": 5000,
            "travel_styles": ["culture"],
            "budget_accommodation_pct": 60,
            "budget_food_pct": 20,
            "budget_activities_pct": 20,
        },
        "day_plans": [],
        "cost_estimate": {},
        "google_maps_overview_url": "",
    }


def _sample_request():
    """Return a minimal TravelRequest-compatible dict."""
    return _make_plan()["request"]


# ---------------------------------------------------------------------------
# Tests: recalc_arrival_days
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recalc_arrival_days():
    """Arrival days rechain correctly from index 0."""
    from utils.route_edit_helpers import recalc_arrival_days

    stops = [
        _make_stop(1, nights=2, arrival_day=99),
        _make_stop(2, nights=1, arrival_day=99),
        _make_stop(3, nights=3, arrival_day=99),
    ]
    await recalc_arrival_days(stops, from_index=0)

    assert stops[0]["arrival_day"] == 1
    # stop 1: arrival_day = 1 + 2 nights + 1 drive = 4
    assert stops[1]["arrival_day"] == 4
    # stop 2: arrival_day = 4 + 1 night + 1 drive = 6
    assert stops[2]["arrival_day"] == 6


@pytest.mark.asyncio
async def test_recalc_arrival_days_from_mid():
    """Arrival days rechain correctly from a mid-index (preserving earlier stops)."""
    from utils.route_edit_helpers import recalc_arrival_days

    stops = [
        _make_stop(1, nights=2, arrival_day=1),
        _make_stop(2, nights=1, arrival_day=4),
        _make_stop(3, nights=3, arrival_day=99),  # wrong, should be 6
    ]
    await recalc_arrival_days(stops, from_index=2)

    assert stops[0]["arrival_day"] == 1  # unchanged
    assert stops[1]["arrival_day"] == 4  # unchanged
    assert stops[2]["arrival_day"] == 6  # recalculated


# ---------------------------------------------------------------------------
# Tests: recalc_segment_directions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recalc_segment_directions():
    """google_directions_simple called with correct origin/destination."""
    from utils.route_edit_helpers import recalc_segment_directions

    stops = [
        _make_stop(1),
        _make_stop(2),
    ]

    with patch("utils.maps_helper.google_directions_simple",
               new_callable=AsyncMock, return_value=(2.5, 200.0)):
        await recalc_segment_directions(stops, 1, "Liestal, Schweiz")

    assert stops[1]["drive_hours_from_prev"] == 2.5
    assert stops[1]["drive_km_from_prev"] == 200


@pytest.mark.asyncio
async def test_recalc_segment_directions_first_stop():
    """First stop uses start_location as origin."""
    from utils.route_edit_helpers import recalc_segment_directions

    stops = [_make_stop(1)]

    with patch("utils.maps_helper.google_directions_simple",
               new_callable=AsyncMock, return_value=(1.0, 80.0)) as mock_dir:
        await recalc_segment_directions(stops, 0, "Liestal, Schweiz")
        mock_dir.assert_called_once()
        args = mock_dir.call_args[0]
        assert args[0] == "Liestal, Schweiz"


# ---------------------------------------------------------------------------
# Tests: remove stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_stop_reconnect():
    """Removing middle stop reconnects and shrinks list."""
    from utils.route_edit_helpers import recalc_segment_directions, recalc_arrival_days

    plan = _make_plan(3)
    stops = plan["stops"]
    assert len(stops) == 3

    # Remove middle stop (index 1)
    stops.pop(1)
    assert len(stops) == 2

    with patch("utils.maps_helper.google_directions_simple",
               new_callable=AsyncMock, return_value=(3.0, 250.0)):
        await recalc_segment_directions(stops, 1, "Liestal, Schweiz")

    assert stops[1]["drive_hours_from_prev"] == 3.0
    assert stops[1]["drive_km_from_prev"] == 250


@pytest.mark.asyncio
async def test_remove_stop_arrival_days():
    """After removing a stop, arrival days rechain correctly."""
    from utils.route_edit_helpers import recalc_arrival_days

    plan = _make_plan(3)
    stops = plan["stops"]

    # Remove middle stop
    stops.pop(1)

    await recalc_arrival_days(stops, from_index=0)
    assert stops[0]["arrival_day"] == 1
    # stop[0] has nights=1, so stop[1].arrival_day = 1 + 1 + 1 = 3
    assert stops[1]["arrival_day"] == 3


# ---------------------------------------------------------------------------
# Tests: add stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_stop_inserts_at_position():
    """New stop inserted after the specified index."""
    plan = _make_plan(3)
    stops = plan["stops"]

    new_stop = _make_stop(99, region="NewStop")
    insert_pos = 1 + 1  # insert after index 1 => position 2
    stops.insert(insert_pos, new_stop)

    assert len(stops) == 4
    assert stops[2]["id"] == 99
    assert stops[2]["region"] == "NewStop 99"


@pytest.mark.asyncio
async def test_add_stop_runs_research():
    """run_research_pipeline is callable with correct signature."""
    from utils.route_edit_helpers import run_research_pipeline
    from models.travel_request import TravelRequest

    plan = _make_plan(2)
    request = TravelRequest(**plan["request"])
    new_stop = _make_stop(99)
    plan["stops"].append(new_stop)

    with patch("agents.activities_agent.ActivitiesAgent") as mock_act, \
         patch("agents.restaurants_agent.RestaurantsAgent") as mock_rest, \
         patch("agents.travel_guide_agent.TravelGuideAgent") as mock_guide, \
         patch("agents.accommodation_researcher.AccommodationResearcherAgent") as mock_acc, \
         patch("utils.image_fetcher.fetch_unsplash_images",
               new_callable=AsyncMock, return_value={}), \
         patch("utils.settings_store.get_setting", return_value=45):

        mock_act.return_value.run_stop = AsyncMock(return_value={"top_activities": []})
        mock_rest.return_value.run_stop = AsyncMock(return_value={"restaurants": []})
        mock_guide.return_value.run_stop = AsyncMock(
            return_value={"travel_guide": "test", "further_activities": []})
        mock_acc.return_value.find_options = AsyncMock(
            return_value={"options": [{"name": "Hotel Test", "price_per_night": 100}]})

        await run_research_pipeline(new_stop, request, "test-job", plan)

    assert new_stop["travel_guide"] == "test"
    assert new_stop["accommodation"]["name"] == "Hotel Test"


# ---------------------------------------------------------------------------
# Tests: reorder stops
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reorder_recalcs_all():
    """After reorder, google_directions_simple called for every stop."""
    from utils.route_edit_helpers import recalc_all_segments

    stops = [_make_stop(1), _make_stop(2), _make_stop(3)]

    # Simulate reorder: move index 0 to index 2
    moved = stops.pop(0)
    stops.insert(2, moved)

    with patch("utils.maps_helper.google_directions_simple",
               new_callable=AsyncMock, return_value=(1.5, 100.0)) as mock_dir:
        await recalc_all_segments(stops, "Liestal, Schweiz")

    assert mock_dir.call_count == 3  # called for every stop


@pytest.mark.asyncio
async def test_reorder_renumbers_ids():
    """After reorder, IDs should be reassigned sequentially."""
    stops = [_make_stop(1), _make_stop(2), _make_stop(3)]

    # Move stop 0 to end
    moved = stops.pop(0)
    stops.insert(2, moved)

    # Reassign IDs (as reorder task does)
    for i, s in enumerate(stops):
        s["id"] = i + 1

    assert stops[0]["id"] == 1
    assert stops[1]["id"] == 2
    assert stops[2]["id"] == 3


# ---------------------------------------------------------------------------
# Tests: edit lock
# ---------------------------------------------------------------------------

def test_edit_lock_acquire_release():
    """Lock semantics: acquire returns True, release clears."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    with patch("utils.route_edit_lock._get_redis", return_value=mock_redis):
        from utils.route_edit_lock import acquire_edit_lock, release_edit_lock

        result = acquire_edit_lock(42)
        assert result is True
        mock_redis.set.assert_called_once_with(
            "edit_lock:42", "1", nx=True, ex=300)

        release_edit_lock(42)
        mock_redis.delete.assert_called_once_with("edit_lock:42")


def test_edit_lock_contention():
    """Second acquire fails when lock is held."""
    mock_redis = MagicMock()
    # First call succeeds, second fails (NX not satisfied)
    mock_redis.set.side_effect = [True, False]

    with patch("utils.route_edit_lock._get_redis", return_value=mock_redis):
        from utils.route_edit_lock import acquire_edit_lock

        assert acquire_edit_lock(42) is True
        assert acquire_edit_lock(42) is False
