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
