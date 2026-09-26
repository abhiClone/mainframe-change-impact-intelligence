"""Deterministic file -> component mapping for Phase 3A.

The mapper is built from authoritative Phase 1 metadata: the components
produced by ``scan_repository``. Each component carries its ``source_file``
(repo-relative path); the mapper inverts that into a file -> [component]
index. No identifiers are guessed from filenames — a file maps to a
component only if Phase 1 says that component comes from that file.

Outcomes per file:

- exactly one component  -> mapped
- several components     -> ambiguous (candidates listed, nothing chosen)
- no known component     -> unmapped (visible, creates no impact)
- deleted with no base snapshot available -> requires_base_snapshot

Components with ``source_file == "unknown"`` (Phase 1 unresolved
targets) are never mapped from files.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from backend.models.component import Component, make_component
from backend.parsers.cobol_parser import parse_program
from backend.parsers.jcl_parser import parse_job, parse_proc
from backend.parsers.sql_parser import parse_schema

from .models import ChangedFile, MappedChange

_UNKNOWN_SOURCE = "unknown"

# Absolute Windows paths: drive-letter (``C:\`` / ``C:/``) or UNC (``\\host``).
_WINDOWS_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _normalize(path: str) -> str:
    """Normalize a repo-relative path for index lookup."""
    return normalize_path(path)


def normalize_path(path: str) -> str:
    """Public normalization for repo-relative change paths."""
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def resolve_contained_path(repo_root: str | Path, user_path: str) -> Path:
    """Resolve ``user_path`` under ``repo_root`` or raise ``ValueError``.

    Security boundary for every Phase 3 repository file read. Rejects:

    - absolute POSIX paths (``/etc/passwd``),
    - absolute Windows paths (``C:\\temp`` / ``C:/temp`` / UNC ``\\\\host``),
    - ``..`` traversal that escapes the repository root,
    - symlink escapes: the candidate is fully resolved (symlinks followed)
      and must remain under the resolved repository root.

    A ``..`` segment that resolves *inside* the repository is allowed by
    this check (containment is the boundary); mapping still fails closed
    for such paths because only strict ``dir/file`` shapes dispatch to a
    parser. The file is never read when this raises.
    """
    normalized = _normalize(user_path)
    if normalized.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(normalized):
        raise ValueError(f"absolute path not allowed: {user_path!r}")
    # Any ``..`` segment is rejected outright: traversal has no legitimate
    # use in a repo-relative change path, and rejecting it keeps the
    # mapping fail-closed for odd-but-contained inputs too.
    if ".." in [p for p in normalized.split("/") if p not in ("", ".")]:
        raise ValueError(f"path traversal not allowed: {user_path!r}")
    root = Path(repo_root).resolve()
    candidate = (root / normalized).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(
            f"path escapes repository root: {user_path!r}"
        ) from None
    return candidate


def build_file_index(components: list[Component]) -> dict[str, list[str]]:
    """Invert Phase 1 component metadata into file -> [component id].

    Deterministic: component ids are sorted. Files backing more than one
    component (e.g. sql/schema.sql -> several DB2 tables) keep every id.
    """
    index: dict[str, list[str]] = {}
    for comp in components:
        if not comp.source_file or comp.source_file == _UNKNOWN_SOURCE:
            continue
        index.setdefault(_normalize(comp.source_file), []).append(comp.id)
    for ids in index.values():
        ids.sort()
    return index


def _parse_source_content(
    repo_relative_path: str, content: str
) -> list[Component]:
    """Parse Mainframe source bytes with the unchanged Phase 1 parsers.

    Dispatches on directory/extension exactly like ``scan_repository``.
    The content is parsed under its real filename because the Phase 1
    parsers derive component names from the file stem — a random temp
    name would fabricate a wrong component id.
    """
    rel = _normalize(repo_relative_path)
    parts = rel.split("/")
    if len(parts) != 2:
        return []
    directory, filename = parts
    stem = Path(filename).stem.upper()
    suffix = Path(filename).suffix.lower()

    with tempfile.TemporaryDirectory(prefix="changeset-parse-") as tmpdir:
        tmp_path = Path(tmpdir) / f"{stem}{suffix}"
        tmp_path.write_text(content, encoding="utf-8")
        if directory == "copybook" and suffix == ".cpy":
            return [make_component("copybook", stem, "COPYBOOK", rel)]
        if directory == "sql" and suffix == ".sql":
            return parse_schema(tmp_path, rel)
        if directory == "cobol" and suffix == ".cbl":
            comp, _deps = parse_program(tmp_path, rel)
            return [comp]
        if directory == "jcl" and suffix == ".jcl":
            comp, _deps = parse_job(tmp_path, rel)
            return [comp]
        if directory == "proc" and suffix == ".proc":
            comp, _deps = parse_proc(tmp_path, rel)
            return [comp]
    return []


def _components_for_base_content(
    repo_relative_path: str, content: str
) -> list[Component]:
    """Derive component ids for a deleted file from its base content.

    Uses the unchanged Phase 1 parsers on the base-tree file bytes, with
    the same directory/extension dispatch as ``scan_repository``. This is
    the "clean deterministic implementation using the Git base snapshot":
    nothing is guessed, the parsers decide.
    """
    return _parse_source_content(repo_relative_path, content)


class FileComponentMapper:
    """Deterministic mapper from changed files to Phase 1 components."""

    def __init__(
        self, components: list[Component], repo_root: str | Path | None = None
    ) -> None:
        self._index = build_file_index(components)
        self._known_ids = {c.id for c in components}
        self._repo_root = Path(repo_root) if repo_root is not None else None

    @property
    def file_index(self) -> dict[str, list[str]]:
        return dict(self._index)

    def map_file(
        self,
        changed: ChangedFile,
        selected: list[str] | None = None,
    ) -> MappedChange:
        """Map one changed file to its confirmed component(s)."""
        path = _normalize(changed.path)
        normalized = ChangedFile(
            path=path, status=changed.status, old_path=changed.old_path
        )
        candidates = self._index.get(path, [])
        via_parser_fallback = False

        if not candidates:
            # Parser fallback: the frozen Phase 1 scanner materializes
            # referenced-but-not-yet-scanned targets with
            # source_file="unknown" and never replaces them when the real
            # definition is scanned later (e.g. PROCs referenced by JCL
            # before proc/*.proc is walked). Parsing the actual file with
            # the unchanged Phase 1 parsers recovers the true component
            # deterministically — no filename guessing, no Phase 1 change.
            fallback = self._parse_head_file(path)
            if fallback:
                candidates = [fallback]
                via_parser_fallback = True

        if not candidates:
            if changed.status == "deleted":
                return MappedChange(
                    file=normalized,
                    mapping_status="requires_base_snapshot",
                    note=(
                        "Deleted file is not present in the current tree and "
                        "no base snapshot was supplied; its previous "
                        "dependencies cannot be proven. No impact guessed."
                    ),
                )
            return MappedChange(
                file=normalized,
                mapping_status="unmapped",
                note=(
                    "File does not represent a known Mainframe component; "
                    "it stays visible but creates no Mainframe impact."
                ),
            )

        if len(candidates) > 1:
            if selected is not None:
                # Duplicate selections are deduplicated (M3); the
                # resolution still analyses the component exactly once.
                deduped = list(dict.fromkeys(selected))
                self._validate_selection(path, candidates, deduped)
                return MappedChange(
                    file=normalized,
                    mapping_status="mapped",
                    component_ids=sorted(deduped),
                    candidate_components=list(candidates),
                    selected_component_ids=sorted(deduped),
                    note=(
                        "Ambiguous file explicitly resolved to the selected "
                        "component(s); every selection was a valid candidate."
                    ),
                )
            return MappedChange(
                file=normalized,
                mapping_status="ambiguous",
                candidate_components=list(candidates),
                note=(
                    "File maps to multiple components; no component was "
                    "chosen automatically. Explicit resolution required."
                ),
            )

        return MappedChange(
            file=normalized,
            mapping_status="mapped",
            component_ids=list(candidates),
            note=(
                "File maps to exactly one known component "
                "(resolved via the Phase 1 parsers; scanner metadata was "
                "'unknown')."
                if via_parser_fallback
                else "File maps to exactly one known component."
            ),
        )

    def _parse_head_file(self, path: str) -> str | None:
        """Map a file via the Phase 1 parsers when the index misses.

        Returns the component id when the parsed id is a known graph
        component, else None. Only fires for files that exist in the
        scanned tree; deleted files keep their base-snapshot path. The
        candidate path is containment-checked before any read: absolute
        paths, ``..`` escapes, and symlink escapes fail closed (None).
        """
        if self._repo_root is None:
            return None
        try:
            disk_path = resolve_contained_path(self._repo_root, path)
        except ValueError:
            return None
        if not disk_path.is_file():
            return None
        try:
            content = disk_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for comp in _parse_source_content(path, content):
            if comp.id in self._known_ids:
                return comp.id
        return None

    def map_deleted_base_file(
        self, changed: ChangedFile, content: str
    ) -> MappedChange:
        """Map a deleted file using its Git base-snapshot content.

        Called by the Git diff provider, which supplies the file bytes
        from the base ref. Component ids come from the Phase 1 parsers,
        never from filename guessing.
        """
        path = _normalize(changed.path)
        normalized = ChangedFile(
            path=path, status=changed.status, old_path=changed.old_path
        )
        components = _components_for_base_content(path, content)
        ids = sorted({c.id for c in components})
        if not ids:
            return MappedChange(
                file=normalized,
                mapping_status="unmapped",
                snapshot="base",
                note=(
                    "Base-snapshot content yields no known Mainframe "
                    "component; no impact created."
                ),
            )
        if len(ids) > 1:
            return MappedChange(
                file=normalized,
                mapping_status="ambiguous",
                candidate_components=ids,
                snapshot="base",
                note=(
                    "Base-snapshot content maps to multiple components; "
                    "explicit resolution required before impact analysis."
                ),
            )
        return MappedChange(
            file=normalized,
            mapping_status="mapped",
            component_ids=ids,
            snapshot="base",
            note=(
                "Deleted component resolved deterministically from the "
                "Git base snapshot via the Phase 1 parsers."
            ),
        )

    @staticmethod
    def _validate_selection(
        path: str, candidates: list[str], selected: list[str]
    ) -> None:
        if not selected:
            raise ValueError(
                f"explicit resolution for '{path}' selected no components"
            )
        unknown = [s for s in selected if s not in candidates]
        if unknown:
            raise ValueError(
                f"invalid resolution for '{path}': {', '.join(unknown)} "
                f"not in candidates {', '.join(candidates)}"
            )
