#!/usr/bin/env python3
"""Phase 3B CLI: deterministic impact analysis of a GitHub pull request.

Read-only GitHub integration. The token comes ONLY from the GITHUB_TOKEN
environment variable -- there is deliberately no --token flag, and the
token is never printed, logged, or included in output.

Examples:
    python github_pr.py --repo abhiClone/mainframe-change-impact-intelligence \\
        --pr 42 --source-root sample_mainframe
    python github_pr.py --repo abhiClone/mainframe-change-impact-intelligence \\
        --pr 42 --json
"""
from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from backend.github import (
    GitHubError,
    analyze_github_pull_request,
    build_request,
    parse_repo_arg,
)
from backend.github.models import SourceScope
from changeset import _print_human as _print_change_set_human


def _short(sha: str) -> str:
    return sha[:7] if sha else "?"


def _print_pr_human(result) -> None:
    pr = result.pull_request
    print("=" * 72)
    print("GITHUB PULL REQUEST (read-only provider -> deterministic analysis)")
    print("=" * 72)
    print()
    print(f"Repository : {result.repository}")
    print(f"PR #{pr.number} : {pr.title}")
    print(f"State      : {pr.state}"
          + (" (draft)" if pr.draft else "")
          + f"  author: {pr.author_login or '?'}")
    print(f"URL        : {pr.html_url}")
    print(f"Base       : {pr.base_ref} @ {_short(pr.base_sha)}"
          f"  ({pr.base_repo_full_name})")
    head_repo = pr.head_repo_full_name or pr.base_repo_full_name
    fork = "  [fork]" if pr.head_repo_full_name and (
        pr.head_repo_full_name != pr.base_repo_full_name) else ""
    print(f"Head       : {pr.head_ref} @ {_short(pr.head_sha)}"
          f"  ({head_repo}){fork}")
    print(f"Source root: {result.source_root}")
    print(f"Files      : {pr.changed_files} changed "
          f"(+{pr.additions}/-{pr.deletions})")
    print()
    print(f"Changed files ({len(result.github_files)}):")
    for f in result.github_files:
        scope = ("IN SCOPE" if f.source_scope is SourceScope.IN_SOURCE_SCOPE
                 else "OUTSIDE SOURCE ROOT")
        prev = (f"  (was: {f.previous_filename})"
                if f.previous_filename else "")
        mapping = ""
        if f.mapping_status == "mapped":
            mapping = f" -> {', '.join(f.mapped_components)}"
        elif f.mapping_status:
            mapping = f" [{f.mapping_status}]"
        print(f"  [{f.status.value}] {f.filename}{prev}")
        print(f"      +{f.additions}/-{f.deletions}  {scope}{mapping}")
    print()
    print("Snapshots (exact PR SHAs, temporary, cleaned after analysis):")
    for snap in (result.base_snapshot, result.head_snapshot):
        print(f"  {snap.label}: {snap.repository_full_name}@{_short(snap.sha)} "
              f"({snap.file_count} files)")
    if result.rate_limit and result.rate_limit.remaining is not None:
        print(f"GitHub API rate limit: {result.rate_limit.remaining} remaining")
    print()
    print("VERIFIED PR CHANGE SET: the file list above came deterministically")
    print("from GitHub PR metadata. Impact below is deterministic Phase 3A")
    print("analysis of the exact base/head snapshots.")
    print()
    _print_change_set_human(result.change_set_intelligence)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic Mainframe impact analysis of a GitHub PR."
    )
    parser.add_argument("--repo", required=True,
                        help="GitHub repository as 'owner/name' (no URLs).")
    parser.add_argument("--pr", required=True, type=int,
                        help="Pull request number (> 0).")
    parser.add_argument("--source-root", default="sample_mainframe",
                        help="Repository-relative Mainframe source root "
                             "(default: sample_mainframe).")
    parser.add_argument("--json", action="store_true",
                        help="Print the full result as JSON.")
    parser.add_argument("--no-test-catalog", action="store_true",
                        help="Analyze without test recommendations.")
    args = parser.parse_args()

    try:
        owner, repo = parse_repo_arg(args.repo)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        request = build_request(owner, repo, args.pr, args.source_root)
    except ValidationError as exc:
        print(f"error: invalid input: {exc.errors()[0]['msg']}",
              file=sys.stderr)
        return 2

    try:
        result = analyze_github_pull_request(
            request, no_test_catalog=args.no_test_catalog
        )
    except GitHubError as exc:
        print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        _print_pr_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
