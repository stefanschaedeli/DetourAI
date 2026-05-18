"""Admin log viewer — file discovery and SSE live tail of backend log files."""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional, List, Set, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from utils.auth import CurrentUser, get_current_user_sse, require_admin
from utils.debug_logger import LOGS_DIR
from utils.log_reader import matches_filters, parse_log_line, read_last_n_lines, tail_files

router = APIRouter(prefix="/api/admin/logs", tags=["admin-logs"])

_GROUPS = ("agents", "orchestrator", "api", "frontend")
_MAX_INITIAL = 5000
_DEFAULT_INITIAL = 500


def _resolve_paths(sources_csv: str) -> List[Path]:
    """Resolve source CSV to a list of validated absolute file paths.

    Raises HTTP 400 if any path escapes LOGS_DIR.
    Sources can be group names (agents/orchestrator/api/frontend) or a single
    relative file path.
    """
    base = LOGS_DIR.resolve()
    parts = [s.strip() for s in sources_csv.split(",") if s.strip()]
    if not parts:
        parts = list(_GROUPS)

    paths: List[Path] = []
    for part in parts:
        if part in _GROUPS:
            group_dir = base / part
            if group_dir.is_dir():
                paths.extend(p for p in sorted(group_dir.iterdir()) if p.suffix == ".log")
        else:
            try:
                candidate = (base / part).resolve()
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Dateipfad")
            if not candidate.is_relative_to(base):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Dateipfad")
            if not candidate.is_file():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Datei nicht gefunden")
            paths.append(candidate)

    return paths


@router.get("/files")
async def list_log_files(admin: CurrentUser = Depends(require_admin)) -> dict:
    """Return a grouped tree of log files under LOGS_DIR."""
    base = LOGS_DIR.resolve()
    groups = []
    for group_name in _GROUPS:
        group_dir = base / group_name
        if not group_dir.is_dir():
            continue
        files = []
        base_files: Dict[str, dict] = {}
        for p in sorted(group_dir.iterdir()):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base))
            st = p.stat()
            if p.suffix == ".log" and "." not in p.stem:
                base_files[p.stem] = {
                    "path": rel,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "rotations": [],
                }
            elif ".log." in p.name:
                stem = p.name.split(".log.")[0]
                if stem in base_files:
                    base_files[stem]["rotations"].append({"path": rel, "size": st.st_size, "mtime": st.st_mtime})
                else:
                    files.append({"path": rel, "size": st.st_size, "mtime": st.st_mtime, "rotations": []})
        files.extend(base_files.values())
        groups.append({"name": group_name, "files": files})
    return {"groups": groups}


@router.get("/stream")
async def stream_logs(
    request: Request,
    token: Optional[str] = Query(default=None),
    sources: str = Query(default=",".join(_GROUPS)),
    levels: str = Query(default=""),
    job_id: str = Query(default=""),
    search: str = Query(default=""),
    initial_lines: int = Query(default=_DEFAULT_INITIAL, ge=1, le=_MAX_INITIAL),
) -> EventSourceResponse:
    """SSE endpoint: emit last initial_lines lines then tail matching log files live."""
    user = await get_current_user_sse(request, token)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Zugriff")

    paths = _resolve_paths(sources)
    level_set: Set[str] = {l.strip().upper() for l in levels.split(",") if l.strip()} if levels else set()
    filter_fn = lambda e: matches_filters(e, levels=level_set, job_id=job_id, search=search)

    async def event_generator():
        snapshot: List[dict] = []
        for p in paths:
            for raw in read_last_n_lines(p, initial_lines):
                entry = parse_log_line(raw)
                if entry and filter_fn(entry):
                    snapshot.append(entry)
        snapshot.sort(key=lambda e: (e["ts"] or ""))
        for entry in snapshot[-initial_lines:]:
            yield {"event": "log", "data": json.dumps(entry)}

        keepalive_counter = 0
        async for entry in tail_files(paths, filter_fn):
            if await request.is_disconnected():
                break
            yield {"event": "log", "data": json.dumps(entry)}
            keepalive_counter += 1
            if keepalive_counter >= 30:
                keepalive_counter = 0
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(event_generator())
