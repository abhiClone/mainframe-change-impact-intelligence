"""Phase 3B service: GitHub PR -> deterministic release intelligence.

Pipeline (read-only GitHub integration)::

    GitHub PR metadata/files (deterministic REST fetch)
      -> exact base/head snapshot materialization (secure extraction)
      -> frozen Phase 3A ChangeSetAnalyzer (unchanged semantics)
      -> deterministic ChangeSetIntelligence (embedded intact)
      -> optional grounded explanation (explains the intelligence only)

GitHub is a change-source provider. It never determines mapping,
dependencies, impact, tests, priorities, DB2 involvement, risks,
checklists, or incident relevance — the frozen Phase 3A engine does,
exactly as for explicit change sets. No parallel GitHub-specific impact
engine exists.

PR metadata (title, author, state, ...) is displayed, never mixed into
technical release risk. The optional AI explainer receives the
deterministic ``ChangeSetIntelligence`` as its factual source; PR
metadata, tokens, archive URLs, and repository source are never sent to
an LLM provider.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.changeset.ai import get_change_set_explainer
from backend.changeset.models import MappedChange
from backend.changeset.service import ChangeSetAnalyzer, build_view

from . import errors as E
from .client import GitHubClient
from .models import (
    GitHubPullRequestAnalysis,
    GitHubRateLimit,
    PullRequestMetadata,
    PullRequestRequest,
    SnapshotMetadata,
    SourceScope,
)
from .provider import GitHubPullRequestProvider, translate_github_files
from .snapshots import (
    SnapshotLimits,
    extract_snapshot,
    source_dir_for,
)


def _split_repo(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").split("/")
    if len(parts) != 2 or not all(parts):
        raise E.analysis_failed(
            f"unexpected repository full name {full_name!r} in PR metadata"
        )
    return parts[0], parts[1]


def _count_snapshot(repo_root: Path) -> tuple[int, int]:
    files = 0
    total = 0
    for p in repo_root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            files += 1
            total += p.stat().st_size
    return files, total


def _materialize(
    client: GitHubClient,
    repo_full_name: str,
    sha: str,
    label: str,
    workdir: Path,
    limits: SnapshotLimits,
    cache: dict[tuple[str, str], bytes],
) -> tuple[Path, SnapshotMetadata]:
    """Download + securely extract one snapshot; return (source_dir, meta)."""
    key = (repo_full_name, sha)
    archive = cache.get(key)
    if archive is None:
        owner, repo = _split_repo(repo_full_name)
        archive = client.download_repository_snapshot(
            owner, repo, sha, limits.max_archive_bytes
        )
        cache[key] = archive
    dest = workdir / label
    repo_root = extract_snapshot(archive, dest, limits)
    file_count, extracted_bytes = _count_snapshot(repo_root)
    meta = SnapshotMetadata(
        label=label,
        repository_full_name=repo_full_name,
        sha=sha,
        file_count=file_count,
        extracted_bytes=extracted_bytes,
    )
    return repo_root, meta


def _attach_provenance(
    files: list, mapped: list[MappedChange]
) -> None:
    """Fill per-file GitHub provenance from the Phase 3A mapping outcome."""
    by_path = {
        f.source_relative_path: f
        for f in files
        if f.source_scope is SourceScope.IN_SOURCE_SCOPE
        and f.source_relative_path
    }
    for m in mapped:
        record = by_path.get(m.file.path)
        if record is None:
            continue
        record.mapping_status = m.mapping_status
        if m.mapping_status == "mapped":
            record.mapped_components = list(m.component_ids)
        elif m.mapping_status == "ambiguous":
            record.mapped_components = list(m.candidate_components)
        record.phase3a_snapshot = (
            m.snapshot if isinstance(m.snapshot, str) else str(m.snapshot)
        )


def analyze_github_pull_request(
    request: PullRequestRequest,
    *,
    client: GitHubClient | None = None,
    explainer=None,
    no_test_catalog: bool = False,
    limits: SnapshotLimits | None = None,
) -> GitHubPullRequestAnalysis:
    """Analyze a GitHub pull request deterministically.

    ``request`` is already validated (pydantic). ``client`` defaults to a
    live client using the server-side ``GITHUB_TOKEN``; tests inject a
    mock-transport client. Temporary snapshots are always cleaned up.
    """
    limits = limits or SnapshotLimits()
    owned_client = client is None
    client = client or GitHubClient(token=GitHubClient.token_from_env())
    rate_limit: GitHubRateLimit | None = None
    try:
        meta, rate_limit = client.get_pull_request(
            request.owner, request.repo, request.pull_number
        )
        raw_files, rate_limit = client.list_pull_request_files(
            request.owner, request.repo, request.pull_number, meta.changed_files
        )
        files = translate_github_files(raw_files, request.source_root)

        with TemporaryDirectory(prefix="github-pr-") as work:
            workdir = Path(work)
            cache: dict[tuple[str, str], bytes] = {}
            base_root, base_meta = _materialize(
                client,
                meta.base_repo_full_name,
                meta.base_sha,
                "base",
                workdir,
                limits,
                cache,
            )
            head_meta: SnapshotMetadata
            try:
                head_repo_name = meta.head_repo_full_name
                if not head_repo_name:
                    # Deleted/unavailable fork: the only deterministic
                    # fallback is the base repository, addressed by the
                    # exact head SHA (content-addressed, never guessed).
                    head_repo_name = meta.base_repo_full_name
                head_root, head_meta = _materialize(
                    client,
                    head_repo_name,
                    meta.head_sha,
                    "head",
                    workdir,
                    limits,
                    cache,
                )
            except E.GitHubError as exc:
                if exc.code in (
                    "repository_not_found_or_not_authorized",
                    "snapshot_download_failed",
                ) and not meta.head_repo_full_name:
                    raise E.head_snapshot_unavailable(
                        "head repository is unavailable and the head SHA "
                        "could not be retrieved from the base repository"
                    ) from exc
                raise

            base_source = source_dir_for(base_root, request.source_root)
            head_source = source_dir_for(head_root, request.source_root)

            provider = GitHubPullRequestProvider(
                files,
                request.source_root,
                meta.base_sha,
                meta.head_sha,
                base_source,
            )
            try:
                analyzer = ChangeSetAnalyzer(
                    build_view(head_source, label="head"),
                    build_view(base_source, label="base"),
                    catalog=[] if no_test_catalog else None,
                )
                intel = analyzer.analyze(
                    provider.get_changes(),
                    provider=provider,
                    explainer=(
                        explainer
                        if explainer is not None
                        else get_change_set_explainer()
                    ),
                )
            except E.GitHubError:
                raise
            except (ValueError, RuntimeError) as exc:
                raise E.analysis_failed(str(exc)) from exc

        _attach_provenance(files, list(intel.mapped_changes))
        _attach_provenance(files, list(intel.ambiguous_changes))
        _attach_provenance(files, list(intel.unmapped_changes))

        return GitHubPullRequestAnalysis(
            repository=request.repository_full_name,
            pull_request=meta,
            source_root=request.source_root,
            github_files=files,
            in_scope_files=[
                f for f in files
                if f.source_scope is SourceScope.IN_SOURCE_SCOPE
            ],
            outside_scope_files=[
                f for f in files
                if f.source_scope is SourceScope.OUTSIDE_SOURCE_SCOPE
            ],
            base_snapshot=base_meta,
            head_snapshot=head_meta,
            change_set_intelligence=intel,
            rate_limit=rate_limit,
        )
    finally:
        if owned_client:
            client.close()


def build_request(
    owner: str, repo: str, pull_number: int, source_root: str = "."
) -> PullRequestRequest:
    """Build a validated request (pydantic surfaces input errors)."""
    return PullRequestRequest(
        owner=owner, repo=repo, pull_number=pull_number, source_root=source_root
    )


def parse_repo_arg(value: str) -> tuple[str, str]:
    """Parse ``owner/repo`` (no URLs, no protocols)."""
    cleaned = (value or "").strip()
    if "://" in cleaned or cleaned.startswith("git@"):
        raise ValueError(
            f"invalid --repo {value!r}: expected 'owner/repo', not a URL"
        )
    parts = cleaned.split("/")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError(
            f"invalid --repo {value!r}: expected 'owner/repo'"
        )
    return parts[0].strip(), parts[1].strip()
