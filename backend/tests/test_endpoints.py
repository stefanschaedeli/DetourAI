import json
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture
def mock_redis(mocker):
    mock = MagicMock()
    mock.get.return_value = None
    mock.setex.return_value = True
    mock.keys.return_value = []
    mocker.patch('main.redis_client', mock)
    return mock


@pytest.fixture
def client(mock_redis):
    from main import app
    return TestClient(app)


@pytest.fixture
def sample_request():
    return {
        "start_location": "Liestal, Schweiz",
        "main_destination": "Paris, Frankreich",
        "start_date": "2026-06-01",
        "end_date": "2026-06-10",
        "total_days": 10,
        "adults": 2,
        "children": [],
        "budget_chf": 5000,
        "travel_styles": ["culture", "culinary"],
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "active_jobs" in data


# ---------------------------------------------------------------------------
# Plan trip
# ---------------------------------------------------------------------------

def test_plan_trip_missing_required_field(client):
    r = client.post("/api/plan-trip", json={"start_location": "A"})
    assert r.status_code == 422


def test_plan_trip_missing_destination(client, sample_request):
    payload = {k: v for k, v in sample_request.items() if k != 'main_destination'}
    r = client.post("/api/plan-trip", json=payload)
    assert r.status_code == 422


def test_plan_trip_success(client, mock_redis, sample_request, mocker):
    mock_options = [
        {"id": 1, "option_type": "direct", "region": "Basel", "country": "CH",
         "lat": 47.55, "lon": 7.59,
         "drive_hours": 0.5, "nights": 1, "highlights": [], "teaser": "Test", "is_fixed": False},
        {"id": 2, "option_type": "scenic", "region": "Colmar", "country": "FR",
         "lat": 48.07, "lon": 7.35,
         "drive_hours": 1.0, "nights": 2, "highlights": [], "teaser": "Test", "is_fixed": False},
        {"id": 3, "option_type": "cultural", "region": "Mulhouse", "country": "FR",
         "lat": 47.74, "lon": 7.33,
         "drive_hours": 0.8, "nights": 1, "highlights": [], "teaser": "Test", "is_fixed": False},
    ]

    async def mock_find_options_streaming(*args, **kwargs):
        for opt in mock_options:
            yield opt
        yield {
            "_all_options": mock_options,
            "estimated_total_stops": 4,
            "route_could_be_complete": False,
        }

    mocker.patch(
        'agents.stop_options_finder.StopOptionsFinderAgent.find_options_streaming',
        side_effect=mock_find_options_streaming,
    )
    mocker.patch('main.geocode_nominatim', return_value=(47.5, 7.6))
    mocker.patch('main.osrm_route', return_value=(1.0, 80.0))

    r = client.post("/api/plan-trip", json=sample_request)
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "building_route"
    assert "options" in data
    assert "meta" in data
    assert mock_redis.setex.called


# ---------------------------------------------------------------------------
# Select stop — job not found
# ---------------------------------------------------------------------------

def test_select_stop_job_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.post("/api/select-stop/fakeid", json={"option_index": 0})
    assert r.status_code == 404


def test_select_stop_invalid_index(client, mock_redis):
    job = {
        "status": "building_route",
        "request": {
            "start_location": "Liestal", "main_destination": "Paris",
            "start_date": "2026-06-01", "end_date": "2026-06-10", "total_days": 10,
        },
        "selected_stops": [], "current_options": [],
        "stop_counter": 0, "segment_index": 0, "segment_budget": 5,
        "segment_stops": [], "selected_accommodations": [],
        "route_could_be_complete": False,
    }
    mock_redis.get.return_value = json.dumps(job)
    r = client.post("/api/select-stop/abcdef1234567890abcdef1234567890", json={"option_index": 5})
    assert r.status_code == 422  # Pydantic validation (TravelRequest missing fields in stored job)


# ---------------------------------------------------------------------------
# Confirm route — job not found
# ---------------------------------------------------------------------------

def test_confirm_route_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.post("/api/confirm-route/fakeid")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Start planning — job not found
# ---------------------------------------------------------------------------

def test_start_planning_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.post("/api/start-planning/fakeid")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Result — job not found
# ---------------------------------------------------------------------------

def test_get_result_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.get("/api/result/fakeid")
    assert r.status_code == 404


def test_get_result_success(client, mock_redis):
    job = {"status": "complete", "result": {"job_id": "abc", "stops": []}}
    mock_redis.get.return_value = json.dumps(job)
    r = client.get("/api/result/abcdef1234567890abcdef1234567890")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "complete"


# ---------------------------------------------------------------------------
# Confirm accommodations
# ---------------------------------------------------------------------------

def test_confirm_accommodations_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.post("/api/confirm-accommodations/fakeid", json={"selections": {}})
    assert r.status_code == 404


def test_confirm_accommodations_success(client, mock_redis):
    job = {
        "status": "loading_accommodations",
        "request": {
            "start_location": "Liestal", "main_destination": "Paris",
            "start_date": "2026-06-01", "end_date": "2026-06-10",
            "total_days": 10, "budget_chf": 5000, "adults": 2,
            "min_nights_per_stop": 1, "budget_buffer_percent": 10,
        },
        "selected_stops": [{"id": 1, "region": "Annecy", "nights": 2}],
        "selected_accommodations": [],
        "prefetched_accommodations": {
            "1": [
                {"id": "acc_1_budget", "option_type": "budget", "total_price_chf": 200, "name": "Budget Hotel"},
            ]
        },
        "stop_counter": 1, "segment_index": 0, "segment_budget": 10,
        "segment_stops": [], "route_could_be_complete": False,
    }
    mock_redis.get.return_value = json.dumps(job)
    r = client.post("/api/confirm-accommodations/abcdef1234567890abcdef1234567890", json={"selections": {"1": 0}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accommodations_confirmed"
    assert data["selected_count"] == 1
