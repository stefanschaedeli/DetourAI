"""
Tests for authentication utilities and endpoints.
Covers: password hashing, JWT creation/validation, auth DB CRUD, login/refresh/logout/me.
"""
import asyncio
import os
import sys
import pytest
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Ensure JWT_SECRET is set before importing auth modules
os.environ["JWT_SECRET"] = "test_secret_that_is_exactly_32chars!"


TEST_JWT_SECRET = "test_secret_that_is_exactly_32chars!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_jwt_secret(monkeypatch):
    """Ensure the in-memory JWT_SECRET constant is set for every test."""
    import utils.auth as _auth_mod
    monkeypatch.setattr(_auth_mod, "JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def use_tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a temp directory for each test."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # Run migrations to create the schema
    from utils.migrations import run_migrations
    db_path = str(tmp_path / "travels.db")
    run_migrations(db_path)
    yield


@pytest.fixture
def mock_redis(mocker):
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.get.return_value = None
    mock.setex.return_value = True
    mock.keys.return_value = []
    mocker.patch('main.redis_client', mock)
    return mock


@pytest.fixture
def client(mock_redis, mocker):
    """FastAPI TestClient with auth bypassed for non-auth tests."""
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def auth_client(mock_redis):
    """TestClient that uses real auth (DB-backed users, real JWT)."""
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def test_user(tmp_path):
    """Create a regular user in the DB and return their credentials."""
    from utils.auth import hash_password
    from utils.auth_db import create_user
    uid = create_user("testuser", hash_password("password123"), is_admin=False)
    return {"id": uid, "username": "testuser", "password": "password123"}


@pytest.fixture
def admin_user(tmp_path):
    """Create an admin user in the DB and return their credentials."""
    from utils.auth import hash_password
    from utils.auth_db import create_user
    uid = create_user("admin", hash_password("adminpass!"), is_admin=True)
    return {"id": uid, "username": "admin", "password": "adminpass!"}


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_and_verify_password():
    from utils.auth import hash_password, verify_password
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"
    assert verify_password("mysecret", hashed)
    assert not verify_password("wrongpass", hashed)


def test_different_hashes_for_same_password():
    from utils.auth import hash_password
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # Argon2 uses random salt


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def test_create_and_decode_access_token():
    from utils.auth import create_access_token, decode_access_token
    token = create_access_token(1, "alice", False)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.sub == 1
    assert payload.username == "alice"
    assert payload.is_admin is False


def test_decode_invalid_token_returns_none():
    from utils.auth import decode_access_token
    result = decode_access_token("not.a.valid.token")
    assert result is None


def test_create_admin_token():
    from utils.auth import create_access_token, decode_access_token
    token = create_access_token(42, "boss", True)
    payload = decode_access_token(token)
    assert payload.is_admin is True
    assert payload.sub == 42


# ---------------------------------------------------------------------------
# Auth DB — users
# ---------------------------------------------------------------------------

def test_create_and_get_user():
    from utils.auth_db import create_user, get_user_by_username, get_user_by_id
    uid = create_user("bob", "hash123", is_admin=False)
    assert uid > 0

    user_by_name = get_user_by_username("bob")
    assert user_by_name is not None
    assert user_by_name["username"] == "bob"
    assert user_by_name["password_hash"] == "hash123"
    assert user_by_name["is_admin"] == 0

    user_by_id = get_user_by_id(uid)
    assert user_by_id is not None
    assert user_by_id["username"] == "bob"


def test_get_user_not_found():
    from utils.auth_db import get_user_by_username, get_user_by_id
    assert get_user_by_username("ghost") is None
    assert get_user_by_id(9999) is None


def test_list_users():
    from utils.auth_db import create_user, list_users
    create_user("u1", "h1")
    create_user("u2", "h2")
    users = list_users()
    assert len(users) == 2
    usernames = {u["username"] for u in users}
    assert "u1" in usernames and "u2" in usernames


def test_delete_user():
    from utils.auth_db import create_user, delete_user, get_user_by_id
    uid = create_user("todelete", "h")
    assert delete_user(uid) is True
    assert get_user_by_id(uid) is None
    assert delete_user(9999) is False


def test_update_password():
    from utils.auth_db import create_user, update_password, get_user_by_username
    uid = create_user("pwuser", "oldhash")
    assert update_password(uid, "newhash") is True
    user = get_user_by_username("pwuser")
    assert user["password_hash"] == "newhash"


# ---------------------------------------------------------------------------
# Auth DB — refresh tokens
# ---------------------------------------------------------------------------

def test_store_and_validate_refresh_token():
    from utils.auth_db import create_user, store_refresh_token, validate_and_rotate_refresh_token
    uid = create_user("rtuser", "h")
    store_refresh_token(uid, "rawtoken123")
    result = validate_and_rotate_refresh_token("rawtoken123")
    assert result == uid


def test_refresh_token_rotated_on_use():
    """Token is deleted after validation (rotation), so second use fails."""
    from utils.auth_db import create_user, store_refresh_token, validate_and_rotate_refresh_token
    uid = create_user("rotuser", "h")
    store_refresh_token(uid, "rawtoken456")
    assert validate_and_rotate_refresh_token("rawtoken456") == uid
    assert validate_and_rotate_refresh_token("rawtoken456") is None  # already consumed


def test_invalid_refresh_token_returns_none():
    from utils.auth_db import validate_and_rotate_refresh_token
    assert validate_and_rotate_refresh_token("nonexistent") is None


def test_delete_refresh_token():
    from utils.auth_db import create_user, store_refresh_token, validate_and_rotate_refresh_token, delete_refresh_token
    uid = create_user("delrt", "h")
    store_refresh_token(uid, "tokenToDelete")
    delete_refresh_token("tokenToDelete")
    assert validate_and_rotate_refresh_token("tokenToDelete") is None


# ---------------------------------------------------------------------------
# Auth endpoints — login
# ---------------------------------------------------------------------------

def test_login_success(auth_client, test_user):
    r = auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # HTTP-only refresh cookie should be set
    assert "travelman_refresh" in r.cookies


def test_login_wrong_password(auth_client, test_user):
    r = auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": "wrongpassword",
    })
    assert r.status_code == 401


def test_login_unknown_user(auth_client):
    r = auth_client.post("/api/auth/login", json={
        "username": "nobody",
        "password": "anything",
    })
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth endpoints — /me
# ---------------------------------------------------------------------------

def test_me_returns_user_info(auth_client, test_user):
    # Login first
    login_r = auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    token = login_r.json()["access_token"]

    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == test_user["username"]
    assert data["is_admin"] is False


def test_me_requires_auth(auth_client):
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth endpoints — refresh
# ---------------------------------------------------------------------------

def test_refresh_issues_new_token(auth_client, test_user):
    login_r = auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    assert login_r.status_code == 200

    r = auth_client.post("/api/auth/refresh")
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data


def test_refresh_no_cookie_returns_401(auth_client):
    # Fresh client with no cookie
    from main import app
    from fastapi.testclient import TestClient
    fresh_client = TestClient(app, cookies={})
    r = fresh_client.post("/api/auth/refresh")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Auth endpoints — logout
# ---------------------------------------------------------------------------

def test_logout_clears_cookie(auth_client, test_user):
    auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    r = auth_client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Protected endpoint — requires valid token
# ---------------------------------------------------------------------------

def test_protected_endpoint_without_token(auth_client):
    r = auth_client.get("/api/travels")
    assert r.status_code == 401


def test_protected_endpoint_with_token(auth_client, test_user):
    login_r = auth_client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    token = login_r.json()["access_token"]

    r = auth_client.get("/api/travels", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
