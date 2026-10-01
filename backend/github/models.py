"""Phase 3B typed models: GitHub pull-request analysis.

Pydantic models for the request, GitHub metadata, changed files with
source-scope classification, snapshot metadata, rate limits, and the
top-level ``GitHubPullRequestAnalysis`` result.

The Phase 3A ``ChangeSetIntelligence`` is embedded intact inside the
result — never flattened or reinvented.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.changeset.models import ChangeSetIntelligence, ChangeStatus

from .errors import invalid_source_root, malformed_github_response

# GitHub REST API version pinned for every request (verified against the
# official docs at implementation time; see docs/GITHUB_PR_ANALYSIS.md).
GITHUB_API_VERSION = "2026-03-10"
GITHUB_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "mainframe-change-impact-intelligence"
GITHUB_API_BASE = "https://api.github.com"
# Archive downloads redirect to this GitHub-controlled host. The
# Authorization header is NEVER forwarded to it.
GITHUB_ARCHIVE_HOST = "codeload.github.com"
# GitHub's PR-files endpoint returns at most this many files.
GITHUB_PR_FILES_HARD_LIMIT = 3000


class SourceScope(str, Enum):
    IN_SOURCE_SCOPE = "in_source_scope"
    OUTSIDE_SOURCE_SCOPE = "outside_source_scope"


class GitHubFileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


_OWNER_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
_REPO_RE = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")

# Immutable Git object IDs as returned by GitHub.com: full 40-character
# lowercase hexadecimal commit SHAs. Branch names, short SHAs, and
# ref-like strings are never accepted as snapshot identity.
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Upstream refs are display-only metadata; still bounded and controlled.
_GIT_REF_MAX_LENGTH = 512

# Input-hardening bound for source_root (L4). This is not a filesystem
# security control (traversal is rejected separately); it caps absurdly
# long values before they reach path handling. 1024 characters is far
# above any legitimate repository-relative Mainframe source root.
SOURCE_ROOT_MAX_LENGTH = 1024


def parse_github_count(value: Any, *, field: str, what: str) -> int:
    """Parse a GitHub integer count field deterministically (L2/L6).

    Accepts ``None`` (missing field -> 0), ints, integral floats, and
    plain integer strings. Anything else — non-numeric strings, bools,
    fractional floats, containers — and any negative value is a
    malformed upstream schema violation and raises the typed
    ``malformed_github_response`` error. Never raises a raw
    ``ValueError`` and never silently coerces obviously invalid values.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        raise malformed_github_response(
            f"{what}: field {field!r} has non-integer value {value!r}"
        )
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise malformed_github_response(
                f"{what}: field {field!r} has non-integer value {value!r}"
            )
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or not text.lstrip("+-").isdigit():
            raise malformed_github_response(
                f"{what}: field {field!r} has non-integer value {value!r}"
            )
        parsed = int(text)
    else:
        raise malformed_github_response(
            f"{what}: field {field!r} has non-integer value {value!r}"
        )
    if parsed < 0:
        raise malformed_github_response(
            f"{what}: field {field!r} has negative value {parsed}"
        )
    return parsed


def parse_commit_sha(value: Any, *, field: str, what: str) -> str:
    """Strictly validate an immutable Git commit SHA from upstream metadata.

    GitHub.com returns full 40-character lowercase hexadecimal SHAs.
    Branch names (``"main"``), short SHAs, traversal strings, and
    non-hex values are rejected as ``malformed_github_response``.
    Phase 3B never substitutes a branch ref, a merge SHA, or current
    HEAD for an invalid SHA: snapshot identity is exact and
    content-addressed, or the analysis fails closed.
    """
    shown = repr(value)
    if len(shown) > 80:
        shown = shown[:77] + "..."
    if not isinstance(value, str) or not _COMMIT_SHA_RE.match(value):
        raise malformed_github_response(
            f"{what}: field {field!r} is not a valid 40-character "
            f"hexadecimal commit SHA (got {shown})"
        )
    return value


def parse_repo_full_name(value: Any, *, field: str, what: str) -> str:
    """Validate an upstream ``owner/repository`` full name structurally.

    Reuses the same owner/repository semantics as the user's repository
    input. These names are split into owner/repo and interpolated into
    GitHub API paths, so malformed values must fail here — they must
    never alter the request host, URL path structure, query, or
    fragment.
    """
    if not isinstance(value, str):
        raise malformed_github_response(
            f"{what}: field {field!r} is not a string "
            f"(got {type(value).__name__})"
        )
    text = value.strip()
    if "://" in text or "\\" in text:
        raise malformed_github_response(
            f"{what}: field {field!r} is not a valid "
            "'owner/repository' name"
        )
    parts = text.split("/")
    if (
        len(parts) != 2
        or not _OWNER_RE.match(parts[0])
        or not _REPO_RE.match(parts[1])
    ):
        raise malformed_github_response(
            f"{what}: field {field!r} is not a valid "
            "'owner/repository' name"
        )
    return f"{parts[0]}/{parts[1]}"


def parse_git_ref(value: Any, *, field: str, what: str) -> str:
    """Validate an upstream git ref (branch name) as display-only metadata.

    Refs are never used for snapshot identity (only validated SHAs are)
    and never interpolated into URLs; they are validated as non-empty,
    bounded, control-character-free strings.
    """
    if not isinstance(value, str):
        raise malformed_github_response(
            f"{what}: field {field!r} is not a string "
            f"(got {type(value).__name__})"
        )
    text = value.strip()
    if not text or len(text) > _GIT_REF_MAX_LENGTH:
        raise malformed_github_response(
            f"{what}: field {field!r} is not a valid git ref"
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise malformed_github_response(
            f"{what}: field {field!r} is not a valid git ref"
        )
    return text


def parse_strict_count(value: Any, *, field: str, what: str) -> int:
    """Parse a PR-level integer count that must be a genuine JSON integer.

    Unlike ``parse_github_count`` (which tolerates missing/``None`` and
    integer strings for optional file-level fields), PR-level
    ``changed_files`` must be present and a real integer: missing,
    null, strings, floats, bools, and negatives are upstream schema
    violations and raise the typed ``malformed_github_response`` error.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise malformed_github_response(
            f"{what}: field {field!r} must be an integer "
            f"(got {value!r})"
        )
    if value < 0:
        raise malformed_github_response(
            f"{what}: field {field!r} has negative value {value}"
        )
    return value


def validate_source_root(value: str) -> str:
    """Validate a repository-relative source root.

    Returns the normalized root (``"."`` for the repository root).
    Raises ``GitHubError`` (invalid_source_root) on unsafe input.
    Values longer than ``SOURCE_ROOT_MAX_LENGTH`` are rejected as
    input hardening (L4).
    """
    raw = (value or "").strip().replace("\\", "/")
    if len(raw) > SOURCE_ROOT_MAX_LENGTH:
        raise invalid_source_root(value)
    if raw in ("", ".", "./"):
        return "."
    # Reject before normalization: absolute paths, "..", Windows drive
    # letters, and UNC paths must fail, never be silently cleaned.
    if (
        raw.startswith("/")
        or raw.startswith("//")
        or _WINDOWS_DRIVE_RE.match(raw)
        or ".." in raw.split("/")
        or raw.endswith("/..")
    ):
        raise invalid_source_root(value)
    normalized = raw.strip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return "."
    if normalized in (".", ".."):
        raise invalid_source_root(value)
    if ".." in normalized.split("/"):
        raise invalid_source_root(value)
    return normalized


class PullRequestRequest(BaseModel):
    """Typed Phase 3B analysis request.

    Unknown fields are rejected (``extra="forbid"``, L3): this is a
    security-sensitive request model, so a body that smuggles ``token``,
    ``api_base_url``, or similar fields must fail validation loudly
    rather than be silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    owner: str = Field(..., description="GitHub repository owner login.")
    repo: str = Field(..., description="GitHub repository name.")
    pull_number: int = Field(..., description="Pull request number (> 0).")
    source_root: str = Field(
        default=".",
        description="Repository-relative Mainframe source root.",
    )

    @field_validator("owner")
    @classmethod
    def _owner_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not _OWNER_RE.match(v):
            raise ValueError(f"invalid GitHub owner {v!r}")
        return v

    @field_validator("repo")
    @classmethod
    def _repo_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not _REPO_RE.match(v) or "/" in v:
            raise ValueError(f"invalid GitHub repository name {v!r}")
        return v

    @field_validator("pull_number")
    @classmethod
    def _pull_number_valid(cls, v: int) -> int:
        if v is None or int(v) <= 0:
            raise ValueError("pull_number must be > 0")
        return int(v)

    @field_validator("source_root")
    @classmethod
    def _source_root_valid(cls, v: str) -> str:
        # validate_source_root raises the typed GitHubError; pydantic
        # needs a ValueError here so invalid input becomes a 422, not a
        # 500. The message (and code text) is preserved.
        from .errors import GitHubError as _GitHubError

        try:
            return validate_source_root(v or ".")
        except _GitHubError as exc:
            raise ValueError(str(exc)) from exc

    @property
    def repository_full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class PullRequestMetadata(BaseModel):
    """Deterministic PR metadata fetched from the GitHub REST API."""

    number: int
    title: str = ""
    state: str = ""
    draft: bool = False
    html_url: str = ""
    author_login: str = ""
    base_ref: str = ""
    base_sha: str = ""
    base_repo_full_name: str = ""
    head_ref: str = ""
    head_sha: str = ""
    head_repo_full_name: str | None = None
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    created_at: str = ""
    updated_at: str = ""


class GitHubChangedFile(BaseModel):
    """One PR file with GitHub provenance, source scope, and the effective
    Phase 3A translation.

    ``status`` is the original GitHub status (never rewritten).
    ``effective_status``/``source_relative_path`` describe what Phase 3A
    actually analyzed (``None`` for outside-scope files, which never enter
    Phase 3A). ``mapping_status``/``mapped_components``/``phase3a_snapshot``
    are filled after the deterministic analysis runs.
    """

    filename: str
    previous_filename: str | None = None
    status: GitHubFileStatus
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    sha: str = ""
    source_scope: SourceScope
    effective_status: ChangeStatus | None = None
    source_relative_path: str | None = None
    source_relative_old_path: str | None = None
    mapping_status: str | None = None
    mapped_components: list[str] = Field(default_factory=list)
    phase3a_snapshot: str | None = None


class SnapshotMetadata(BaseModel):
    """Provenance for one materialized source snapshot."""

    label: str = Field(..., description="'base' or 'head'.")
    repository_full_name: str
    sha: str
    file_count: int = 0
    extracted_bytes: int = 0


class GitHubRateLimit(BaseModel):
    """Safe rate-limit metadata (operational only, never mixed into risk)."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    resource: str | None = None


class GitHubPullRequestAnalysis(BaseModel):
    """Top-level Phase 3B result.

    ``change_set_intelligence`` is the frozen Phase 3A result embedded
    intact; everything else is GitHub-specific metadata and provenance.
    """

    provider: str = "github"
    repository: str
    pull_request: PullRequestMetadata
    source_root: str
    github_files: list[GitHubChangedFile] = Field(default_factory=list)
    in_scope_files: list[GitHubChangedFile] = Field(default_factory=list)
    outside_scope_files: list[GitHubChangedFile] = Field(default_factory=list)
    base_snapshot: SnapshotMetadata
    head_snapshot: SnapshotMetadata
    change_set_intelligence: ChangeSetIntelligence
    rate_limit: GitHubRateLimit | None = None
