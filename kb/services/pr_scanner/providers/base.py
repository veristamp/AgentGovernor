# services/pr_scanner/providers/base.py
"""
Abstract Git Provider - Base class for GitHub, GitLab, etc.

Defines the interface for fetching PR data and posting comments.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PRInfo:
    """Pull Request information from any git provider."""
    number: int
    title: str
    state: str  # open, closed, merged
    author: str
    base_branch: str
    head_branch: str
    repo: str  # owner/repo format
    
    # Content
    diff_url: str = ""
    diff_text: str = ""
    
    # Metadata
    labels: List[str] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Stats
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "state": self.state,
            "author": self.author,
            "base_branch": self.base_branch,
            "head_branch": self.head_branch,
            "repo": self.repo,
            "labels": self.labels,
            "additions": self.additions,
            "deletions": self.deletions,
            "changed_files": self.changed_files,
        }


@dataclass
class CommentInfo:
    """Posted comment information."""
    id: str
    body: str
    url: str
    created_at: Optional[datetime] = None


# =============================================================================
# ABSTRACT PROVIDER
# =============================================================================

class GitProvider(ABC):
    """
    Abstract base class for git hosting providers.
    
    Implement this for GitHub, GitLab, Bitbucket, etc.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'github', 'gitlab')."""
        pass
    
    @abstractmethod
    async def get_pr(self, repo: str, pr_number: int) -> PRInfo:
        """
        Get PR information.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            
        Returns:
            PRInfo with PR details
        """
        pass
    
    @abstractmethod
    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """
        Get the unified diff for a PR.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            
        Returns:
            Unified diff as string
        """
        pass
    
    @abstractmethod
    async def post_comment(
        self, 
        repo: str, 
        pr_number: int, 
        body: str
    ) -> CommentInfo:
        """
        Post a comment on a PR.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            body: Comment body (Markdown)
            
        Returns:
            CommentInfo with posted comment details
        """
        pass
    
    @abstractmethod
    async def update_comment(
        self,
        repo: str,
        comment_id: str,
        body: str
    ) -> CommentInfo:
        """
        Update an existing comment.
        
        Args:
            repo: Repository in owner/repo format
            comment_id: Comment ID to update
            body: New comment body
            
        Returns:
            Updated CommentInfo
        """
        pass
    
    @abstractmethod
    async def add_labels(
        self,
        repo: str,
        pr_number: int,
        labels: List[str]
    ) -> List[str]:
        """
        Add labels to a PR.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            labels: Labels to add
            
        Returns:
            List of labels now on the PR
        """
        pass
    
    @abstractmethod
    async def create_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        event: str,  # "APPROVE", "REQUEST_CHANGES", "COMMENT"
    ) -> Dict[str, Any]:
        """
        Create a PR review.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            body: Review body
            event: Review event type
            
        Returns:
            Review response
        """
        pass
    
    async def post_inline_comment(
        self,
        repo: str,
        pr_number: int,
        file_path: str,
        line: int,
        body: str,
        commit_sha: Optional[str] = None,
    ) -> CommentInfo:
        """
        Post an inline comment on a specific line.
        
        Default implementation raises NotImplementedError.
        Override in subclasses that support inline comments.
        """
        raise NotImplementedError("Inline comments not supported by this provider")
