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


# ---------------------------------------------------------------------------
# Research accommodation (new endpoint)
# ---------------------------------------------------------------------------

def test_research_accommodation_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    r = client.post("/api/research-accommodation/fakeid", json={"stop_id": "1", "extra_instructions": ""})
    assert r.status_code == 404


def test_research_accommodation_stop_not_found(client, mock_redis):
    job = {
        "status": "loading_accommodations",
        "request": {
            "start_location": "Liestal", "main_destination": "Paris",
            "start_date": "2026-06-01", "end_date": "2026-06-10",
            "total_days": 10, "budget_chf": 5000, "adults": 2,
            "min_nights_per_stop": 1, "budget_buffer_percent": 10,
        },
        "selected_stops": [{"id": 1, "region": "Annecy", "nights": 2, "country": "FR", "arrival_day": 3}],
        "selected_accommodations": [],
        "prefetched_accommodations": {},
        "stop_counter": 1, "segment_index": 0, "segment_budget": 10,
        "segment_stops": [], "route_could_be_complete": False,
    }
    mock_redis.get.return_value = json.dumps(job)
    r = client.post(
        "/api/research-accommodation/abcdef1234567890abcdef1234567890",
        json={"stop_id": "99", "extra_instructions": ""}
    )
    assert r.status_code == 404
    assert "99" in r.json()["detail"]


def test_research_accommodation_success(client, mock_redis, mocker):
    job = {
        "status": "loading_accommodations",
        "request": {
            "start_location": "Liestal", "main_destination": "Paris",
            "start_date": "2026-06-01", "end_date": "2026-06-10",
            "total_days": 10, "budget_chf": 5000, "adults": 2,
            "min_nights_per_stop": 1, "budget_buffer_percent": 10,
        },
        "selected_stops": [{"id": 1, "region": "Annecy", "nights": 2, "country": "FR", "arrival_day": 3}],
        "selected_accommodations": [],
        "prefetched_accommodations": {},
        "stop_counter": 1, "segment_index": 0, "segment_budget": 10,
        "segment_stops": [], "route_could_be_complete": False,
    }
    mock_redis.get.return_value = json.dumps(job)

    mock_options = [
        {"id": "acc_1_1", "name": "Hotel Test", "type": "hotel",
         "price_per_night_chf": 120, "total_price_chf": 240,
         "teaser": "Test", "description": "Test hotel", "is_geheimtipp": False,
         "matched_must_haves": [], "features": []},
        {"id": "acc_1_2", "name": "Apartment Test", "type": "apartment",
         "price_per_night_chf": 100, "total_price_chf": 200,
         "teaser": "Test", "description": "Test apt", "is_geheimtipp": False,
         "matched_must_haves": [], "features": []},
        {"id": "acc_1_3", "name": "Geheimtipp Test", "type": "bauernhof",
         "price_per_night_chf": 90, "total_price_chf": 180,
         "teaser": "Secret", "description": "Hidden gem", "is_geheimtipp": True,
         "matched_must_haves": [], "features": []},
    ]

    async def mock_find_options(stop, budget_per_night, semaphore=None):
        return {"stop_id": 1, "region": "Annecy", "options": mock_options}

    mocker.patch(
        'agents.accommodation_researcher.AccommodationResearcherAgent.find_options',
        side_effect=mock_find_options,
    )

    r = client.post(
        "/api/research-accommodation/abcdef1234567890abcdef1234567890",
        json={"stop_id": "1", "extra_instructions": "am See bitte"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == "abcdef1234567890abcdef1234567890"
    assert data["stop_id"] == "1"
    assert len(data["options"]) == 3
    assert mock_redis.setex.called


# ---------------------------------------------------------------------------
# Travel history endpoints
# ---------------------------------------------------------------------------

SAMPLE_PLAN = {
    "job_id": "abc123",
    "start_location": "Liestal",
    "stops": [{"region": "Annecy", "id": 1}],
    "day_plans": [{}, {}],
    "cost_estimate": {"total_chf": 1200.0},
}


def test_list_travels_empty(client, mocker):
    mocker.patch('main.list_travels', new=AsyncMock(return_value=[]))
    r = client.get("/api/travels")
    assert r.status_code == 200
    assert r.json() == {"travels": []}


def test_list_travels(client, mocker):
    rows = [{"id": 1, "job_id": "abc", "title": "Test", "created_at": "2026-01-01",
             "start_location": "Liestal", "destination": "Annecy",
             "total_days": 2, "num_stops": 1, "total_cost_chf": 1200.0}]
    mocker.patch('main.list_travels', new=AsyncMock(return_value=rows))
    r = client.get("/api/travels")
    assert r.status_code == 200
    assert len(r.json()["travels"]) == 1


def test_save_travel(client, mocker):
    mocker.patch('main.save_travel', new=AsyncMock(return_value=1))
    r = client.post("/api/travels", json={"plan": SAMPLE_PLAN})
    assert r.status_code == 201
    data = r.json()
    assert data["saved"] is True
    assert data["id"] == 1


def test_save_travel_duplicate(client, mocker):
    mocker.patch('main.save_travel', new=AsyncMock(return_value=None))
    r = client.post("/api/travels", json={"plan": SAMPLE_PLAN})
    assert r.status_code == 201
    data = r.json()
    assert data["saved"] is False
    assert data["id"] is None


def test_get_travel(client, mocker):
    mocker.patch('main.get_travel', new=AsyncMock(return_value=SAMPLE_PLAN))
    r = client.get("/api/travels/1")
    assert r.status_code == 200
    assert r.json()["job_id"] == "abc123"


def test_get_travel_not_found(client, mocker):
    mocker.patch('main.get_travel', new=AsyncMock(return_value=None))
    r = client.get("/api/travels/9999")
    assert r.status_code == 404
    assert "9999" in r.json()["detail"]


def test_delete_travel(client, mocker):
    mocker.patch('main.delete_travel', new=AsyncMock(return_value=True))
    r = client.delete("/api/travels/1")
    assert r.status_code == 200
    data = r.json()
    assert data["deleted"] is True
    assert data["id"] == 1


def test_delete_travel_not_found(client, mocker):
    mocker.patch('main.delete_travel', new=AsyncMock(return_value=False))
    r = client.delete("/api/travels/9999")
    assert r.status_code == 404
    assert "9999" in r.json()["detail"]
