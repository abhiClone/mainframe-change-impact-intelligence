"""Phase 3A change-set providers.

A provider produces a :class:`ChangeSet` (raw changed files). Two
implementations exist:

- :class:`ExplicitFileListProvider` — a supplied list of changed files.
  Works without Git; this is the core Phase 3A input.
- :class:`GitDiffProvider` — local Git metadata only
  (``git diff --name-status <base>...<head>``). No GitHub API, no network.

Security: Git is invoked via subprocess argument lists only (never
``shell=True``); refs are validated against a strict allow-list; the
public HTTP API never accepts repository paths (git mode is CLI/service
layer only).
"""
from __future__ import annotations

import re
import subprocess
import tarfile
from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory

from .mapping import resolve_contained_path
from .models import ChangedFile, ChangeSet

# Conservative allow-list for Git refs: tags, branches, SHAs, HEAD,
# hierarchical names, and ~ / ^ ancestry suffixes (e.g. HEAD~1).
# Anything else is rejected before Git runs.
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/^~]*$")

# git diff --name-status single-letter codes we understand.
_STATUS_MAP = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "T": "unknown",
    "U": "unknown",
    "C": "unknown",
}


def validate_ref(ref: str) -> str:
    """Reject anything that is not a plain Git ref name."""
    if not _REF_RE.match(ref):
        raise ValueError(
            f"invalid git ref {ref!r}: only letters, digits, '_', '.', '-', '/' allowed"
        )
    return ref


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git with an argument list (never shell=True)."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class ChangeSetProvider(ABC):
    """Produces a ChangeSet of raw changed files."""

    @abstractmethod
    def get_changes(self) -> ChangeSet:
        """Return the change set described by this provider."""

    def read_base_file(self, repo_relative_path: str) -> str | None:
        """Base-snapshot bytes for a repo-root-relative path, if available.

        The default implementation offers nothing (explicit file lists
        have no base snapshot); GitDiffProvider overrides it.
        """
        return None


class ExplicitFileListProvider(ChangeSetProvider):
    """Change sets from an explicitly supplied file list (no Git needed)."""

    def __init__(self, files: list[ChangedFile | dict]) -> None:
        normalized: list[ChangedFile] = []
        for entry in files:
            if isinstance(entry, ChangedFile):
                normalized.append(entry)
            else:
                normalized.append(ChangedFile(**entry))
        self._files = normalized

    def get_changes(self) -> ChangeSet:
        return ChangeSet(files=list(self._files), source="explicit")


class GitDiffProvider(ChangeSetProvider):
    """Change sets from local ``git diff --name-status`` metadata.

    ``repository_path`` is the Git working tree; ``source_prefix`` selects
    the subtree holding the Mainframe sources (default
    ``"sample_mainframe"`` so project-level files such as README.md stay
    outside the Mainframe mapping scope but remain visible as unmapped).
    An empty ``source_prefix`` means the Mainframe sources live at the
    repository root (used by tests with temporary repositories).
    """

    def __init__(
        self,
        repository_path: str | Path,
        base_ref: str,
        head_ref: str = "HEAD",
        source_prefix: str = "sample_mainframe",
    ) -> None:
        self.repository_path = Path(repository_path)
        self.base_ref = validate_ref(base_ref)
        self.head_ref = validate_ref(head_ref)
        cleaned_prefix = source_prefix.strip()
        if cleaned_prefix:
            # Validate before stripping slashes: an absolute prefix such
            # as "/abs" must be rejected, not silently normalized to "abs".
            # The prefix selects a subtree inside the repository; it must
            # itself be contained (rejects absolute paths and ``..``).
            resolve_contained_path(self.repository_path, cleaned_prefix)
        self.source_prefix = cleaned_prefix.strip("/")

    # -- ChangeSetProvider -------------------------------------------
    def get_changes(self) -> ChangeSet:
        proc = _git(
            self.repository_path,
            "diff",
            "--name-status",
            "-z",
            f"{self.base_ref}...{self.head_ref}",
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"git diff failed for {self.base_ref}...{self.head_ref}: "
                f"{proc.stderr.strip()}"
            )
        files = [
            self._to_changed_file(path, status, old_path)
            for path, status, old_path in self._parse_name_status(proc.stdout)
        ]
        return ChangeSet(
            files=files,
            source="git-diff",
            base_ref=self.base_ref,
            head_ref=self.head_ref,
        )

    def read_base_file(self, repo_relative_path: str) -> str | None:
        """Return the base-ref bytes of a repo-root-relative path."""
        # Containment first: absolute paths, ``..`` escapes, and symlink
        # escapes are rejected before Git ever sees the path.
        resolve_contained_path(self.repository_path, repo_relative_path)
        proc = _git(
            self.repository_path, "show", f"{self.base_ref}:{repo_relative_path}"
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def read_base_source_file(self, source_relative_path: str) -> str | None:
        """Base bytes for a Mainframe-source-relative path.

        The service works in source-relative space (after
        ``source_prefix`` stripping); this re-attaches the prefix so
        ``git show`` receives the repo-root-relative path it needs.
        """
        repo_path = (
            f"{self.source_prefix}/{source_relative_path}"
            if self.source_prefix
            else source_relative_path
        )
        return self.read_base_file(repo_path)

    # -- tree extraction (deterministic head/base scans) --------------
    def extract_file(self, ref: str, repo_relative_path: str) -> str | None:
        """Single file's bytes at a ref (repo-root-relative path), if present."""
        ref = validate_ref(ref)
        resolve_contained_path(self.repository_path, repo_relative_path)
        proc = _git(self.repository_path, "show", f"{ref}:{repo_relative_path}")
        if proc.returncode != 0:
            return None
        return proc.stdout

    def extract_tree(self, ref: str, dest: Path) -> Path:
        """Extract ``<source_prefix>/`` at ``ref`` into ``dest``.

        Returns the directory holding the Mainframe sources. Uses
        ``git archive`` piped to tarfile (no shell, no working-tree
        mutation) so the analyzed tree always matches the ref exactly.
        """
        validate_ref(ref)
        # Binary capture: git archive writes a tar stream to stdout.
        raw = subprocess.run(
            ["git", "-C", str(self.repository_path), "archive", ref,
             "--", self.source_prefix or "."],
            capture_output=True,
            check=False,
        )
        if raw.returncode != 0:
            raise RuntimeError(
                f"git archive failed for ref {ref!r}: "
                f"{raw.stderr.decode(errors='replace').strip()}"
            )
        import io

        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw.stdout)) as tar:
            tar.extractall(dest, filter="data")
        root = dest / self.source_prefix if self.source_prefix else dest
        return root

    # -- internals ----------------------------------------------------
    def _prefix_relative(self, repo_path: str) -> str:
        """Map a repo-root-relative path into Mainframe-source space."""
        if not self.source_prefix:
            return repo_path
        prefix = self.source_prefix + "/"
        if repo_path == self.source_prefix or repo_path.startswith(prefix):
            return repo_path[len(prefix):].lstrip("/")
        # Outside the Mainframe source subtree: keep the full repo-relative
        # path so the file stays visible (it will map as unmapped).
        return repo_path

    def _to_changed_file(
        self, repo_path: str, status: str, old_path: str | None
    ) -> ChangedFile:
        old = self._prefix_relative(old_path) if old_path else None
        return ChangedFile(
            path=self._prefix_relative(repo_path),
            status=status,  # type: ignore[arg-type]
            old_path=old,
        )

    @staticmethod
    def _parse_name_status(
        output: str,
    ) -> list[tuple[str, str, str | None]]:
        """Parse NUL-separated ``git diff --name-status -z`` output.

        Returns (path, status, old_path) with the repo-root-relative path
        as Git reported it (prefix stripping happens in _to_changed_file).
        """
        tokens = output.split("\0")
        entries: list[tuple[str, str, str | None]] = []
        i = 0
        while i < len(tokens):
            code = tokens[i]
            i += 1
            if not code:
                continue
            kind = code[0]
            status = _STATUS_MAP.get(kind, "unknown")
            if kind == "R" or kind == "C":
                # R100<old><new> (similarity score fused to the code letter)
                old_path = tokens[i] if i < len(tokens) else ""
                new_path = tokens[i + 1] if i + 1 < len(tokens) else ""
                i += 2
                entries.append((new_path, status, old_path or None))
            else:
                path = tokens[i] if i < len(tokens) else ""
                i += 1
                entries.append((path, status, None))
        return [(p, s, o) for p, s, o in entries if p]


def make_temp_dir() -> TemporaryDirectory:
    """TemporaryDirectory helper kept importable for the service layer."""
    return TemporaryDirectory(prefix="changeset-")
