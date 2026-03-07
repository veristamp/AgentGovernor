# services/pr_scanner/providers/__init__.py
"""
Git Provider Integrations.

Provides abstract base and concrete implementations for:
- GitHub PR API
- GitLab MR API (future)
- Bitbucket PR API (future)
"""

from .base import GitProvider, PRInfo
from .github import GitHubProvider, create_github_provider

__all__ = [
    # Base
    "GitProvider",
    "PRInfo",
    # GitHub
    "GitHubProvider",
    "create_github_provider",
]
