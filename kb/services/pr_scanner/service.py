# services/pr_scanner/service.py
"""
PR Service - High-level integration for end-to-end PR scanning.

Combines:
- Git provider (GitHub/GitLab) for fetching PRs
- PRScanner for analysis
- PRCommentFormatter for output
- Comment posting back to the PR
"""

from typing import Optional, Any, List

from config import get_logger
from .core import PRVerdictReport, PRVerdict, PRScannerConfig
from .scanner import PRScanner, create_pr_scanner
from .formatter import PRCommentFormatter, format_pr_comment
from .providers import GitProvider, GitHubProvider, create_github_provider, PRInfo

logger = get_logger("PRService")


# =============================================================================
# PR SERVICE
# =============================================================================

class PRService:
    """
    High-level PR scanning service.
    
    End-to-end workflow:
    1. Fetch PR from provider (GitHub/GitLab)
    2. Scan with PRScanner
    3. Format as Markdown comment
    4. Post comment back to PR
    5. Add labels (optional)
    6. Create review (optional)
    
    Usage:
        service = PRService(github_token="ghp_...")
        report = await service.scan_and_comment("owner/repo", 123)
    """
    
    def __init__(
        self,
        scanner: Optional[PRScanner] = None,
        provider: Optional[GitProvider] = None,
        formatter: Optional[PRCommentFormatter] = None,
        config: Optional[PRScannerConfig] = None,
        session_maker: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
    ):
        """
        Initialize PR Service.
        
        Args:
            scanner: Pre-configured PRScanner
            provider: Git provider (GitHub, GitLab, etc.)
            formatter: Comment formatter
            config: Scanner configuration
            session_maker: DB session for audit logging
            qdrant_client: Qdrant client for semantic linting
        """
        self._scanner = scanner
        self._provider = provider
        self._formatter = formatter or PRCommentFormatter()
        self._config = config or PRScannerConfig()
        self._session_maker = session_maker
        self._qdrant_client = qdrant_client
    
    @property
    def scanner(self) -> PRScanner:
        """Lazy-load scanner."""
        if self._scanner is None:
            self._scanner = create_pr_scanner(
                project_root=self._config.project_root,
                session_maker=self._session_maker,
                qdrant_client=self._qdrant_client,
            )
        return self._scanner
    
    @property
    def provider(self) -> GitProvider:
        """Get the git provider (raises if not configured)."""
        if self._provider is None:
            raise ValueError("No git provider configured. Pass provider or github_token.")
        return self._provider
    
    async def scan_pr(self, repo: str, pr_number: int) -> PRVerdictReport:
        """
        Scan a PR and return the verdict report.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            
        Returns:
            PRVerdictReport with full analysis
        """
        logger.info(f"Scanning PR #{pr_number} in {repo}")
        
        # 1. Get PR info
        pr_info = await self.provider.get_pr(repo, pr_number)
        
        # 2. Get diff
        diff_text = await self.provider.get_pr_diff(repo, pr_number)
        
        # 3. Scan with scanner
        report = await self.scanner.scan_diff(
            diff_text=diff_text,
            pr_number=pr_number,
            repo=repo,
            base_branch=pr_info.base_branch,
            head_branch=pr_info.head_branch,
        )
        
        return report
    
    async def scan_and_comment(
        self,
        repo: str,
        pr_number: int,
        update_existing: bool = True,
        create_review: bool = False,
    ) -> PRVerdictReport:
        """
        Scan a PR and post a comment with the results.
        
        Args:
            repo: Repository in owner/repo format
            pr_number: Pull request number
            update_existing: Update existing bot comment if found
            create_review: Create a formal PR review instead of comment
            
        Returns:
            PRVerdictReport with results
        """
        # 1. Scan the PR
        report = await self.scan_pr(repo, pr_number)
        
        # 2. Format as comment
        comment_body = self._formatter.format(report)
        
        # 3. Post comment or create review
        if create_review:
            event = self._verdict_to_review_event(report.verdict)
            await self.provider.create_review(repo, pr_number, comment_body, event)
            logger.info(f"Created {event} review on PR #{pr_number}")
        else:
            await self.provider.post_comment(repo, pr_number, comment_body)
            logger.info(f"Posted comment on PR #{pr_number}")
        
        # 4. Add labels if configured
        if self._config.auto_label and report.labels:
            try:
                await self.provider.add_labels(repo, pr_number, report.labels)
                logger.info(f"Added labels: {report.labels}")
            except Exception as e:
                logger.warning(f"Failed to add labels: {e}")
        
        return report
    
    async def get_pr_info(self, repo: str, pr_number: int) -> PRInfo:
        """Get PR information without scanning."""
        return await self.provider.get_pr(repo, pr_number)
    
    def _verdict_to_review_event(self, verdict: PRVerdict) -> str:
        """Map verdict to GitHub review event."""
        mapping = {
            PRVerdict.APPROVE: "APPROVE",
            PRVerdict.REQUEST_CHANGES: "REQUEST_CHANGES",
            PRVerdict.COMMENT: "COMMENT",
        }
        return mapping.get(verdict, "COMMENT")


# =============================================================================
# FACTORY
# =============================================================================

def create_pr_service(
    github_token: Optional[str] = None,
    project_root: Optional[str] = None,
    session_maker: Optional[Any] = None,
    qdrant_client: Optional[Any] = None,
    **kwargs
) -> PRService:
    """
    Factory function to create a PRService with GitHub integration.
    
    Args:
        github_token: GitHub API token (or reads GITHUB_TOKEN env)
        project_root: Project root for file resolution
        session_maker: DB session for audit logging
        qdrant_client: Qdrant client for semantic linting
        **kwargs: Additional PRScannerConfig fields
        
    Returns:
        Configured PRService
    """
    # Create GitHub provider if token provided
    provider = None
    if github_token or "GITHUB_TOKEN" in __import__("os").environ:
        provider = create_github_provider(token=github_token)
    
    # Create config
    config = PRScannerConfig(
        project_root=project_root,
        **{k: v for k, v in kwargs.items() if hasattr(PRScannerConfig, k)}
    )
    
    return PRService(
        provider=provider,
        config=config,
        session_maker=session_maker,
        qdrant_client=qdrant_client,
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def quick_scan_pr(
    repo: str,
    pr_number: int,
    github_token: Optional[str] = None,
) -> PRVerdictReport:
    """
    Quick function to scan a PR and get results.
    
    Args:
        repo: Repository in owner/repo format
        pr_number: Pull request number
        github_token: GitHub token (optional, uses env)
        
    Returns:
        PRVerdictReport
    """
    service = create_pr_service(github_token=github_token)
    return await service.scan_pr(repo, pr_number)


async def quick_scan_and_comment(
    repo: str,
    pr_number: int,
    github_token: Optional[str] = None,
) -> PRVerdictReport:
    """
    Quick function to scan a PR and post comment.
    
    Args:
        repo: Repository in owner/repo format
        pr_number: Pull request number
        github_token: GitHub token (optional, uses env)
        
    Returns:
        PRVerdictReport
    """
    service = create_pr_service(github_token=github_token)
    return await service.scan_and_comment(repo, pr_number)
