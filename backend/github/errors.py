"""Phase 3B typed error model: GitHub pull-request analysis.

Every failure is a controlled ``GitHubError`` carrying a machine-readable
``code`` and a safe human message. Messages never contain tokens,
authorization headers, raw GitHub response bodies, or archive bytes.
"""
from __future__ import annotations


class GitHubError(Exception):
    """Controlled Phase 3B failure.

    ``code`` is one of the documented error codes below; ``message`` is
    safe to surface to API/CLI/UI callers.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


# Error codes (see docs/GITHUB_PR_ANALYSIS.md for the full contract):
#
# repository_not_found_or_not_authorized - repo unreachable or token lacks
#     access (GitHub deliberately returns 404 for private repos).
# pull_request_not_found - PR number does not exist in the repository.
# github_authentication_failed - 401: bad or revoked credentials.
# github_rate_limited - 403/429 with rate-limit headers; includes reset time.
# github_unavailable - repeated 5xx / network failure after bounded retries.
# malformed_github_response - the GitHub API returned a payload whose
#     schema violates the expected contract (non-integer counts,
#     negative counts, non-integer PR number, invalid commit SHAs,
#     malformed refs, malformed repository full names, missing
#     base/head objects). Never a raw ValueError.
# incomplete_change_set - GitHub file-list API limit (3000) exceeded, or
#     pagination ended before the advertised file count.
# unsupported_github_status - a file status GitHub returned that Phase 3B
#     does not know how to translate (never silently mapped to modified).
# snapshot_download_failed - archive endpoint did not yield an archive.
# snapshot_too_large - a configured archive/size limit was exceeded.
# unsafe_archive - archive member rejected before materialization
#     (traversal, absolute path, symlink/hardlink, device, FIFO, ...).
# invalid_source_root - the requested source_root is not a safe
#     repository-relative path.
# head_snapshot_unavailable - head repository/sha could not be fetched
#     (e.g. deleted fork with unrecoverable head SHA).
# analysis_failed - deterministic analysis itself failed after the GitHub
#     inputs were successfully gathered.


def repository_not_found_or_not_authorized(repo: str) -> GitHubError:
    return GitHubError(
        "repository_not_found_or_not_authorized",
        f"Repository or pull request was not found, or the configured "
        f"GitHub credentials do not have access: {repo}.",
    )


def pull_request_not_found(repo: str, number: int) -> GitHubError:
    return GitHubError(
        "pull_request_not_found",
        f"Pull request #{number} was not found in {repo}.",
    )


def github_authentication_failed() -> GitHubError:
    return GitHubError(
        "github_authentication_failed",
        "GitHub authentication failed: the configured credentials were "
        "rejected. Check GITHUB_TOKEN.",
    )


def github_rate_limited(reset_at: str | None = None) -> GitHubError:
    detail = f" Rate limit resets at {reset_at}." if reset_at else ""
    return GitHubError(
        "github_rate_limited",
        "GitHub API rate limit exceeded." + detail,
    )


def github_unavailable(detail: str = "") -> GitHubError:
    suffix = f" {detail}" if detail else ""
    return GitHubError(
        "github_unavailable",
        "GitHub API is unavailable after bounded retries." + suffix,
    )


def incomplete_change_set(reason: str) -> GitHubError:
    return GitHubError("incomplete_change_set", reason)


def malformed_github_response(detail: str) -> GitHubError:
    return GitHubError(
        "malformed_github_response",
        f"Malformed GitHub API response: {detail}",
    )


def unsupported_github_status(status: str) -> GitHubError:
    return GitHubError(
        "unsupported_github_status",
        f"Unsupported GitHub file status {status!r}: refusing to guess a "
        "Phase 3A mapping for it.",
    )


def snapshot_download_failed(detail: str) -> GitHubError:
    return GitHubError(
        "snapshot_download_failed", f"Snapshot download failed: {detail}"
    )


def snapshot_too_large(detail: str) -> GitHubError:
    return GitHubError("snapshot_too_large", detail)


def unsafe_archive(member: str, reason: str) -> GitHubError:
    return GitHubError(
        "unsafe_archive",
        f"Archive member rejected before extraction: {member} ({reason}).",
    )


def invalid_source_root(root: str) -> GitHubError:
    return GitHubError(
        "invalid_source_root",
        f"Invalid source_root {root!r}: must be a safe repository-relative "
        "path (no '..', absolute paths, drive letters, or UNC paths).",
    )


def head_snapshot_unavailable(detail: str) -> GitHubError:
    return GitHubError("head_snapshot_unavailable", detail)


def analysis_failed(detail: str) -> GitHubError:
    return GitHubError("analysis_failed", detail)
