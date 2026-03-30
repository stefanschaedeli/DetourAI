"""Email notification service for issue proposals."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import get_settings
from .models import IssueProposal

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends email notifications about issue proposals."""

    def send_proposal_notification(self, proposal: IssueProposal) -> bool:
        """Send an email with the solution proposal and approve/reject links."""
        settings = get_settings()
        base_url = settings.app_base_url
        token = proposal.approval_token

        approve_url = f"{base_url}/proposals/{proposal.issue_number}/approve?token={token}"
        reject_url = f"{base_url}/proposals/{proposal.issue_number}/reject?token={token}"
        detail_url = f"{base_url}/proposals/{proposal.issue_number}?token={token}"

        subject = f"[DetourAI] Lösungsvorschlag für Issue #{proposal.issue_number}: {proposal.issue_title}"

        html_body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 700px; margin: 0 auto; color: #24292f;">
            <div style="background: #0969da; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0;">Issue #{proposal.issue_number}: {proposal.issue_title}</h2>
                <p style="margin: 8px 0 0; opacity: 0.9;">Automatischer Lösungsvorschlag</p>
            </div>

            <div style="border: 1px solid #d0d7de; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
                <h3>Analyse</h3>
                <p>{proposal.analysis}</p>

                <h3>Betroffene Dateien</h3>
                <ul>
                    {"".join(f"<li><code>{f}</code></li>" for f in proposal.files_to_modify)}
                </ul>

                <h3>Vorgeschlagene Änderungen</h3>
                <pre style="background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 13px;">{proposal.diff_preview}</pre>

                <div style="margin-top: 24px; text-align: center;">
                    <a href="{approve_url}"
                       style="display: inline-block; background: #2da44e; color: white; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 0 8px;">
                        ✅ Genehmigen & PR erstellen
                    </a>
                    <a href="{reject_url}"
                       style="display: inline-block; background: #cf222e; color: white; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 0 8px;">
                        ❌ Ablehnen
                    </a>
                </div>

                <p style="margin-top: 16px; text-align: center;">
                    <a href="{detail_url}">Details im Dashboard ansehen</a>
                    &nbsp;|&nbsp;
                    <a href="{proposal.issue_url}">Issue auf GitHub ansehen</a>
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
Lösungsvorschlag für Issue #{proposal.issue_number}: {proposal.issue_title}

Analyse: {proposal.analysis}

Betroffene Dateien: {", ".join(proposal.files_to_modify)}

Änderungen: {proposal.diff_preview}

Genehmigen: {approve_url}
Ablehnen: {reject_url}
Details: {detail_url}
Issue: {proposal.issue_url}
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notify_email
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            logger.info(f"Notification sent for issue #{proposal.issue_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email for issue #{proposal.issue_number}: {e}")
            return False
