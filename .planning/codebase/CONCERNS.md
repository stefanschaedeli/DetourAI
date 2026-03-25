# Codebase Concerns

**Analysis Date:** 2026-03-25

## Security

**Google Maps API Key Exposed to Frontend:**
- Risk: The `/api/maps-config` endpoint (line 2021-2023 in `backend/main.py`) returns the raw `GOOGLE_MAPS_API_KEY` to any unauthenticated caller. This key is used for Geocoding, Directions, and Places APIs on the backend (billable). Anyone can extract it and abuse it.
- Files: `backend/main.py:2021-2023`, `frontend/js/maps.js`
- Current mitigation: None (endpoint has no auth dependency).
- Recommendations: Restrict the Google API key to specific referrers in Google Cloud Console. Add authentication to the endpoint or proxy all Maps requests through the backend.

**No Job Ownership Verification on Most Endpoints:**
- Risk: Most endpoints (`/api/select-stop/{job_id}`, `/api/recompute-options/{job_id}`, `/api/confirm-route/{job_id}`, `/api/start-accommodations/{job_id}`, `/api/confirm-accommodations/{job_id}`, `/api/select-accommodation/{job_id}`, `/api/start-planning/{job_id}`, `/api/patch-job/{job_id}`, `/api/result/{job_id}`, `/api/generate-output/{job_id}/{file_type}`) call `get_job(job_id)` without verifying `job["user_id"] == current_user.id`. Only the SSE stream endpoint (`/api/progress/{job_id}`) checks ownership. Any authenticated user can access and modify any other user's active job if they know/guess the job_id.
- Files: `backend/main.py` -- lines 1124, 1377, 1464, 1596, 1671, 1686, 1729, 1793, 1927, 1937
- Current mitigation: Job IDs are UUIDs (hard to guess), but this is security through obscurity.
- Recommendations: Add an `_assert_job_owner(job, current_user)` helper and call it after every `get_job()`.

**Settings Endpoints Not Admin-Restricted:**
- Risk: `/api/settings` PUT and `/api/settings/reset` POST only require `get_current_user` (any authenticated user), not `require_admin`. Any user can change agent models, budget percentages, retry counts, and system settings.
- Files: `backend/main.py:1991-2014`
- Current mitigation: None.
- Recommendations: Change dependency to `Depends(require_admin)` for PUT/POST settings endpoints.

**Unauthenticated `/api/log` Endpoint:**
- Risk: The `/api/log` POST endpoint (for frontend error reporting) has no authentication. An attacker could flood the server with log entries, filling disk space.
- Files: `backend/main.py` (search for `/api/log`)
- Current mitigation: Message truncated to 5000 chars in `frontend/js/api.js:281`.
- Recommendations: Add rate limiting or basic auth check.

**XSS Surface Area:**
- Risk: The frontend uses `innerHTML` assignment in 68 locations across 11 JS files. While `esc()` is used (172 occurrences across 9 files), the high `innerHTML` count creates risk of missed escaping.
- Files: All `frontend/js/*.js` files, especially `guide.js` (14 innerHTML, 84 esc), `route-builder.js` (17 innerHTML, 30 esc)
- Current mitigation: `esc()` function used for user-content interpolation.
- Recommendations: Audit each `innerHTML` assignment to verify all dynamic content passes through `esc()`. Consider switching to `textContent` where HTML is not needed.

## Performance

**`_InMemoryStore` Has No TTL/Eviction:**
- Problem: The in-memory Redis fallback (`backend/main.py:47-63`) ignores the TTL parameter in `setex()`. Jobs accumulate indefinitely and are never evicted, causing memory growth.
- Files: `backend/main.py:47-63`
- Cause: `setex` stores the value but discards the TTL argument entirely.
- Improvement path: Add a dict of expiry timestamps and check on `get()`, or use a bounded dict with LRU eviction.

**Health Endpoint Scans All Redis Keys:**
- Problem: `/health` calls `redis_client.keys("job:*")` and deserializes every job to count active ones. This is O(N) in the number of jobs and blocks Redis.
- Files: `backend/main.py:2031-2040`
- Cause: Using `KEYS` pattern scan + full JSON parse per key.
- Improvement path: Maintain a counter in Redis (increment on job create, decrement on complete/error) or use `SCAN` with a separate status index.

**Monolithic `main.py` (2614 Lines):**
- Problem: All 25+ API endpoints, helper functions, request models, and route geometry logic live in a single file. This slows IDE navigation and increases merge conflicts.
- Files: `backend/main.py` (2614 lines)
- Improvement path: Extract endpoint groups into FastAPI routers (auth and admin already extracted to `backend/routers/`). Candidates: route-building endpoints, accommodation endpoints, travel CRUD, settings.

**SQLite Connection Per Query (No Pooling):**
- Problem: Both `backend/utils/travel_db.py:13-16` and `backend/utils/auth_db.py:19-23` create a new `sqlite3.connect()` on every function call. While SQLite connections are lightweight, this means no connection reuse and no WAL mode by default.
- Files: `backend/utils/travel_db.py:13-16`, `backend/utils/auth_db.py:19-23`
- Cause: Each function opens and closes its own connection.
- Improvement path: Use a connection pool or a single long-lived connection with proper locking for the write path. Enable WAL mode for concurrent reads.

**Unbounded Parallel API Calls in Orchestrator:**
- Problem: The orchestrator launches `asyncio.gather(*tasks)` for all stops simultaneously (`backend/orchestrator.py:268-273`). With 10+ stops, this fires 30+ parallel Claude API calls (activities + restaurants + images per stop), potentially hitting rate limits.
- Files: `backend/orchestrator.py:268-273`
- Current mitigation: `call_with_retry()` handles 429 errors with exponential backoff.
- Improvement path: Use `asyncio.Semaphore` to limit concurrent Claude API calls (e.g., max 5).

## Reliability

**Broad `except Exception` / `except:` Swallowing Errors:**
- Problem: Many utility functions catch all exceptions and return empty results silently (e.g., `[]`, `None`, `{}`). This makes debugging difficult when external APIs change behavior or credentials expire.
- Files:
  - `backend/utils/maps_helper.py:51,83,119` -- geocoding/directions silently return None/zeros
  - `backend/utils/google_places.py:57,83,135,179` -- all Places API calls silently fail
  - `backend/utils/brave_search.py:39,71` -- search silently returns `[]`
  - `backend/utils/weather.py:77,120` -- weather silently returns `[]`/`None`
  - `backend/utils/currency.py:89` -- ECB rates fetch silently fails
  - `backend/utils/wikipedia.py:29,98` -- Wikipedia enrichment silently fails
- Impact: When a Google API key expires, the system silently produces trips with no coordinates, no directions, no images -- and no error is logged.
- Fix approach: Log warnings in catch blocks (at least `LogLevel.WARNING`) before returning fallback values. Distinguish between network errors (retry-worthy) and auth errors (immediate alert).

**No Timeout on Orchestrator Overall Execution:**
- Problem: A planning job has no global timeout. If an agent hangs (e.g., Claude returns a streaming response that never completes), the Celery task runs indefinitely.
- Files: `backend/orchestrator.py:64-98`, `backend/tasks/run_planning_job.py:94-97`
- Current mitigation: Individual HTTP calls have 8-10s timeouts; Anthropic SDK has its own timeout.
- Fix approach: Add `asyncio.wait_for(orchestrator.run(...), timeout=600)` in the task runner.

**Race Condition in Redis Job State:**
- Problem: Multiple endpoints read a job from Redis, modify it in Python, then write back. If two requests arrive nearly simultaneously (e.g., rapid clicking), the second read may get stale state and overwrite the first write.
- Files: `backend/main.py` -- pattern: `job = get_job(job_id)` ... modify ... `save_job(job_id, job)`
- Current mitigation: Frontend UI generally prevents concurrent requests via loading states.
- Fix approach: Use Redis transactions (`WATCH`/`MULTI`) or optimistic locking with a version field.

**`_InMemoryStore` Not Thread-Safe:**
- Problem: The in-memory fallback store uses a plain Python `dict` without locks. If `asyncio.ensure_future` tasks and request handlers access it concurrently, dict mutations could corrupt state.
- Files: `backend/main.py:47-63`
- Fix approach: Use `threading.Lock` or switch to `asyncio`-aware data structures.

## Maintainability

**Duplicated `_get_store()` Pattern:**
- Issue: The pattern of importing `redis_client` from `main` with a fallback is duplicated in three places.
- Files: `backend/orchestrator.py:27-33`, `backend/tasks/run_planning_job.py:12-19`, `backend/tasks/replace_stop_job.py:12-19`
- Fix approach: Extract into a shared `utils/store.py` module.

**Inline Migrations in `_init_db()`:**
- Issue: `backend/utils/travel_db.py:42-58` uses try/except ALTER TABLE for migrations. This approach does not scale and duplicates the migration logic in `backend/utils/migrations.py`.
- Files: `backend/utils/travel_db.py:42-58`, `backend/utils/migrations.py`
- Fix approach: Remove inline migrations from `_init_db()` and rely solely on `migrations.py`.

**Agent Boilerplate Duplication:**
- Issue: Every agent (`stop_options_finder.py`, `accommodation_researcher.py`, `activities_agent.py`, `restaurants_agent.py`, `day_planner.py`, `travel_guide_agent.py`, `region_planner.py`, `trip_analysis_agent.py`) follows the same pattern: `__init__` with `get_client()` + `get_model()`, prompt building, `call_with_retry()`, `parse_agent_json()`. There is no base class.
- Files: All files in `backend/agents/`
- Fix approach: Create a `BaseAgent` class that handles client creation, model selection, retry, JSON parsing, and token accumulation. Subclasses only define prompt building and result extraction.

**`fetch_unsplash_images()` is a Dead Stub:**
- Issue: `backend/utils/image_fetcher.py:4-6` always returns `{None, None, None}`. It is still called from `backend/orchestrator.py:265,318-320` on every stop (including in a loop for further_activities), wasting async overhead.
- Files: `backend/utils/image_fetcher.py:4-6`, `backend/orchestrator.py:265,318-320`
- Fix approach: Remove the stub and all call sites, or replace with actual `fetch_place_images()` calls.

## Scalability

**SQLite as Primary Database:**
- Current capacity: Single-file database at `data/travels.db` handles both user/auth tables and travel data.
- Limit: SQLite supports only one concurrent writer. Under load with multiple Celery workers saving travel results simultaneously, writes will serialize and potentially timeout.
- Files: `backend/utils/travel_db.py`, `backend/utils/auth_db.py`
- Scaling path: Migrate to PostgreSQL for concurrent write support. The schema is simple enough that migration would be straightforward.

**Redis as Single Point of Failure:**
- Current capacity: All active job state lives only in Redis with 24h TTL. No persistence guarantee.
- Limit: Redis restart loses all in-progress jobs. No retry or recovery mechanism exists.
- Files: `backend/main.py:41,220`, `backend/orchestrator.py:42`
- Scaling path: Enable Redis AOF persistence. Consider storing job checkpoints in SQLite for recovery.

**Single aiohttp Session (Global Singleton):**
- Current: `backend/utils/http_session.py` uses a single `aiohttp.ClientSession` with `limit=100` connections, `limit_per_host=10`.
- Limit: With many concurrent jobs making Google API calls, the per-host limit (10) could become a bottleneck for `maps.googleapis.com`.
- Files: `backend/utils/http_session.py:17-19`
- Scaling path: Increase `limit_per_host` or use separate sessions per external service.

## Technical Debt

**Hardcoded Model Name in StopOptionsFinderAgent:**
- Issue: `backend/agents/stop_options_finder.py:33` passes `"claude-haiku-4-5"` as the production model to `get_model()`. According to CLAUDE.md, this agent should use `claude-sonnet-4-5` in production. The agent always uses Haiku regardless of TEST_MODE.
- Files: `backend/agents/stop_options_finder.py:33`
- Fix: Change to `get_model("claude-sonnet-4-5", AGENT_KEY)`.

**Inline Pydantic Model Definitions in `main.py`:**
- Issue: Several request models (`RecomputeRequest`, `PatchJobRequest`, `SettingsUpdateRequest`, `SettingsResetRequest`, `SaveTravelRequest`, `UpdateTravelRequest`, `RundreiseModeRequest`) are defined inline in `main.py` instead of in `backend/models/`.
- Files: `backend/main.py:457-458,1458-1461,1973-1977,2047-2048,2051-2052`
- Fix: Move to appropriate model files in `backend/models/`.

**`user_id` Fallback to 1 in Tasks:**
- Issue: Both `backend/tasks/run_planning_job.py:34` and `backend/tasks/replace_stop_job.py:41` use `job.get("user_id", 1)` as a fallback. This silently assigns trips to user ID 1 (admin) if the user_id is somehow missing.
- Files: `backend/tasks/run_planning_job.py:34`, `backend/tasks/replace_stop_job.py:41`
- Fix: Fail explicitly if `user_id` is not set rather than silently defaulting.

## Test Coverage Gaps

**No Tests for Job State Machine:**
- What's not tested: The multi-step flow of init-job -> plan-trip -> select-stop -> confirm-route -> start-accommodations -> confirm-accommodations -> start-planning is not tested end-to-end.
- Files: `backend/main.py` (all route-building endpoints)
- Risk: State transitions between phases could break silently. The `segment_budget`, `segment_index`, `leg_index` tracking is complex and error-prone.
- Priority: High

**No Tests for Authorization/Ownership:**
- What's not tested: No test verifies that user A cannot access user B's job or travel.
- Files: `backend/tests/test_endpoints.py`, `backend/tests/test_auth.py`
- Risk: Authorization bypass on job endpoints goes undetected.
- Priority: High

**No Integration Tests for External APIs:**
- What's not tested: Google Maps, Brave Search, Open-Meteo, and ECB currency API integrations have no tests (not even with mocked responses).
- Files: `backend/utils/maps_helper.py`, `backend/utils/google_places.py`, `backend/utils/brave_search.py`, `backend/utils/weather.py`, `backend/utils/currency.py`
- Risk: Changes to API response formats or error handling break silently.
- Priority: Medium

**No Frontend Tests:**
- What's not tested: All 14 JavaScript modules have zero automated tests. The route builder, accommodation selection, and SSE progress handling are untested.
- Files: All `frontend/js/*.js` files
- Risk: UI regressions go undetected.
- Priority: Medium

---

*Concerns audit: 2026-03-25*
