"""Phase 3B secure snapshot materialization.

Downloads are byte-capped by the client; this module extracts repository
archives (gzip-tar or zip, as served by GitHub's archive endpoint) into a
temporary directory under HIGH-priority security constraints:

- path traversal (``..``), absolute paths, Windows drive paths, UNC paths
- zip-slip / tar-slip: every extracted path must resolve under ``dest``
- symlinks, hard links: rejected before materialization
- device files, FIFOs, sockets and other special objects: rejected
- decompression bombs / uncontrolled disk use: configurable limits on
  archive size, extracted bytes, file count, and individual file size

Limits are fail-closed: exceeding one raises ``snapshot_too_large`` and
nothing is silently truncated. Unsafe members raise ``unsafe_archive``
before any filesystem escape is possible (members are pre-scanned, then
extracted with ``tarfile``'s ``data`` filter as defense-in-depth, then
the materialized tree is re-verified).
"""
from __future__ import annotations

import io
import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import errors as E

_GZIP_MAGIC = b"\x1f\x8b"
_ZIP_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class SnapshotLimits:
    """Conservative, documented, configurable resource limits."""

    max_archive_bytes: int = 100 * 1024 * 1024  # download cap (client-side)
    max_extracted_bytes: int = 256 * 1024 * 1024  # total materialized bytes
    max_files: int = 50_000
    max_file_bytes: int = 20 * 1024 * 1024  # single regular file


def detect_archive_format(archive: bytes) -> str:
    if archive[:2] == _GZIP_MAGIC:
        return "tar.gz"
    if archive[:4] == _ZIP_MAGIC:
        return "zip"
    # Plain (uncompressed) tar as a fallback:ustar magic at offset 257.
    if len(archive) > 262 and archive[257:262] == b"ustar":
        return "tar"
    return "unknown"


def _check_member_name(name: str) -> str:
    """Validate an archive member name; return the normalized posix path.

    Raises ``unsafe_archive`` on absolute paths, ``..`` traversal,
    Windows drive paths, or UNC paths. Backslashes are treated as
    separators so Windows-style traversal cannot slip through.
    """
    normalized = name.replace("\\", "/")
    if not normalized or normalized in ("/", "."):
        raise E.unsafe_archive(name, "empty member name")
    # Absolute / drive / UNC.
    if (
        normalized.startswith("/")
        or normalized.startswith("//")
        or (len(normalized) >= 2 and normalized[1] == ":")
    ):
        raise E.unsafe_archive(name, "absolute path")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts:
        raise E.unsafe_archive(name, "empty member name")
    if ".." in parts:
        raise E.unsafe_archive(name, "path traversal ('..')")
    return "/".join(parts)


def _scan_tar_members(
    tar: tarfile.TarFile, limits: SnapshotLimits
) -> list[tuple[str, int, bool]]:
    """Pre-scan tar members: (safe_name, size, is_dir). Fail closed."""
    members: list[tuple[str, int, bool]] = []
    total = 0
    for info in tar.getmembers():
        name = _check_member_name(info.name)
        if info.issym() or info.islnk():
            raise E.unsafe_archive(info.name, "symlink/hard-link rejected")
        if info.isdev():
            raise E.unsafe_archive(info.name, "device file rejected")
        if info.isfifo():
            raise E.unsafe_archive(info.name, "FIFO rejected")
        if not (info.isfile() or info.isdir()):
            raise E.unsafe_archive(
                info.name, f"unsupported member type {info.type!r}"
            )
        size = info.size if info.isfile() else 0
        if size < 0:
            raise E.unsafe_archive(info.name, "negative member size")
        if info.isfile() and size > limits.max_file_bytes:
            raise E.snapshot_too_large(
                f"archive member {info.name} ({size} bytes) exceeds the "
                f"{limits.max_file_bytes}-byte per-file limit"
            )
        total += size
        if total > limits.max_extracted_bytes:
            raise E.snapshot_too_large(
                "archive exceeds the "
                f"{limits.max_extracted_bytes}-byte extracted-size limit"
            )
        members.append((name, size, info.isdir()))
    if len([m for m in members if not m[2]]) > limits.max_files:
        raise E.snapshot_too_large(
            f"archive exceeds the {limits.max_files}-file limit"
        )
    return members


def _scan_zip_members(
    zf: zipfile.ZipFile, limits: SnapshotLimits
) -> list[tuple[str, int, bool]]:
    members: list[tuple[str, int, bool]] = []
    total = 0
    for info in zf.infolist():
        raw_name = info.filename
        is_dir = raw_name.endswith("/")
        name = _check_member_name(raw_name)
        # Symlink entries smuggled through zip external attributes.
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise E.unsafe_archive(raw_name, "symlink rejected")
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise E.unsafe_archive(
                raw_name, f"unsupported file mode {oct(mode)}"
            )
        size = info.file_size if not is_dir else 0
        if size > limits.max_file_bytes:
            raise E.snapshot_too_large(
                f"archive member {raw_name} ({size} bytes) exceeds the "
                f"{limits.max_file_bytes}-byte per-file limit"
            )
        total += size
        if total > limits.max_extracted_bytes:
            raise E.snapshot_too_large(
                "archive exceeds the "
                f"{limits.max_extracted_bytes}-byte extracted-size limit"
            )
        members.append((name, size, is_dir))
    if len([m for m in members if not m[2]]) > limits.max_files:
        raise E.snapshot_too_large(
            f"archive exceeds the {limits.max_files}-file limit"
        )
    return members


def _resolve_under(dest: Path, name: str) -> Path:
    """Resolve a validated member name under ``dest`` (tar-slip guard)."""
    target = dest.joinpath(*name.split("/"))
    # resolve() without strict: collapses any residual '.' segments; the
    # pre-scan already rejected '..' and absolute paths, this is the
    # second barrier before any write happens.
    resolved = target.resolve()
    if resolved != dest.resolve() and dest.resolve() not in resolved.parents:
        raise E.unsafe_archive(name, "escapes the extraction root")
    return resolved


def extract_snapshot(
    archive: bytes,
    dest: Path,
    limits: SnapshotLimits | None = None,
) -> Path:
    """Securely extract a GitHub repository archive.

    Returns the repository root directory (GitHub archives contain a
    single top-level ``<owner>-<repo>-<sha>/`` directory). Raises
    ``unsafe_archive`` / ``snapshot_too_large`` / ``snapshot_download_failed``
    fail-closed; never partially materializes an unsafe archive.
    """
    limits = limits or SnapshotLimits()
    if len(archive) > limits.max_archive_bytes:
        raise E.snapshot_too_large(
            f"archive ({len(archive)} bytes) exceeds the "
            f"{limits.max_archive_bytes}-byte download limit"
        )
    fmt = detect_archive_format(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if fmt in ("tar.gz", "tar"):
        _extract_tar(archive, dest, limits)
    elif fmt == "zip":
        _extract_zip(archive, dest, limits)
    else:
        raise E.snapshot_download_failed(
            f"unsupported archive format ({fmt}); expected tar.gz or zip"
        )

    _verify_tree(dest, limits)
    return _repo_root(dest)


def _extract_tar(archive: bytes, dest: Path, limits: SnapshotLimits) -> None:
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
    except tarfile.TarError as exc:
        raise E.snapshot_download_failed(
            f"unreadable tar archive: {exc}"
        ) from exc
    with tar:
        members = _scan_tar_members(tar, limits)
        names = {name for name, _, _ in members}
        # Defense in depth: the stdlib "data" filter blocks anything the
        # pre-scan missed (absolute paths, .., devices, FIFOs, links).
        tar.extractall(dest, filter="data")
        # The pre-scan is authoritative: fail if extraction produced
        # anything unexpected.
        _assert_no_extra(dest, names)


def _extract_zip(archive: bytes, dest: Path, limits: SnapshotLimits) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise E.snapshot_download_failed(
            f"unreadable zip archive: {exc}"
        ) from exc
    with zf:
        members = _scan_zip_members(zf, limits)
        written = 0
        for info in zf.infolist():
            name = _check_member_name(info.filename)
            target = _resolve_under(dest, name)
            if info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limits.max_extracted_bytes:
                        raise E.snapshot_too_large(
                            "archive exceeds the "
                            f"{limits.max_extracted_bytes}-byte "
                            "extracted-size limit during materialization"
                        )
                    out.write(chunk)


def _assert_no_extra(dest: Path, expected: set[str]) -> None:
    """Ensure tar extraction produced only pre-scanned members.

    Implicit parent directories created by extraction are allowed; every
    other entry must have been pre-scanned.
    """
    allowed: set[str] = set()
    for name in expected:
        parts = name.split("/")
        for i in range(1, len(parts)):
            allowed.add("/".join(parts[:i]))
    allowed |= expected
    seen: set[str] = set()
    for root, dirs, files in os.walk(dest):
        rel_root = os.path.relpath(root, dest)
        for d in dirs:
            p = d if rel_root == "." else f"{rel_root}/{d}"
            seen.add(p)
        for f in files:
            p = f if rel_root == "." else f"{rel_root}/{f}"
            seen.add(p)
    extra = seen - allowed
    if extra:
        raise E.unsafe_archive(
            sorted(extra)[0], "unexpected extra entry after extraction"
        )


def _verify_tree(dest: Path, limits: SnapshotLimits) -> None:
    """Post-extraction verification: containment, types, actual disk use."""
    root = dest.resolve()
    total = 0
    count = 0
    for dirpath, dirnames, filenames in os.walk(dest):
        for name in list(dirnames) + filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                raise E.unsafe_archive(
                    str(p.relative_to(dest)), "symlink present after extraction"
                )
            resolved = p.resolve()
            if resolved != root and root not in resolved.parents:
                raise E.unsafe_archive(
                    str(p.relative_to(dest)), "escapes the extraction root"
                )
            if p.is_file() and not p.is_symlink():
                count += 1
                total += p.stat().st_size
    if count > limits.max_files:
        raise E.snapshot_too_large(
            f"materialized tree exceeds the {limits.max_files}-file limit"
        )
    if total > limits.max_extracted_bytes:
        raise E.snapshot_too_large(
            "materialized tree exceeds the "
            f"{limits.max_extracted_bytes}-byte extracted-size limit"
        )


def _repo_root(dest: Path) -> Path:
    """Return the single top-level directory of a GitHub archive."""
    entries = list(dest.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        raise E.snapshot_download_failed(
            "unexpected archive layout: expected a single top-level "
            "repository directory"
        )
    return entries[0]


def source_dir_for(repo_root: Path, source_root: str) -> Path:
    """Resolve the Mainframe source directory inside a snapshot.

    ``source_root`` was already validated as a safe relative path; this
    additionally rejects symlink escapes and missing directories.
    """
    from backend.changeset.mapping import resolve_contained_path

    if source_root in (".", ""):
        candidate = repo_root
    else:
        try:
            candidate = resolve_contained_path(repo_root, source_root)
        except ValueError as exc:
            raise E.invalid_source_root(source_root) from exc
    if candidate.is_symlink():
        raise E.unsafe_archive(
            source_root, "source root is a symlink escaping the snapshot"
        )
    if not candidate.is_dir():
        raise E.analysis_failed(
            f"source_root {source_root!r} not found in the snapshot"
        )
    return candidate
