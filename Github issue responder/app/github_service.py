"""GitHub API interactions: repo analysis, branch creation, PR creation."""

import base64
import logging
from typing import Optional

from github import Github, GithubException
from github.Repository import Repository

from .config import get_settings

logger = logging.getLogger(__name__)


class GitHubService:
    """Handles all GitHub API interactions."""

    def __init__(self):
        settings = get_settings()
        self._gh = Github(settings.github_token)
        self._repo_name = settings.github_repo

    @property
    def repo(self) -> Repository:
        return self._gh.get_repo(self._repo_name)

    def get_repo_structure(self, path: str = "", max_depth: int = 3) -> list[str]:
        """Get the file tree of the repository."""
        files = []
        try:
            contents = self.repo.get_contents(path)
            for item in contents:
                if item.type == "dir" and max_depth > 0:
                    files.append(f"{item.path}/")
                    files.extend(self.get_repo_structure(item.path, max_depth - 1))
                else:
                    files.append(item.path)
        except GithubException as e:
            logger.warning(f"Could not read path '{path}': {e}")
        return files

    def get_file_content(self, path: str) -> Optional[str]:
        """Read a single file from the repo."""
        try:
            content = self.repo.get_contents(path)
            if content.encoding == "base64":
                return base64.b64decode(content.content).decode("utf-8")
            return content.decoded_content.decode("utf-8")
        except (GithubException, UnicodeDecodeError) as e:
            logger.warning(f"Could not read file '{path}': {e}")
            return None

    def get_relevant_files(self, file_paths: list[str], max_files: int = 10) -> dict[str, str]:
        """Read multiple files, skipping binary/large ones."""
        result = {}
        skip_extensions = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".ttf", ".lock"}
        for path in file_paths[:max_files]:
            if any(path.endswith(ext) for ext in skip_extensions):
                continue
            content = self.get_file_content(path)
            if content and len(content) < 50_000:
                result[path] = content
        return result

    def create_branch(self, branch_name: str) -> str:
        """Create a new branch from the default branch."""
        default_branch = self.repo.default_branch
        ref = self.repo.get_git_ref(f"heads/{default_branch}")
        sha = ref.object.sha
        self.repo.create_git_ref(f"refs/heads/{branch_name}", sha)
        logger.info(f"Created branch '{branch_name}' from '{default_branch}' at {sha[:8]}")
        return sha

    def commit_file_change(
        self, branch: str, path: str, new_content: str, commit_message: str
    ) -> str:
        """Update or create a file on the given branch."""
        try:
            existing = self.repo.get_contents(path, ref=branch)
            result = self.repo.update_file(
                path, commit_message, new_content, existing.sha, branch=branch
            )
        except GithubException:
            result = self.repo.create_file(
                path, commit_message, new_content, branch=branch
            )
        return result["commit"].sha

    def create_pull_request(
        self, branch: str, title: str, body: str, issue_number: int
    ) -> str:
        """Create a pull request and link it to the issue."""
        default_branch = self.repo.default_branch
        pr = self.repo.create_pull(
            title=title,
            body=f"{body}\n\nCloses #{issue_number}",
            head=branch,
            base=default_branch,
        )
        logger.info(f"Created PR #{pr.number}: {pr.html_url}")
        return pr.html_url

    def add_issue_comment(self, issue_number: int, comment: str) -> None:
        """Post a comment on a GitHub issue."""
        issue = self.repo.get_issue(issue_number)
        issue.create_comment(comment)

    def add_issue_label(self, issue_number: int, label: str) -> None:
        """Add a label to an issue, creating it if necessary."""
        try:
            self.repo.get_label(label)
        except GithubException:
            self.repo.create_label(label, "0e8a16")
        issue = self.repo.get_issue(issue_number)
        issue.add_to_labels(label)
