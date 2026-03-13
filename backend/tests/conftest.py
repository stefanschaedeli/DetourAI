import json
import uuid
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Point DATA_DIR to a writable temp location before main.py is imported
# (main.py calls _init_db() at module level using this env var)
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp())

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def client(mocker):
    # Mock Redis to avoid needing a real Redis server
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.keys.return_value = []
    mocker.patch('main.redis_client', mock_redis)

    from main import app
    return TestClient(app)


@pytest.fixture
def mock_job(mocker):
    """A minimal job dict stored in the mocked Redis, returns the job dict for mutation."""
    job_id = uuid.uuid4().hex
    leg = {
        "leg_id": "leg-0",
        "start_location": "Liestal",
        "end_location": "Paris",
        "start_date": "2026-06-01",
        "end_date": "2026-06-14",
        "mode": "transit",
        "via_points": [],
        "zone_bbox": None,
        "zone_guidance": [],
    }
    job = {
        "job_id": job_id,
        "status": "building_route",
        "request": {"legs": [leg], "adults": 2, "children": [],
                    "budget_accommodation_pct": 60, "budget_food_pct": 20,
                    "budget_activities_pct": 20},
        "selected_stops": [],
        "leg_index": 0,
        "region_plan": None,
        "region_plan_confirmed": False,
    }

    mock_redis = mocker.patch("main.redis_client")
    mock_redis.get.side_effect = lambda key: (
        json.dumps(job).encode() if key == f"job:{job_id}" else None
    )
    mock_redis.setex.side_effect = lambda key, ttl, val: job.update(json.loads(val))
    mock_redis.keys.return_value = []

    job["job_id"] = job_id  # expose for test access
    return job


@pytest.fixture
def sample_request():
    leg = {
        "leg_id": "leg-0",
        "start_location": "Liestal, Schweiz",
        "end_location": "Paris, Frankreich",
        "start_date": "2026-06-01",
        "end_date": "2026-06-10",
        "mode": "transit",
        "via_points": [],
        "zone_bbox": None,
        "zone_guidance": [],
    }
    return {
        "legs": [leg],
        "adults": 2,
        "children": [],
        "budget_chf": 5000,
        "travel_styles": ["culture", "culinary"],
        "budget_accommodation_pct": 60,
        "budget_food_pct": 20,
        "budget_activities_pct": 20,
    }
