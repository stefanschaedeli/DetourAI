"""Implements approved proposals by creating branches and PRs."""

import json
import logging
import re

from .github_service import GitHubService
from .models import IssueProposal, ProposalStatus

logger = logging.getLogger(__name__)


class ProposalImplementer:
    """Creates branches, commits changes, and opens PRs for approved proposals."""

    def __init__(self):
        self._gh = GitHubService()

    def implement(self, proposal: IssueProposal) -> IssueProposal:
        """Apply the proposed changes and create a PR."""
        branch_name = self._make_branch_name(proposal)

        try:
            # 1. Create feature branch
            self._gh.create_branch(branch_name)

            # 2. Apply each file change
            changes = json.loads(proposal.proposed_changes)
            for change in changes:
                path = change["path"]
                content = change["content"]
                description = change.get("description", f"Update {path}")
                commit_msg = (
                    f"fix(#{proposal.issue_number}): {description}\n\n"
                    f"Auto-generated fix for issue #{proposal.issue_number}"
                )
                self._gh.commit_file_change(branch_name, path, content, commit_msg)
                logger.info(f"Committed change to {path} on {branch_name}")

            # 3. Create pull request
            pr_title = f"fix: {proposal.issue_title} (#{proposal.issue_number})"
            pr_body = (
                f"## Automatisch generierter Fix\n\n"
                f"**Issue:** #{proposal.issue_number}\n\n"
                f"### Analyse\n{proposal.analysis}\n\n"
                f"### Änderungen\n{proposal.diff_preview}\n\n"
                f"---\n"
                f"*Dieser PR wurde automatisch vom GitHub Issue Responder erstellt.*"
            )
            pr_url = self._gh.create_pull_request(
                branch_name, pr_title, pr_body, proposal.issue_number
            )
            proposal.pr_url = pr_url
            proposal.status = ProposalStatus.IMPLEMENTED

            # 4. Comment on the issue
            self._gh.add_issue_comment(
                proposal.issue_number,
                f"Ein automatischer Lösungsvorschlag wurde genehmigt und als PR erstellt: {pr_url}",
            )
            self._gh.add_issue_label(proposal.issue_number, "auto-fix")

            logger.info(f"PR created for issue #{proposal.issue_number}: {pr_url}")

        except Exception as e:
            logger.error(f"Implementation failed for #{proposal.issue_number}: {e}")
            proposal.status = ProposalStatus.FAILED
            proposal.error_message = str(e)

        return proposal

    @staticmethod
    def _make_branch_name(proposal: IssueProposal) -> str:
        """Generate a clean branch name from the issue."""
        slug = re.sub(r"[^a-z0-9]+", "-", proposal.issue_title.lower()).strip("-")[:40]
        return f"auto-fix/{proposal.issue_number}-{slug}"
