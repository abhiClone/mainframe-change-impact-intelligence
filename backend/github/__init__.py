"""Phase 3B: read-only GitHub pull-request impact analysis."""
from .client import GitHubClient
from .errors import GitHubError
from .models import (
    GITHUB_API_VERSION,
    GitHubChangedFile,
    GitHubPullRequestAnalysis,
    GitHubRateLimit,
    PullRequestMetadata,
    PullRequestRequest,
    SnapshotMetadata,
    SourceScope,
)
from .provider import GitHubPullRequestProvider, translate_github_files
from .service import analyze_github_pull_request, build_request, parse_repo_arg
from .snapshots import SnapshotLimits, extract_snapshot

__all__ = [
    "GITHUB_API_VERSION",
    "GitHubChangedFile",
    "GitHubClient",
    "GitHubError",
    "GitHubPullRequestAnalysis",
    "GitHubPullRequestProvider",
    "GitHubRateLimit",
    "PullRequestMetadata",
    "PullRequestRequest",
    "SnapshotMetadata",
    "SnapshotLimits",
    "SourceScope",
    "analyze_github_pull_request",
    "build_request",
    "extract_snapshot",
    "parse_repo_arg",
    "translate_github_files",
]
