"""FastAPI application — HTTP endpoints, SSE streaming, and startup configuration.

Planning-flow endpoints live in routers/planning.py; their shared helpers
(_find_and_stream_options, _fire_task, quota checks, etc.) live in
services/job_helpers.py to avoid circular imports.
"""
import asyncio
import json
import os
import re
import secrets
import time as _time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from models.travel_request import TravelRequest
from models.trip_leg import RegionPlan
from utils.auth import get_current_user, CurrentUser, verify_jwt_secret, hash_password
from utils.i18n import get_request_language, SUPPORTED_LANGUAGES, t as i18n_t
from utils.auth_db import admin_exists, create_user, assign_orphan_trips, get_user_by_username
from utils.migrations import run_migrations
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.logs import router as logs_router
from routers.feedback import router as feedback_router
from routers.planning import router as planning_router
from routers.accommodations import router as accommodations_router
from utils.debug_logger import debug_logger, LogLevel
from utils.route_edit_lock import acquire_edit_lock
from utils.maps_helper import geocode_google
from services.redis_store import redis_client, get_job, save_job, _InMemoryStore, _job_lang
from services.job_helpers import (
    _fire_task,
    _running_tasks,
    _TASK_TIMEOUT_SECONDS,
    _calc_route_geometry,
    _find_and_stream_options,
    _auto_confirm_regions,  # re-exported so `from main import _auto_confirm_regions` (orchestrator) keeps working
)


async def _periodic_subscriber_cleanup():
    """Bereinigt verwaiste SSE-Subscriber alle 10 Minuten."""
    while True:
        await asyncio.sleep(600)
        now = _time.time()
        stale = [
            jid for jid, qs in list(debug_logger._subscribers.items())
            if not qs  # leere Listen
        ]
        for jid in stale:
            debug_logger._subscribers.pop(jid, None)


# Active statuses that indicate a job is in progress and can become stuck.
_ACTIVE_JOB_STATUSES = frozenset((
    "building_route", "loading_accommodations", "selecting_accommodations",
    "accommodations_confirmed", "pending", "running",
))

# Max age in seconds before a job in an active status is declared stuck and terminated.
_STUCK_JOB_TIMEOUT_SECONDS = 2700  # 45 minutes


async def _periodic_stuck_job_reaper():
    """Marks zombie jobs (active status for >45 min) as failed every 5 minutes.

    Prevents jobs that crash without writing an error status from blocking
    the UI indefinitely. Runs independently of _running_tasks tracking so it
    also catches jobs whose worker process was killed.
    """
    import logging as _logging
    logger = _logging.getLogger("travelman")
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        now = _time.time()
        try:
            keys = redis_client.keys("job:*")
        except Exception as _redis_exc:
            logger.warning("Stuck-job reaper: Redis nicht erreichbar: %s", _redis_exc)
            continue
        for key in keys:
            try:
                raw = redis_client.get(key)
                if not raw:
                    continue
                job = json.loads(raw)
                if job.get("status") not in _ACTIVE_JOB_STATUSES:
                    continue
                started_at = job.get("created_at") or job.get("started_at")
                if started_at is None:
                    continue
                age = now - float(started_at)
                if age < _STUCK_JOB_TIMEOUT_SECONDS:
                    continue
                # Job has been stuck too long — mark as error.
                job_id = key.decode() if isinstance(key, bytes) else key
                job_id = job_id.removeprefix("job:")
                logger.error("Stuck job detected: %s (age %.0fs) — marking as error", job_id, age)
                job["status"] = "error"
                redis_client.set(key, json.dumps(job))
                try:
                    await debug_logger.push_event(
                        job_id, "job_error", None,
                        {"message": "Job wurde automatisch beendet (Timeout nach 45 Minuten)."},
                    )
                except Exception as _push_exc:
                    logger.warning("SSE push fehlgeschlagen im Stuck-Job-Reaper: %s", _push_exc)
            except Exception as exc:
                logger.warning("Stuck-job reaper error for key %s: %s", key, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown für gemeinsame Ressourcen."""
    cleanup_task = asyncio.create_task(_periodic_subscriber_cleanup())
    reaper_task = asyncio.create_task(_periodic_stuck_job_reaper())
    yield
    cleanup_task.cancel()
    reaper_task.cancel()
    from utils.http_session import close_session
    await close_session()


app = FastAPI(title="DetourAI API", version="1.0.0", lifespan=lifespan)

_CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,http://localhost:80,http://127.0.0.1"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept-Language"],
)


@app.middleware("http")
async def language_middleware(request: Request, call_next):
    """Extract Accept-Language and store on request.state for all endpoints."""
    accept_lang = request.headers.get("Accept-Language", "de")
    request.state.lang = get_request_language(accept_lang)
    response = await call_next(request)
    return response


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(feedback_router)
app.include_router(planning_router)
app.include_router(accommodations_router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging
    logger = logging.getLogger("uvicorn")
    # Log the raw request body for debugging
    try:
        body = await request.body()
        logger.error(f"Request body: {body.decode('utf-8', errors='replace')[:2000]}")
    except Exception as _body_exc:
        logger.warning("Request body konnte nicht gelesen werden: %s", _body_exc)
    errors = [
        {k: str(v) if not isinstance(v, (str, int, float, bool, list, tuple, type(None))) else v
         for k, v in e.items()}
        for e in exc.errors()
    ]
    logger.error(f"Validation error: {errors}")
    return JSONResponse(status_code=422, content={"detail": errors})


from utils.travel_db import _init_db, save_travel, list_travels, get_travel, delete_travel, update_travel, update_plan_json, set_share_token, get_travel_by_share_token
from utils.settings_store import (
    get_setting, async_get_all_settings, async_reset_section,
    validate_setting, set_setting, DEFAULTS, ALLOWED_MODELS,
)

# ── Startup: validate JWT secret, run DB migrations, bootstrap admin ──────────
verify_jwt_secret()

_default_data_dir = str(Path(__file__).parent.parent / "data")
_data_dir = os.getenv("DATA_DIR", _default_data_dir)
_db_path = os.path.join(_data_dir, "travels.db")
os.makedirs(_data_dir, exist_ok=True)
run_migrations(_db_path)
_init_db()

_admin_username = os.getenv("ADMIN_USERNAME", "")
_admin_password = os.getenv("ADMIN_PASSWORD", "")
if _admin_username and _admin_password:
    if not admin_exists():
        _admin_id = create_user(_admin_username, hash_password(_admin_password), is_admin=True)
    else:
        _u = get_user_by_username(_admin_username)
        _admin_id = _u["id"] if _u else 1
    assign_orphan_trips(_admin_id)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Serve frontend static files at / (must be mounted after all /api routes are defined)
# We add a root redirect here and mount static at the end of the file.




# ---------------------------------------------------------------------------
# Settings endpoints (SQLite key-value store)
# ---------------------------------------------------------------------------

class SettingsUpdateRequest(BaseModel):
    settings: dict[str, object]

class SettingsResetRequest(BaseModel):
    section: str = Field(pattern="^(agent|budget|api|geo|system|all)$")


@app.get("/api/settings")
async def api_get_settings(current_user: CurrentUser = Depends(get_current_user)):
    all_settings = await async_get_all_settings()
    api_keys = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google_maps": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "brave": bool(os.getenv("BRAVE_API_KEY")),
    }
    return {"settings": all_settings, "defaults": DEFAULTS, "api_keys": api_keys}


@app.put("/api/settings")
async def api_update_settings(body: SettingsUpdateRequest, current_user: CurrentUser = Depends(get_current_user)):
    errors = []
    for key, value in body.settings.items():
        err = validate_setting(key, value)
        if err:
            errors.append(err)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    for key, value in body.settings.items():
        # Coerce types to match defaults
        default = DEFAULTS[key]
        if isinstance(default, int) and not isinstance(default, bool):
            value = int(value)  # type: ignore[call-overload]
        elif isinstance(default, float):
            value = float(value)  # type: ignore[arg-type]
        set_setting(key, value)
    return {"saved": True, "count": len(body.settings)}


@app.post("/api/settings/reset")
async def api_reset_settings(body: SettingsResetRequest, current_user: CurrentUser = Depends(get_current_user)):
    count = await async_reset_section(body.section)
    return {"reset": True, "section": body.section, "deleted": count}


@app.get("/api/ollama/health")
async def ollama_health(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Check connectivity to the locally-configured Ollama LLM server."""
    import aiohttp
    endpoint = get_setting("system.ollama_endpoint") or "http://localhost:11434/v1/"
    # Convert the OpenAI-compatible /v1 URL to the native Ollama /api/tags endpoint
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    tags_url = base + "/api/tags"
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as resp:
                if resp.status != 200:
                    return {"status": "error", "detail": f"Ollama antwortete mit HTTP {resp.status}"}
                data = await resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "ok", "models": models, "endpoint": endpoint}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/api/maps-config")
async def get_maps_config():
    return {"api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")}


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools():
    return {}


@app.get("/health")
async def health():
    import logging as _logging
    # Check Redis connectivity — unhealthy if unreachable.
    try:
        keys = redis_client.keys("job:*")
        active_statuses = (
            "building_route", "loading_accommodations", "selecting_accommodations",
            "accommodations_confirmed", "pending", "running",
        )
        active = len([k for k in keys if json.loads(redis_client.get(k) or "{}").get("status") in active_statuses])
        redis_ok = True
    except Exception as _redis_exc:
        _logging.getLogger("travelman").warning("/health: Redis nicht erreichbar: %s", _redis_exc)
        active = 0
        redis_ok = False

    # Check for stuck background tasks (running longer than the timeout).
    now = _time.time()
    stuck_jobs = [jid for jid, started in _running_tasks.items() if now - started > _TASK_TIMEOUT_SECONDS]

    if not redis_ok or stuck_jobs:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "redis_ok": redis_ok,
                "active_jobs": active,
                "stuck_jobs": stuck_jobs,
            },
        )

    return {"status": "ok", "active_jobs": active, "running_tasks": len(_running_tasks)}


# ---------------------------------------------------------------------------
# Travel history endpoints (SQLite)
# ---------------------------------------------------------------------------

class SaveTravelRequest(BaseModel):
    plan: dict


class UpdateTravelRequest(BaseModel):
    custom_name: Optional[str] = None
    rating: Optional[int] = None


def _slugify(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-')[:50]


@app.get("/api/travels")
async def api_list_travels(current_user: CurrentUser = Depends(get_current_user)):
    travels = await list_travels(current_user.id)
    for t in travels:
        name = t.get("custom_name") or t.get("title") or ""
        t["slug"] = _slugify(name)
    return {"travels": travels}


@app.post("/api/travels", status_code=201)
async def api_save_travel(body: SaveTravelRequest, current_user: CurrentUser = Depends(get_current_user)):
    travel_id = await save_travel(body.plan, current_user.id)
    if travel_id is None:
        return {"saved": False, "id": None}
    return {"saved": True, "id": travel_id}


@app.patch("/api/travels/{travel_id}")
async def api_update_travel(travel_id: int, body: UpdateTravelRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Update custom name or rating for a saved travel."""
    updated = await update_travel(travel_id, current_user.id, body.custom_name, body.rating)
    if not updated:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))
    return {"updated": True, "id": travel_id}


@app.get("/api/travels/{travel_id}")
async def api_get_travel(travel_id: int, current_user: CurrentUser = Depends(get_current_user)):
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))
    return plan


@app.delete("/api/travels/{travel_id}")
async def api_delete_travel(travel_id: int, current_user: CurrentUser = Depends(get_current_user)):
    if not await delete_travel(travel_id, current_user.id):
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))
    return {"deleted": True, "id": travel_id}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replan
# Re-runs the full orchestrator (all agents, incl. TravelGuide + stündliche
# Tagespläne) for a saved trip, reusing the existing route + accommodations.
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/replan")
async def api_replan_travel(travel_id: int, current_user: CurrentUser = Depends(get_current_user)):
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    # Reconstruct TravelRequest from the saved plan
    # The plan must contain a "request" snapshot; fall back to deriving minimal fields.
    req_data = plan.get("request")
    if not req_data:
        # Build a minimal request from the plan itself
        stops = plan.get("stops", [])
        first_stop = stops[0] if stops else {}
        last_stop  = stops[-1] if stops else {}
        day_plans  = plan.get("day_plans", [])
        req_data = {
            "start_location":  plan.get("start_location", "Unbekannt"),
            "main_destination": last_stop.get("region", "Unbekannt"),
            "start_date":      "2026-01-01",
            "end_date":        "2026-01-10",
            "total_days":      len(day_plans) or 10,
            "adults":          2,
            "budget_chf":      plan.get("cost_estimate", {}).get("total_chf", 3000),
        }

    request_obj = TravelRequest(**req_data)

    # Rebuild pre_built_stops and pre_selected_accommodations from the saved plan
    pre_built_stops = []
    for stop in plan.get("stops", []):
        s = {k: v for k, v in stop.items()
             if k not in ("travel_guide", "further_activities", "top_activities",
                          "restaurants", "accommodation", "image_overview",
                          "image_mood", "image_customer")}
        pre_built_stops.append(s)

    pre_selected_accommodations = []
    for stop in plan.get("stops", []):
        if stop.get("accommodation"):
            pre_selected_accommodations.append({
                "stop_id": stop["id"],
                "option": stop["accommodation"],
            })

    # Create a new ephemeral job
    job_id = uuid.uuid4().hex
    job = {
        "status": "pending",
        "request": request_obj.model_dump(mode="json"),
        "selected_stops": pre_built_stops,
        "selected_accommodations": pre_selected_accommodations,
        "replan_source_id": travel_id,
        "user_id": current_user.id,
    }
    save_job(job_id, job)

    _fire_task("run_planning_job", job_id,
               pre_built_stops=pre_built_stops,
               pre_selected_accommodations=pre_selected_accommodations)

    return {"job_id": job_id, "status": "planning_started", "source_travel_id": travel_id}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replace-stop
# Replace a stop in a finished travel plan (manual location or search mode)
# ---------------------------------------------------------------------------

class ReplaceStopRequest(BaseModel):
    stop_id: int
    mode: str  # "manual" | "search"
    manual_location: Optional[str] = None
    manual_nights: Optional[int] = None
    hints: Optional[str] = None  # e.g. "mehr Strand", "weniger Fahrzeit"


class RemoveStopRequest(BaseModel):
    stop_id: int


class AddStopRequest(BaseModel):
    location: str
    insert_after_stop_id: int  # ID of stop after which to insert
    nights: int = 1


class ReorderStopsRequest(BaseModel):
    old_index: int
    new_index: int


class UpdateNightsRequest(BaseModel):
    stop_id: int
    nights: int  # 1-14


@app.post("/api/travels/{travel_id}/replace-stop")
async def api_replace_stop(travel_id: int, body: ReplaceStopRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Replace a stop in a finished travel plan: manual location or AI-searched options."""
    from agents.stop_options_finder import StopOptionsFinderAgent

    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    stop_index = next((i for i, s in enumerate(stops) if s.get("id") == body.stop_id), None)
    if stop_index is None:
        raise HTTPException(400, detail=i18n_t("error.stop_not_found", "de", stop_id=body.stop_id))

    old_stop = stops[stop_index]

    if body.mode == "manual":
        if not body.manual_location or not body.manual_location.strip():
            raise HTTPException(400, detail=i18n_t("error.location_empty", "de"))

        geo_result = await geocode_google(body.manual_location.strip())
        if not geo_result:
            raise HTTPException(400, detail=i18n_t("error.location_not_found", "de", location=body.manual_location))

        if not acquire_edit_lock(travel_id):
            raise HTTPException(409, detail=i18n_t("error.edit_in_progress", "de"))

        nights = body.manual_nights if body.manual_nights and body.manual_nights > 0 else old_stop.get("nights", 1)

        job_id = uuid.uuid4().hex
        job = {
            "status": "replacing",
            "travel_id": travel_id,
            "stop_index": stop_index,
            "new_region": body.manual_location.strip(),
            "new_country": "XX",
            "new_lat": geo_result[0],
            "new_lng": geo_result[1],
            "new_nights": nights,
            "request": plan.get("request", {}),
            "user_id": current_user.id,
        }
        save_job(job_id, job)
        _fire_task("replace_stop_job", job_id)

        return {"job_id": job_id, "status": "replacing"}

    elif body.mode == "search":
        req_data = plan.get("request", {})
        request = TravelRequest(**req_data)

        # Determine prev/next locations
        if stop_index > 0:
            prev_stop = stops[stop_index - 1]
            prev_location = f"{prev_stop['region']}, {prev_stop.get('country', '')}"
        else:
            prev_location = plan.get("start_location", "")

        if stop_index < len(stops) - 1:
            next_stop = stops[stop_index + 1]
            segment_target = f"{next_stop['region']}, {next_stop.get('country', '')}"
        else:
            segment_target = ""

        # Calc route geometry for the segment
        route_geo = {}
        if prev_location and segment_target:
            route_geo = await _calc_route_geometry(
                prev_location, segment_target, 1,
                request.max_drive_hours_per_day,
            )

        agent = StopOptionsFinderAgent(request, "search_" + uuid.uuid4().hex[:8])
        options, map_anchors, _, _ = await _find_and_stream_options(
            agent=agent,
            job_id="search_" + uuid.uuid4().hex[:8],
            selected_stops=[],
            stop_number=1,
            days_remaining=old_stop.get("nights", 2) + 2,
            route_could_be_complete=False,
            segment_target=segment_target,
            segment_index=0,
            segment_count=1,
            prev_location=prev_location,
            max_drive_hours=request.max_drive_hours_per_day,
            route_geometry=route_geo,
            extra_instructions=body.hints or "",
        )

        # Enrich options with Google Directions
        for opt in options:
            opt["nights"] = old_stop.get("nights", 1)

        job_id = uuid.uuid4().hex
        job = {
            "status": "awaiting_selection",
            "travel_id": travel_id,
            "stop_index": stop_index,
            "options": options,
            "request": req_data,
            "user_id": current_user.id,
            "hints": body.hints,
        }
        save_job(job_id, job)

        return {"job_id": job_id, "options": options, "map_anchors": map_anchors}

    else:
        raise HTTPException(400, detail=i18n_t("error.unknown_mode", "de"))


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/replace-stop-select
# Select one of the search options for stop replacement
# ---------------------------------------------------------------------------

class ReplaceStopSelectRequest(BaseModel):
    job_id: str
    option_index: int


@app.post("/api/travels/{travel_id}/replace-stop-select")
async def api_replace_stop_select(travel_id: int, body: ReplaceStopSelectRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Confirm one of the AI-searched replacement options and trigger the background replace job."""
    job = get_job(body.job_id)
    if job.get("travel_id") != travel_id:
        raise HTTPException(400, detail=i18n_t("error.job_not_travel", _job_lang(job)))

    options = job.get("options", [])
    if body.option_index < 0 or body.option_index >= len(options):
        raise HTTPException(400, detail=i18n_t("error.invalid_option_index", _job_lang(job)))

    selected = options[body.option_index]
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    stop_index = job["stop_index"]
    old_stop = stops[stop_index] if stop_index < len(stops) else {}
    nights = selected.get("nights", old_stop.get("nights", 1))

    new_job_id = uuid.uuid4().hex
    new_job = {
        "status": "replacing",
        "travel_id": travel_id,
        "stop_index": stop_index,
        "new_region": selected.get("region", ""),
        "new_country": selected.get("country", "XX"),
        "new_lat": selected.get("lat", 0),
        "new_lng": selected.get("lon", 0),
        "new_nights": nights,
        "request": job.get("request", plan.get("request", {})),
    }
    save_job(new_job_id, new_job)
    _fire_task("replace_stop_job", new_job_id)

    return {"job_id": new_job_id, "status": "replacing", "selected": selected}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/remove-stop
# Remove a stop from a finished travel plan
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/remove-stop")
async def api_remove_stop(travel_id: int, body: RemoveStopRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Remove a stop from a finished travel plan and queue a background job to update day plans."""
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    stop_index = next((i for i, s in enumerate(stops) if s.get("id") == body.stop_id), None)
    if stop_index is None:
        raise HTTPException(400, detail=i18n_t("error.stop_not_found", "de", stop_id=body.stop_id))
    if len(stops) <= 1:
        raise HTTPException(400, detail=i18n_t("error.min_one_stop", "de"))

    if not acquire_edit_lock(travel_id):
        raise HTTPException(409, detail=i18n_t("error.edit_in_progress", "de"))

    job_id = uuid.uuid4().hex
    job = {
        "status": "editing",
        "travel_id": travel_id,
        "operation": "remove",
        "stop_index": stop_index,
        "user_id": current_user.id,
    }
    save_job(job_id, job)
    _fire_task("remove_stop_job", job_id)
    return {"job_id": job_id, "status": "editing"}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/add-stop
# Add a new stop to a finished travel plan
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/add-stop")
async def api_add_stop(travel_id: int, body: AddStopRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Add a new geocoded stop after a given stop in a finished travel plan and queue a background job."""
    if not body.location or not body.location.strip():
        raise HTTPException(400, detail=i18n_t("error.location_empty", "de"))

    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    insert_after_index = next((i for i, s in enumerate(stops) if s.get("id") == body.insert_after_stop_id), None)
    if insert_after_index is None:
        raise HTTPException(400, detail=i18n_t("error.stop_not_found", "de", stop_id=body.insert_after_stop_id))

    geo_result = await geocode_google(body.location.strip())
    if not geo_result:
        raise HTTPException(400, detail=i18n_t("error.location_not_found", "de", location=body.location))

    if not acquire_edit_lock(travel_id):
        raise HTTPException(409, detail=i18n_t("error.edit_in_progress", "de"))

    job_id = uuid.uuid4().hex
    job = {
        "status": "editing",
        "travel_id": travel_id,
        "operation": "add",
        "insert_after_index": insert_after_index,
        "location_name": body.location.strip(),
        "lat": geo_result[0],
        "lng": geo_result[1],
        "nights": body.nights if body.nights and body.nights > 0 else 1,
        "user_id": current_user.id,
        "request": plan.get("request", {}),
    }
    save_job(job_id, job)
    _fire_task("add_stop_job", job_id)
    return {"job_id": job_id, "status": "editing"}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/reorder-stops
# Reorder stops in a finished travel plan
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/reorder-stops")
async def api_reorder_stops(travel_id: int, body: ReorderStopsRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Move a stop from old_index to new_index in a finished travel plan and queue a background job."""
    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    if body.old_index < 0 or body.old_index >= len(stops):
        raise HTTPException(400, detail=i18n_t("error.invalid_source_index", "de"))
    if body.new_index < 0 or body.new_index >= len(stops):
        raise HTTPException(400, detail=i18n_t("error.invalid_target_index", "de"))
    if body.old_index == body.new_index:
        raise HTTPException(400, detail=i18n_t("error.same_index", "de"))

    if not acquire_edit_lock(travel_id):
        raise HTTPException(409, detail=i18n_t("error.edit_in_progress", "de"))

    job_id = uuid.uuid4().hex
    job = {
        "status": "editing",
        "travel_id": travel_id,
        "operation": "reorder",
        "old_index": body.old_index,
        "new_index": body.new_index,
        "user_id": current_user.id,
    }
    save_job(job_id, job)
    _fire_task("reorder_stops_job", job_id)
    return {"job_id": job_id, "status": "editing"}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/update-nights
# Update nights for a stop and recalculate day plans
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/update-nights")
async def api_update_nights(travel_id: int, body: UpdateNightsRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Update the number of nights for a stop and queue a background job to recalculate day plans."""
    if body.nights < 1 or body.nights > 14:
        raise HTTPException(400, detail=i18n_t("error.nights_range", "de"))

    plan = await get_travel(travel_id, current_user.id)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))

    stops = plan.get("stops", [])
    stop_index = next((i for i, s in enumerate(stops) if s.get("id") == body.stop_id), None)
    if stop_index is None:
        raise HTTPException(400, detail=i18n_t("error.stop_not_found", "de", stop_id=body.stop_id))

    if not acquire_edit_lock(travel_id):
        raise HTTPException(409, detail=i18n_t("error.edit_in_progress", "de"))

    job_id = uuid.uuid4().hex
    job = {
        "status": "editing",
        "travel_id": travel_id,
        "operation": "update_nights",
        "stop_id": body.stop_id,
        "stop_index": stop_index,
        "nights": body.nights,
        "user_id": current_user.id,
    }
    save_job(job_id, job)
    _fire_task("update_nights_job", job_id)
    return {"job_id": job_id, "status": "editing"}


# ---------------------------------------------------------------------------
# POST /api/travels/{travel_id}/share — generate or regenerate share token
# ---------------------------------------------------------------------------

@app.post("/api/travels/{travel_id}/share")
async def api_share_travel(travel_id: int, current_user: CurrentUser = Depends(get_current_user)):
    token = secrets.token_urlsafe(16)
    ok = await set_share_token(travel_id, current_user.id, token)
    if not ok:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))
    return {"share_token": token, "share_url": f"/travel/{travel_id}?share={token}"}


# ---------------------------------------------------------------------------
# DELETE /api/travels/{travel_id}/share — revoke share link
# ---------------------------------------------------------------------------

@app.delete("/api/travels/{travel_id}/share")
async def api_unshare_travel(travel_id: int, current_user: CurrentUser = Depends(get_current_user)):
    ok = await set_share_token(travel_id, current_user.id, None)
    if not ok:
        raise HTTPException(404, detail=i18n_t("error.travel_not_found", "de", travel_id=travel_id))
    return {"status": "unshared"}


# ---------------------------------------------------------------------------
# GET /api/shared/{token} — public access, NO auth dependency
# ---------------------------------------------------------------------------

@app.get("/api/shared/{token}")
async def api_get_shared_travel(token: str):
    plan = await get_travel_by_share_token(token)
    if plan is None:
        raise HTTPException(404, detail=i18n_t("error.shared_link_invalid", "de"))
    return plan



# ---------------------------------------------------------------------------
# Serve frontend static files
# Must be registered AFTER all /api/* routes so they take priority.
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

if FRONTEND_DIR.exists():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="frontend-js")
    app.mount("/i18n", StaticFiles(directory=str(FRONTEND_DIR / "i18n")), name="frontend-i18n")
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend-assets")

    # SPA catch-all: any non-API, non-static path → index.html for client-side routing
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # Serve actual static files if they exist (css, images, etc.)
        file = FRONTEND_DIR / path
        if file.is_file():
            return FileResponse(str(file))
        # Otherwise serve index.html for client-side router
        return FileResponse(str(FRONTEND_DIR / "index.html"))
