"""Simple file-based proposal storage."""

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import IssueProposal, ProposalStatus

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data/proposals"))


class ProposalStore:
    """Persists proposals to JSON files on disk (volume-mounted)."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, issue_number: int) -> Path:
        return DATA_DIR / f"issue-{issue_number}.json"

    def save(self, proposal: IssueProposal) -> None:
        data = asdict(proposal)
        data["created_at"] = proposal.created_at.isoformat()
        data["status"] = proposal.status.value
        self._path(proposal.issue_number).write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )

    def get(self, issue_number: int) -> Optional[IssueProposal]:
        path = self._path(issue_number)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["status"] = ProposalStatus(data["status"])
        return IssueProposal(**data)

    def list_all(self) -> list[IssueProposal]:
        proposals = []
        for path in sorted(DATA_DIR.glob("issue-*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                data["status"] = ProposalStatus(data["status"])
                proposals.append(IssueProposal(**data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping corrupt file {path}: {e}")
        return proposals

    def has_proposal(self, issue_number: int) -> bool:
        return self._path(issue_number).exists()

    def get_processed_issues(self) -> set[int]:
        """Return set of issue numbers that already have proposals."""
        return {
            int(p.stem.replace("issue-", ""))
            for p in DATA_DIR.glob("issue-*.json")
        }
