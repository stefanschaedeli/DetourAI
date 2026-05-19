"""Integration tests for /api/admin/logs endpoints."""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("DATA_DIR", "/tmp/test_logs_router")
os.environ.setdefault("JWT_SECRET", "test_secret_that_is_exactly_32chars!")


@pytest.fixture(autouse=True)
def patch_jwt_secret(monkeypatch):
    import utils.auth as _auth_mod
    monkeypatch.setattr(_auth_mod, "JWT_SECRET", "test_secret_that_is_exactly_32chars!")


@pytest.fixture
def tmp_logs(tmp_path, monkeypatch):
    """Create a temp LOGS_DIR with sample log files."""
    logs = tmp_path / "logs"
    (logs / "agents").mkdir(parents=True)
    (logs / "orchestrator").mkdir(parents=True)
    (logs / "api").mkdir(parents=True)
    (logs / "frontend").mkdir(parents=True)
    (logs / "agents" / "route_architect.log").write_text(
        "[2026-05-18 10:00:00] [INFO] [job:abc12345] [RouteArchitect] Processing\n"
        "[2026-05-18 10:00:01] [ERROR] [job:abc12345] [RouteArchitect] Failed\n"
    )
    (logs / "orchestrator" / "orchestrator.log").write_text(
        "[2026-05-18 09:59:00] [INFO] [Orchestrator] Starting\n"
    )
    monkeypatch.setenv("LOGS_DIR", str(logs))
    import routers.logs as logs_mod
    import utils.debug_logger as dl_mod
    dl_mod.LOGS_DIR = logs
    logs_mod.LOGS_DIR = logs
    return logs


@pytest.fixture
def admin_headers():
    from utils.auth import create_access_token
    token = create_access_token(user_id=1, username="admin", is_admin=True)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers():
    from utils.auth import create_access_token
    token = create_access_token(user_id=2, username="user", is_admin=False)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(mocker):
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.keys.return_value = []
    mocker.patch("services.redis_store.redis_client", mock_redis)
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/admin/logs/files
# ---------------------------------------------------------------------------

def test_files_requires_admin(client, tmp_logs, user_headers):
    res = client.get("/api/admin/logs/files", headers=user_headers)
    assert res.status_code == 403


def test_files_requires_auth(client, tmp_logs):
    res = client.get("/api/admin/logs/files")
    assert res.status_code == 401


def test_files_returns_tree(client, tmp_logs, admin_headers):
    res = client.get("/api/admin/logs/files", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "groups" in data
    names = [g["name"] for g in data["groups"]]
    assert "agents" in names
    agents_group = next(g for g in data["groups"] if g["name"] == "agents")
    paths = [f["path"] for f in agents_group["files"]]
    assert any("route_architect.log" in p for p in paths)


# ---------------------------------------------------------------------------
# /api/admin/logs/stream
# ---------------------------------------------------------------------------

def test_stream_requires_admin(client, tmp_logs):
    from utils.auth import create_access_token
    token = create_access_token(user_id=2, username="user", is_admin=False)
    res = client.get(f"/api/admin/logs/stream?token={token}&initial_lines=5")
    assert res.status_code == 403


def test_stream_path_traversal_rejected(client, tmp_logs):
    from utils.auth import create_access_token
    token = create_access_token(user_id=1, username="admin", is_admin=True)
    res = client.get(f"/api/admin/logs/stream?token={token}&sources=../../etc/passwd")
    assert res.status_code == 400


def test_stream_returns_initial_lines(client, tmp_logs, mocker):
    from utils.auth import create_access_token
    token = create_access_token(user_id=1, username="admin", is_admin=True)

    async def _no_tail(paths, filter_fn, poll_interval=0.5):
        return
        yield  # make it an async generator

    mocker.patch("routers.logs.tail_files", _no_tail)
    res = client.get(
        f"/api/admin/logs/stream?token={token}&sources=agents&initial_lines=5",
        headers={"Accept": "text/event-stream"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    assert "data:" in res.text
