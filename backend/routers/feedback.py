"""Feedback router — submit user feedback as GitHub Issues with optional screenshot upload."""
from __future__ import annotations

import base64
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from utils.auth import get_current_user, CurrentUser
from utils.http_session import get_session
from utils.debug_logger import debug_logger, LogLevel

router = APIRouter(prefix="/api", tags=["feedback"])

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.getenv("GITHUB_REPO", "")
GITHUB_API = "https://api.github.com"

# Simple in-memory rate limit: user_id → last submission timestamp
_last_feedback: dict[int, float] = {}
_COOLDOWN_SECONDS = 300  # 5 minutes


class FeedbackRequest(BaseModel):
    text: str = Field(min_length=10, max_length=5000)
    screenshot: Optional[str] = None  # base64 PNG without data: prefix
    category: str = Field(default="general", pattern="^(bug|vorschlag|general)$")


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


async def _upload_screenshot(screenshot_b64: str, timestamp: str) -> Optional[str]:
    """Upload screenshot to repo via GitHub Contents API, return download URL."""
    path = f"feedback-screenshots/{timestamp}.png"
    session = await get_session()

    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": f"feedback: screenshot {timestamp}",
        "content": screenshot_b64,
        "branch": "main",
    }

    async with session.put(url, json=payload, headers=_github_headers()) as resp:
        if resp.status in (200, 201):
            data = await resp.json()
            return data.get("content", {}).get("download_url")
        debug_logger.log(
            LogLevel.WARNING,
            f"Screenshot-Upload fehlgeschlagen: HTTP {resp.status}",
            agent="API",
        )
        return None


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a GitHub Issue from user feedback, optionally attaching a screenshot.

    Enforces a per-user cooldown of 5 minutes between submissions.
    Requires GITHUB_TOKEN and GITHUB_REPO environment variables to be set.
    Returns {"ok": True, "issue_url": "..."} on success.
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(503, detail="Feedback-System nicht konfiguriert.")

    # Rate limit
    now = time.time()
    last = _last_feedback.get(user.id, 0)
    if now - last < _COOLDOWN_SECONDS:
        remaining = int(_COOLDOWN_SECONDS - (now - last))
        raise HTTPException(
            429,
            detail=f"Bitte warte noch {remaining} Sekunden zwischen Feedback-Einsendungen.",
        )

    debug_logger.log(
        LogLevel.INFO,
        f"Feedback von {user.username}: {body.category} ({len(body.text)} Zeichen)",
        agent="API",
    )

    # Upload screenshot if provided
    screenshot_url: Optional[str] = None
    timestamp = str(int(now))
    if body.screenshot:
        try:
            base64.b64decode(body.screenshot)
        except Exception:
            raise HTTPException(400, detail="Ungültiger Screenshot (kein gültiges Base64).")
        screenshot_url = await _upload_screenshot(body.screenshot, timestamp)

    # Build issue body
    category_labels = {"bug": "Bug", "vorschlag": "Vorschlag", "general": "Allgemein"}
    lines = [
        f"**Benutzer:** {user.username}",
        f"**Kategorie:** {category_labels.get(body.category, body.category)}",
        "",
        "### Feedback",
        body.text,
    ]
    if screenshot_url:
        lines += ["", "### Screenshot", f"![Screenshot]({screenshot_url})"]

    issue_body = "\n".join(lines)
    title_text = body.text[:70].replace("\n", " ")
    issue_payload = {
        "title": f"[Feedback] {title_text}",
        "body": issue_body,
        "labels": ["user-feedback", body.category],
    }

    # Create GitHub issue
    session = await get_session()
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/issues"

    async with session.post(url, json=issue_payload, headers=_github_headers()) as resp:
        if resp.status not in (200, 201):
            error_text = await resp.text()
            debug_logger.log(
                LogLevel.ERROR,
                f"GitHub Issue-Erstellung fehlgeschlagen: HTTP {resp.status} — {error_text}",
                agent="API",
            )
            raise HTTPException(502, detail="GitHub-Issue konnte nicht erstellt werden.")

        data = await resp.json()

    _last_feedback[user.id] = now

    debug_logger.log(
        LogLevel.SUCCESS,
        f"GitHub Issue erstellt: {data['html_url']}",
        agent="API",
    )

    return {"ok": True, "issue_url": data["html_url"]}
