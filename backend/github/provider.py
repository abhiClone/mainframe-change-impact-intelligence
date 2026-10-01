"""Phase 3B provider: GitHub PR -> frozen Phase 3A ``ChangeSet``.

``GitHubPullRequestProvider`` is a Phase 3A ``ChangeSetProvider``. It
translates GitHub file statuses into Phase 3A statuses, classifies every
file as in/out of the configured ``source_root``, and exposes the
materialized base snapshot for deleted/renamed files.

Translation contract (never silently guessed):

- added -> added, modified -> modified, removed -> deleted,
  renamed -> renamed; any other GitHub status raises
  ``unsupported_github_status``.
- Rename across the source-root boundary (four explicit cases):
  inside->inside: Phase 3A ``renamed``;
  outside->inside: Phase 3A ``added`` (GitHub status ``renamed``
  preserved on the file record);
  inside->outside: Phase 3A ``deleted`` (GitHub provenance preserved);
  outside->outside: not sent to Phase 3A (``outside_source_scope``).
- Files outside ``source_root`` never enter the Phase 3A ``ChangeSet``;
  they stay visible on the GitHub file records only.

No HTTP, mapping, impact, test, risk, checklist, or incident logic lives
here — those stay in the frozen Phase 3A modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.changeset.mapping import normalize_path, resolve_contained_path
from backend.changeset.models import ChangedFile, ChangeSet
from backend.changeset.providers import ChangeSetProvider

from . import errors as E
from .models import (
    GitHubChangedFile,
    GitHubFileStatus,
    SourceScope,
    parse_github_count,
)

_GITHUB_TO_PHASE3A = {
    GitHubFileStatus.ADDED: "added",
    GitHubFileStatus.MODIFIED: "modified",
    GitHubFileStatus.REMOVED: "deleted",
    GitHubFileStatus.RENAMED: "renamed",
}


def _in_scope(repo_path: str, source_root: str) -> bool:
    if source_root in (".", ""):
        return True
    return repo_path == source_root or repo_path.startswith(source_root + "/")


def _relative(repo_path: str, source_root: str) -> str:
    """Map a repo-root-relative path into Mainframe-source space."""
    if source_root in (".", ""):
        return repo_path
    prefix = source_root + "/"
    if repo_path.startswith(prefix):
        rel = repo_path[len(prefix):]
        return rel or repo_path  # pathological: file named as the root
    if repo_path == source_root:
        return repo_path  # same pathological case
    return repo_path  # outside scope: keep full path for visibility


def translate_github_files(
    raw_files: list[dict[str, Any]], source_root: str
) -> list[GitHubChangedFile]:
    """Translate raw PR file dicts into scoped ``GitHubChangedFile`` records.

    Raises ``unsupported_github_status`` for unknown statuses and
    ``invalid_source_root``-adjacent failures never occur here (the root is
    validated at request time).
    """
    out: list[GitHubChangedFile] = []
    for raw in raw_files:
        filename = str(raw.get("filename") or "")
        previous = raw.get("previous_filename") or None
        try:
            status = GitHubFileStatus(str(raw.get("status") or ""))
        except ValueError:
            raise E.unsupported_github_status(str(raw.get("status"))) from None
        if not filename:
            raise E.unsupported_github_status("<missing filename>")

        record = GitHubChangedFile(
            filename=filename,
            previous_filename=previous,
            status=status,
            # Upstream count fields are parsed strictly (L2): malformed
            # values become the typed malformed_github_response error,
            # never a raw ValueError.
            additions=parse_github_count(
                raw.get("additions"), field="additions",
                what=f"PR file {filename!r}",
            ),
            deletions=parse_github_count(
                raw.get("deletions"), field="deletions",
                what=f"PR file {filename!r}",
            ),
            changes=parse_github_count(
                raw.get("changes"), field="changes",
                what=f"PR file {filename!r}",
            ),
            sha=str(raw.get("sha") or ""),
            source_scope=SourceScope.OUTSIDE_SOURCE_SCOPE,
        )

        if status is GitHubFileStatus.RENAMED:
            _translate_rename(record, filename, previous, source_root)
        else:
            if _in_scope(filename, source_root):
                record.source_scope = SourceScope.IN_SOURCE_SCOPE
                record.effective_status = _GITHUB_TO_PHASE3A[status]  # type: ignore[assignment]
                record.source_relative_path = _relative(filename, source_root)
        out.append(record)
    return out


def _translate_rename(
    record: GitHubChangedFile,
    filename: str,
    previous: str | None,
    source_root: str,
) -> None:
    if not previous:
        raise E.unsupported_github_status(
            "renamed (missing previous_filename)"
        )
    old_in = _in_scope(previous, source_root)
    new_in = _in_scope(filename, source_root)
    if new_in and old_in:
        # inside -> inside: a genuine Phase 3A rename.
        record.source_scope = SourceScope.IN_SOURCE_SCOPE
        record.effective_status = "renamed"
        record.source_relative_path = _relative(filename, source_root)
        record.source_relative_old_path = _relative(previous, source_root)
    elif new_in and not old_in:
        # outside -> inside: enters Mainframe scope as an addition; the
        # original GitHub status stays on the record for provenance.
        record.source_scope = SourceScope.IN_SOURCE_SCOPE
        record.effective_status = "added"
        record.source_relative_path = _relative(filename, source_root)
    elif old_in and not new_in:
        # inside -> outside: leaves Mainframe scope as a deletion.
        record.source_scope = SourceScope.IN_SOURCE_SCOPE
        record.effective_status = "deleted"
        record.source_relative_path = _relative(previous, source_root)
    else:
        # outside -> outside: visible only, never analyzed.
        record.source_scope = SourceScope.OUTSIDE_SOURCE_SCOPE


class GitHubPullRequestProvider(ChangeSetProvider):
    """Phase 3A provider backed by translated GitHub PR files."""

    def __init__(
        self,
        files: list[GitHubChangedFile],
        source_root: str,
        base_sha: str,
        head_sha: str,
        base_source_dir: Path | str | None = None,
    ) -> None:
        self.files = files
        self.source_root = source_root
        self.base_sha = base_sha
        self.head_sha = head_sha
        self._base_source_dir = (
            Path(base_source_dir) if base_source_dir is not None else None
        )

    # -- ChangeSetProvider -------------------------------------------
    def get_changes(self) -> ChangeSet:
        """The Phase 3A change set: in-scope files only, source-relative."""
        changed = [
            ChangedFile(
                path=normalize_path(f.source_relative_path or ""),
                status=f.effective_status or "unknown",
                old_path=(
                    normalize_path(f.source_relative_old_path)
                    if f.source_relative_old_path
                    else None
                ),
            )
            for f in self.files
            if f.source_scope is SourceScope.IN_SOURCE_SCOPE
            and f.effective_status is not None
            and f.source_relative_path
        ]
        return ChangeSet(
            files=changed,
            source="github-pr",
            base_ref=self.base_sha,
            head_ref=self.head_sha,
        )

    def read_base_source_file(self, source_relative_path: str) -> str | None:
        """Base-snapshot bytes for a source-relative path, if available.

        Used by the frozen Phase 3A mapper for deleted files and rename
        old-paths. Reads from the materialized base snapshot with the same
        containment boundary Phase 3A uses everywhere.
        """
        if self._base_source_dir is None:
            return None
        try:
            candidate = resolve_contained_path(
                self._base_source_dir, source_relative_path
            )
        except ValueError:
            return None
        if not candidate.is_file() or candidate.is_symlink():
            return None
        try:
            return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
