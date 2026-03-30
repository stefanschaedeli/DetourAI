"""Issue analysis using Claude API to generate solution proposals."""

import json
import logging
from typing import Optional

import anthropic

from .config import get_settings
from .github_service import GitHubService
from .models import IssueProposal

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """You are an expert software engineer analyzing GitHub issues.
You receive the issue description, the repository file structure, and relevant source files.

Your job:
1. Understand the issue thoroughly
2. Identify which files need to be changed
3. Propose concrete code changes with full file content for each modified file
4. Explain your reasoning

Respond in JSON with this structure:
{
  "analysis": "Brief explanation of the problem and your approach",
  "files_to_modify": ["path/to/file1.py", "path/to/file2.py"],
  "changes": [
    {
      "path": "path/to/file1.py",
      "content": "full new file content here",
      "description": "What changed and why"
    }
  ],
  "diff_preview": "Human-readable summary of all changes"
}

If the issue is unclear or you cannot propose a solution, set analysis to your explanation
and leave changes as an empty array.
"""


class IssueAnalyzer:
    """Analyzes GitHub issues and generates solution proposals."""

    def __init__(self):
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._gh = GitHubService()

    def analyze(self, proposal: IssueProposal) -> IssueProposal:
        """Analyze an issue and fill in the proposal with a solution."""
        logger.info(f"Analyzing issue #{proposal.issue_number}: {proposal.issue_title}")

        # Gather context from the repo
        file_tree = self._gh.get_repo_structure()
        repo_context = "\n".join(file_tree)

        # Read key files for context (README, configs, etc.)
        key_files = [f for f in file_tree if any(
            f.endswith(ext) for ext in [
                "README.md", "requirements.txt", "package.json",
                "Dockerfile", "docker-compose.yml", ".env.example",
            ]
        )]
        # Also include source files (limit to manageable set)
        source_files = [f for f in file_tree if any(
            f.endswith(ext) for ext in [".py", ".ts", ".js", ".go", ".rs", ".java"]
        )]
        files_to_read = key_files + source_files[:15]
        file_contents = self._gh.get_relevant_files(files_to_read)

        files_context = ""
        for path, content in file_contents.items():
            files_context += f"\n--- {path} ---\n{content}\n"

        user_message = f"""## GitHub Issue #{proposal.issue_number}
**Title:** {proposal.issue_title}

**Description:**
{proposal.issue_body}

## Repository Structure
```
{repo_context}
```

## Source Files
{files_context}

Please analyze this issue and propose a concrete solution.
"""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            result_text = response.content[0].text

            # Parse JSON from response (handle markdown code blocks)
            json_str = result_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            result = json.loads(json_str)

            proposal.analysis = result.get("analysis", "")
            proposal.files_to_modify = result.get("files_to_modify", [])
            proposal.proposed_changes = json.dumps(result.get("changes", []), indent=2)
            proposal.diff_preview = result.get("diff_preview", "")

            logger.info(
                f"Analysis complete for #{proposal.issue_number}: "
                f"{len(proposal.files_to_modify)} files to modify"
            )

        except (json.JSONDecodeError, anthropic.APIError) as e:
            logger.error(f"Analysis failed for #{proposal.issue_number}: {e}")
            proposal.analysis = f"Analysis failed: {e}"
            proposal.proposed_changes = "[]"

        return proposal
