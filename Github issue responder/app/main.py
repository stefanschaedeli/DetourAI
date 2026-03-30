"""GitHub Issue Responder — FastAPI application."""

import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .analyzer import IssueAnalyzer
from .config import get_settings
from .implementer import ProposalImplementer
from .models import IssueProposal, ProposalStatus
from .notifier import EmailNotifier
from .store import ProposalStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GitHub Issue Responder starting up")
    logger.info(f"Monitoring repo: {get_settings().github_repo}")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="GitHub Issue Responder",
    description="Automatically analyzes GitHub issues and proposes solutions",
    version="1.0.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="templates")
store = ProposalStore()


# ── Webhook endpoint ─────────────────────────────────────────────

def verify_github_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify the GitHub webhook HMAC signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def process_new_issue(issue_number: int, issue_title: str, issue_body: str, issue_url: str):
    """Background task: analyze issue, store proposal, send notification."""
    proposal = IssueProposal(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body or "(no description)",
        issue_url=issue_url,
    )

    # Analyze with Claude
    analyzer = IssueAnalyzer()
    proposal = analyzer.analyze(proposal)

    # Persist
    store.save(proposal)

    # Notify via email
    notifier = EmailNotifier()
    notifier.send_proposal_notification(proposal)

    # Also comment on the issue
    from .github_service import GitHubService
    gh = GitHubService()
    gh.add_issue_comment(
        issue_number,
        f"🤖 **Automatische Analyse abgeschlossen**\n\n"
        f"{proposal.analysis}\n\n"
        f"Ein Lösungsvorschlag wurde erstellt und wird geprüft.",
    )
    gh.add_issue_label(issue_number, "auto-analyzed")

    logger.info(f"Issue #{issue_number} processed and notification sent")


@app.post("/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive GitHub webhook events."""
    settings = get_settings()

    # Verify signature
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(body, signature, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    if event == "issues" and payload.get("action") == "opened":
        issue = payload["issue"]
        issue_number = issue["number"]

        # Skip if already processed
        if store.has_proposal(issue_number):
            return {"status": "already_processed"}

        background_tasks.add_task(
            process_new_issue,
            issue_number=issue_number,
            issue_title=issue["title"],
            issue_body=issue.get("body", ""),
            issue_url=issue["html_url"],
        )
        return {"status": "processing", "issue": issue_number}

    if event == "ping":
        return {"status": "pong"}

    return {"status": "ignored", "event": event}


# ── Approval endpoints ───────────────────────────────────────────

@app.get("/proposals/{issue_number}/approve")
async def approve_proposal(
    issue_number: int,
    token: str = Query(...),
    background_tasks: BackgroundTasks = None,
):
    """Approve a proposal and trigger PR creation."""
    proposal = store.get(issue_number)
    if not proposal or proposal.approval_token != token:
        raise HTTPException(status_code=404, detail="Proposal not found or invalid token")

    if proposal.status != ProposalStatus.PENDING:
        return HTMLResponse(
            f"<h2>Proposal #{issue_number} has already been {proposal.status.value}.</h2>"
            f'<p><a href="/proposals/{issue_number}?token={token}">View details</a></p>'
        )

    proposal.status = ProposalStatus.APPROVED
    store.save(proposal)

    # Implement in background
    def do_implement():
        impl = ProposalImplementer()
        updated = impl.implement(proposal)
        store.save(updated)

    background_tasks.add_task(do_implement)

    return HTMLResponse(f"""
    <html>
    <body style="font-family: sans-serif; max-width: 600px; margin: 40px auto; text-align: center;">
        <h1 style="color: #2da44e;">✅ Genehmigt!</h1>
        <p>Der Lösungsvorschlag für Issue #{issue_number} wird jetzt als Pull Request umgesetzt.</p>
        <p>Du erhältst eine Benachrichtigung, sobald der PR erstellt wurde.</p>
        <a href="/proposals/{issue_number}?token={token}">Details ansehen</a>
    </body>
    </html>
    """)


@app.get("/proposals/{issue_number}/reject")
async def reject_proposal(issue_number: int, token: str = Query(...)):
    """Reject a proposal."""
    proposal = store.get(issue_number)
    if not proposal or proposal.approval_token != token:
        raise HTTPException(status_code=404, detail="Proposal not found or invalid token")

    proposal.status = ProposalStatus.REJECTED
    store.save(proposal)

    from .github_service import GitHubService
    gh = GitHubService()
    gh.add_issue_comment(
        issue_number,
        "❌ Der automatische Lösungsvorschlag wurde abgelehnt. "
        "Ein Entwickler wird sich das Issue manuell ansehen.",
    )

    return HTMLResponse(f"""
    <html>
    <body style="font-family: sans-serif; max-width: 600px; margin: 40px auto; text-align: center;">
        <h1 style="color: #cf222e;">❌ Abgelehnt</h1>
        <p>Der Vorschlag für Issue #{issue_number} wurde abgelehnt.</p>
        <a href="{proposal.issue_url}">Issue auf GitHub ansehen</a>
    </body>
    </html>
    """)


# ── Dashboard ────────────────────────────────────────────────────

@app.get("/proposals/{issue_number}")
async def proposal_detail(request: Request, issue_number: int, token: str = Query(None)):
    """Show proposal details."""
    proposal = store.get(issue_number)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return templates.TemplateResponse("proposal_detail.html", {
        "request": request,
        "proposal": proposal,
        "token": token,
    })


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Show all proposals."""
    proposals = store.list_all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "proposals": proposals,
    })


@app.get("/health")
async def health():
    return {"status": "healthy", "repo": get_settings().github_repo}
