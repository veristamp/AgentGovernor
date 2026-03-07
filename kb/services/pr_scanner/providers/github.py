# services/pr_scanner/providers/github.py
"""
GitHub Provider - GitHub API integration for PR scanning.

Uses GitHub REST API to:
- Fetch PR information and diffs
- Post review comments
- Add labels
- Create reviews
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime

from config import get_logger
from .base import GitProvider, PRInfo, CommentInfo

logger = get_logger("GitHubProvider")


# =============================================================================
# GITHUB PROVIDER
# =============================================================================

class GitHubProvider(GitProvider):
    """
    GitHub API integration using httpx.
    
    Requires a GitHub token with repo access.
    Token can be:
    - Personal Access Token (PAT)
    - GitHub App Installation Token
    - Fine-grained PAT
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize GitHub provider.
        
        Args:
            token: GitHub token (or reads from GITHUB_TOKEN env)
            base_url: Base API URL (for GitHub Enterprise)
        """
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self._client = None
        
        if not self.token:
            logger.warning("No GitHub token provided - API calls will be limited")
    
    @property
    def name(self) -> str:
        return "github"
    
    async def _get_client(self):
        """Lazy-load httpx async client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._get_headers(),
                timeout=30.0,
            )
        return self._client
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Veristamp-PRScanner",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def get_pr(self, repo: str, pr_number: int) -> PRInfo:
        """Get PR information from GitHub API."""
        client = await self._get_client()
        
        response = await client.get(f"/repos/{repo}/pulls/{pr_number}")
        response.raise_for_status()
        
        data = response.json()
        
        return PRInfo(
            number=data["number"],
            title=data["title"],
            state=data["state"],
            author=data["user"]["login"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            repo=repo,
            diff_url=data["diff_url"],
            labels=[l["name"] for l in data.get("labels", [])],
            reviewers=[r["login"] for r in data.get("requested_reviewers", [])],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
        )
    
    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Get unified diff for a PR."""
        client = await self._get_client()
        
        # Request diff format
        headers = {
            "Accept": "application/vnd.github.v3.diff",
        }
        
        response = await client.get(
            f"/repos/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        response.raise_for_status()
        
        return response.text
    
    async def get_pr_files(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get list of changed files with patches."""
        client = await self._get_client()
        
        files = []
        page = 1
        per_page = 100
        
        while True:
            response = await client.get(
                f"/repos/{repo}/pulls/{pr_number}/files",
                params={"page": page, "per_page": per_page}
            )
            response.raise_for_status()
            
            data = response.json()
            if not data:
                break
            
            files.extend(data)
            
            if len(data) < per_page:
                break
            page += 1
        
        return files
    
    async def post_comment(
        self,
        repo: str,
        pr_number: int,
        body: str
    ) -> CommentInfo:
        """Post a comment on a PR (issue comment)."""
        client = await self._get_client()
        
        # Use issues API for general PR comments
        response = await client.post(
            f"/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body}
        )
        response.raise_for_status()
        
        data = response.json()
        
        return CommentInfo(
            id=str(data["id"]),
            body=data["body"],
            url=data["html_url"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
    
    async def update_comment(
        self,
        repo: str,
        comment_id: str,
        body: str
    ) -> CommentInfo:
        """Update an existing comment."""
        client = await self._get_client()
        
        response = await client.patch(
            f"/repos/{repo}/issues/comments/{comment_id}",
            json={"body": body}
        )
        response.raise_for_status()
        
        data = response.json()
        
        return CommentInfo(
            id=str(data["id"]),
            body=data["body"],
            url=data["html_url"],
            created_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
        )
    
    async def add_labels(
        self,
        repo: str,
        pr_number: int,
        labels: List[str]
    ) -> List[str]:
        """Add labels to a PR."""
        if not labels:
            return []
        
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{repo}/issues/{pr_number}/labels",
            json={"labels": labels}
        )
        response.raise_for_status()
        
        data = response.json()
        return [l["name"] for l in data]
    
    async def remove_labels(
        self,
        repo: str,
        pr_number: int,
        labels: List[str]
    ) -> None:
        """Remove labels from a PR."""
        client = await self._get_client()
        
        for label in labels:
            try:
                await client.delete(
                    f"/repos/{repo}/issues/{pr_number}/labels/{label}"
                )
            except Exception as e:
                logger.debug(f"Could not remove label {label}: {e}")
    
    async def create_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        event: str,
    ) -> Dict[str, Any]:
        """
        Create a PR review.
        
        Args:
            event: APPROVE, REQUEST_CHANGES, or COMMENT
        """
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            json={
                "body": body,
                "event": event,
            }
        )
        response.raise_for_status()
        
        return response.json()
    
    async def post_inline_comment(
        self,
        repo: str,
        pr_number: int,
        file_path: str,
        line: int,
        body: str,
        commit_sha: Optional[str] = None,
    ) -> CommentInfo:
        """Post an inline comment on a specific line."""
        client = await self._get_client()
        
        # Get latest commit SHA if not provided
        if not commit_sha:
            pr_info = await self.get_pr(repo, pr_number)
            response = await client.get(f"/repos/{repo}/pulls/{pr_number}")
            response.raise_for_status()
            commit_sha = response.json()["head"]["sha"]
        
        response = await client.post(
            f"/repos/{repo}/pulls/{pr_number}/comments",
            json={
                "body": body,
                "commit_id": commit_sha,
                "path": file_path,
                "line": line,
                "side": "RIGHT",  # Comment on the new version
            }
        )
        response.raise_for_status()
        
        data = response.json()
        
        return CommentInfo(
            id=str(data["id"]),
            body=data["body"],
            url=data["html_url"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        )
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# FACTORY
# =============================================================================

def create_github_provider(
    token: Optional[str] = None,
    base_url: Optional[str] = None,
) -> GitHubProvider:
    """
    Factory function to create a GitHubProvider.
    
    Args:
        token: GitHub token (defaults to GITHUB_TOKEN env var)
        base_url: Base API URL (for GitHub Enterprise)
        
    Returns:
        Configured GitHubProvider
    """
    return GitHubProvider(token=token, base_url=base_url)
