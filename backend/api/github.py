"""Phase 3B API router: read-only GitHub pull-request analysis.

Additive layer: no existing endpoint is modified.

  POST /api/github/pull-request/analyze -> GitHubPullRequestAnalysis
  GET  /api/github/status                -> provider/auth status (safe)

Authentication is server-side only: the ``GITHUB_TOKEN`` environment
variable is read by the backend. The token is never accepted from the
request body, query parameters, or any frontend input, and never appears
in responses, logs, or error details.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.github import (
    GitHubClient,
    GitHubError,
    GitHubPullRequestAnalysis,
    PullRequestRequest,
    analyze_github_pull_request,
)

router = APIRouter()

# GitHubError.code -> HTTP status. Messages are pre-scrubbed (no tokens,
# no raw GitHub bodies) by the github package.
_ERROR_STATUS = {
    "repository_not_found_or_not_authorized": 404,
    "pull_request_not_found": 404,
    "github_authentication_failed": 401,
    "github_rate_limited": 429,
    "github_unavailable": 502,
    "malformed_github_response": 502,
    "incomplete_change_set": 422,
    "unsupported_github_status": 422,
    "snapshot_download_failed": 502,
    "snapshot_too_large": 413,
    "unsafe_archive": 422,
    "invalid_source_root": 400,
    "head_snapshot_unavailable": 422,
    "analysis_failed": 500,
}


class GitHubStatusResponse(BaseModel):
    provider: str = Field(default="github")
    auth_configured: bool = Field(
        ...,
        description="Whether a server-side GITHUB_TOKEN is configured. "
        "No credential details are ever exposed.",
    )


@router.get(
    "/api/github/status",
    response_model=GitHubStatusResponse,
    summary="GitHub integration status (safe)",
)
def github_status() -> GitHubStatusResponse:
    return GitHubStatusResponse(
        auth_configured=bool(os.environ.get("GITHUB_TOKEN"))
    )


@router.post(
    "/api/github/pull-request/analyze",
    response_model=GitHubPullRequestAnalysis,
    summary="Deterministic impact analysis of a GitHub pull request",
)
def analyze_github_pull_request_endpoint(
    request: PullRequestRequest,
) -> GitHubPullRequestAnalysis:
    # Pydantic already validated owner/repo/pull_number/source_root (422).
    # The client is per-request and server-side: token from env only.
    client = GitHubClient(token=GitHubClient.token_from_env())
    try:
        return analyze_github_pull_request(request, client=client)
    except GitHubError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, 500),
            detail={"code": exc.code, "message": exc.message},
        )
    finally:
        client.close()
