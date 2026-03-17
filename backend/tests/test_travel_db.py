import asyncio
import json
import os
import pytest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

USER_ID = 1  # synthetic user_id for all travel_db tests


@pytest.fixture(autouse=True)
def use_tmp_db(tmp_path, monkeypatch):
    """Redirect DB to a temp directory for each test."""
    import utils.travel_db as tdb
    monkeypatch.setattr(tdb, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(tdb, 'DB_PATH', tmp_path / 'travels.db')
    tdb._init_db()
    yield


def _sample_plan(job_id: str = "abc123") -> dict:
    return {
        "job_id": job_id,
        "start_location": "Liestal",
        "stops": [{"region": "Annecy", "id": 1}],
        "day_plans": [{}, {}],
        "cost_estimate": {"total_chf": 1200.0},
    }


# ---------------------------------------------------------------------------
# save_travel
# ---------------------------------------------------------------------------

def test_save_returns_id():
    from utils.travel_db import _sync_save
    plan = _sample_plan()
    row_id = _sync_save(plan, USER_ID)
    assert isinstance(row_id, int)
    assert row_id > 0


def test_save_duplicate_ignored():
    from utils.travel_db import _sync_save
    plan = _sample_plan("dup_job")
    first  = _sync_save(plan, USER_ID)
    second = _sync_save(plan, USER_ID)  # same job_id
    assert first is not None
    assert second is None  # duplicate silently skipped


# ---------------------------------------------------------------------------
# list_travels
# ---------------------------------------------------------------------------

def test_list_empty():
    from utils.travel_db import _sync_list
    assert _sync_list(USER_ID) == []


def test_list_returns_newest_first():
    from utils.travel_db import _sync_save, _sync_list
    _sync_save(_sample_plan("job_a"), USER_ID)
    _sync_save(_sample_plan("job_b"), USER_ID)
    rows = _sync_list(USER_ID)
    assert len(rows) == 2
    # newest (job_b) should be first (ORDER BY id DESC)
    assert rows[0]["job_id"] == "job_b"
    assert rows[1]["job_id"] == "job_a"


def test_list_scoped_to_user():
    """Trips saved by user 1 must not appear for user 2."""
    from utils.travel_db import _sync_save, _sync_list
    _sync_save(_sample_plan("job_u1"), USER_ID)
    assert _sync_list(2) == []
    assert len(_sync_list(USER_ID)) == 1


# ---------------------------------------------------------------------------
# get_travel
# ---------------------------------------------------------------------------

def test_get_returns_plan():
    from utils.travel_db import _sync_save, _sync_get
    plan = _sample_plan("get_job")
    row_id = _sync_save(plan, USER_ID)
    result = _sync_get(row_id, USER_ID)
    assert result is not None
    assert result["job_id"] == "get_job"


def test_get_not_found():
    from utils.travel_db import _sync_get
    assert _sync_get(9999, USER_ID) is None


def test_get_wrong_user_returns_none():
    from utils.travel_db import _sync_save, _sync_get
    row_id = _sync_save(_sample_plan("owned"), USER_ID)
    assert _sync_get(row_id, 2) is None  # user 2 cannot access user 1's trip


# ---------------------------------------------------------------------------
# delete_travel
# ---------------------------------------------------------------------------

def test_delete_removes_row():
    from utils.travel_db import _sync_save, _sync_delete, _sync_list
    row_id = _sync_save(_sample_plan("del_job"), USER_ID)
    deleted = _sync_delete(row_id, USER_ID)
    assert deleted is True
    assert _sync_list(USER_ID) == []


def test_delete_not_found():
    from utils.travel_db import _sync_delete
    assert _sync_delete(9999, USER_ID) is False


def test_delete_wrong_user_fails():
    from utils.travel_db import _sync_save, _sync_delete, _sync_list
    row_id = _sync_save(_sample_plan("protected"), USER_ID)
    assert _sync_delete(row_id, 2) is False  # user 2 cannot delete user 1's trip
    assert len(_sync_list(USER_ID)) == 1


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

def test_async_save_and_get():
    from utils.travel_db import save_travel, get_travel, list_travels

    async def run():
        plan = _sample_plan("async_job")
        row_id = await save_travel(plan, USER_ID)
        assert row_id is not None
        result = await get_travel(row_id, USER_ID)
        assert result["job_id"] == "async_job"
        rows = await list_travels(USER_ID)
        assert len(rows) == 1

    asyncio.run(run())
