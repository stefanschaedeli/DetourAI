"""Data models for issue proposals."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import hashlib
import secrets


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    FAILED = "failed"


@dataclass
class IssueProposal:
    """Represents a solution proposal for a GitHub issue."""

    issue_number: int
    issue_title: str
    issue_body: str
    issue_url: str
    analysis: str = ""
    proposed_changes: str = ""
    files_to_modify: list[str] = field(default_factory=list)
    diff_preview: str = ""
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approval_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    pr_url: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def id(self) -> str:
        return hashlib.sha256(
            f"{self.issue_number}-{self.created_at.isoformat()}".encode()
        ).hexdigest()[:12]
