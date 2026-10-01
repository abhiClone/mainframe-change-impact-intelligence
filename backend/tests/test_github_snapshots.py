"""Phase 3B: secure snapshot extraction tests.

Archives are built entirely in-test (never downloaded). Every unsafe
case must fail before any filesystem escape: traversal, absolute paths,
symlinks, hard links, device files, FIFOs, and resource-limit breaches.
"""
import io
import os
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from backend.github import GitHubError
from backend.github.snapshots import (
    SnapshotLimits,
    detect_archive_format,
    extract_snapshot,
    source_dir_for,
)

TOP = "owner-repo-abc123"


def make_tar(members, gzip=True):
    """members: list of (name, data|None, kind). kind in file/dir/symlink/
    hardlink/chr/fifo. Returns tar.gz bytes."""
    buf = io.BytesIO()
    mode = "w:gz" if gzip else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tar:
        for name, payload, kind in members:
            info = tarfile.TarInfo(f"{TOP}/{name}")
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "file":
                data = payload or b""
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = payload.decode()
                tar.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = payload.decode()
                tar.addfile(info)
            elif kind == "chr":
                info.type = tarfile.CHRTYPE
                info.devmajor, info.devminor = 1, 5
                tar.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)
            else:
                raise AssertionError(kind)
    return buf.getvalue()


def make_zip(entries):
    """entries: list of (name, data, is_symlink)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data, is_symlink in entries:
            info = zipfile.ZipInfo(name)
            if is_symlink:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zf.writestr(info, "target")
            else:
                zf.writestr(info, data or b"")
    return buf.getvalue()


def extract(archive, limits=None):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "out"
        root = extract_snapshot(archive, dest, limits)
        # Copy results out before the temp dir vanishes.
        found = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        return root_exists(root), found


def root_exists(root):
    return root.is_dir()


GOOD = [
    ("sample_mainframe/copybook/WARRCOPY.cpy", b"copybook", "file"),
    ("sample_mainframe/cobol/WARR002.cbl", b"program", "file"),
    ("sample_mainframe/tests/test_catalog.yaml", b"tests: []", "file"),
]


def test_valid_tarball_nested_project_root(tmp_path):
    archive = make_tar(GOOD)
    root = extract_snapshot(archive, tmp_path / "out")
    assert root.name == TOP
    assert (root / "sample_mainframe" / "copybook" / "WARRCOPY.cpy").read_bytes() == b"copybook"
    assert detect_archive_format(archive) == "tar.gz"


def test_valid_zip(tmp_path):
    archive = make_zip([(f"{TOP}/a.txt", b"hi", False)])
    root = extract_snapshot(archive, tmp_path / "out")
    assert (root / "a.txt").read_bytes() == b"hi"
    assert detect_archive_format(archive) == "zip"


def test_dotdot_traversal_rejected(tmp_path):
    archive = make_tar([("../evil.txt", b"x", "file")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"
    assert not (tmp_path / "evil.txt").exists()


def test_backslash_traversal_rejected(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(f"{TOP}/..\\evil.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(GitHubError) as e:
        extract_snapshot(buf.getvalue(), tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_absolute_path_rejected(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("/etc/evil")  # truly absolute member name
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(GitHubError) as e:
        extract_snapshot(buf.getvalue(), tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_symlink_rejected(tmp_path):
    archive = make_tar(
        GOOD + [("link", b"sample_mainframe", "symlink")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_symlink_escape_rejected(tmp_path):
    archive = make_tar(
        GOOD + [("escape", b"/etc", "symlink")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_hardlink_rejected(tmp_path):
    archive = make_tar(
        GOOD + [("hard", f"{TOP}/sample_mainframe/copybook/WARRCOPY.cpy".encode(), "hardlink")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_device_rejected(tmp_path):
    archive = make_tar(GOOD + [("dev", None, "chr")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_fifo_rejected(tmp_path):
    archive = make_tar(GOOD + [("pipe", None, "fifo")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_zip_symlink_rejected(tmp_path):
    archive = make_zip([(f"{TOP}/link", b"", True)])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_zip_traversal_rejected(tmp_path):
    archive = make_zip([(f"{TOP}/../../evil", b"x", False)])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"


def test_file_count_limit(tmp_path):
    members = [(f"f{i}.txt", b"x", "file") for i in range(10)]
    archive = make_tar(members)
    limits = SnapshotLimits(max_files=5)
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out", limits)
    assert e.value.code == "snapshot_too_large"


def test_individual_file_size_limit(tmp_path):
    archive = make_tar([("big.bin", b"x" * 100, "file")])
    limits = SnapshotLimits(max_file_bytes=10)
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out", limits)
    assert e.value.code == "snapshot_too_large"


def test_total_extracted_bytes_limit(tmp_path):
    members = [(f"f{i}.txt", b"x" * 100, "file") for i in range(5)]
    archive = make_tar(members)
    limits = SnapshotLimits(max_extracted_bytes=200,
                            max_file_bytes=10_000)
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out", limits)
    assert e.value.code == "snapshot_too_large"


def test_archive_download_size_limit(tmp_path):
    archive = make_tar(GOOD)
    limits = SnapshotLimits(max_archive_bytes=10)
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out", limits)
    assert e.value.code == "snapshot_too_large"


def test_unknown_format_rejected(tmp_path):
    with pytest.raises(GitHubError) as e:
        extract_snapshot(b"not-an-archive", tmp_path / "out")
    assert e.value.code == "snapshot_download_failed"


def test_multiple_top_level_dirs_rejected(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for top in ("aaa", "bbb"):
            info = tarfile.TarInfo(f"{top}/f.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(GitHubError) as e:
        extract_snapshot(buf.getvalue(), tmp_path / "out")
    assert e.value.code == "snapshot_download_failed"


def test_source_dir_for(tmp_path):
    archive = make_tar(GOOD)
    root = extract_snapshot(archive, tmp_path / "out")
    src = source_dir_for(root, "sample_mainframe")
    assert (src / "copybook" / "WARRCOPY.cpy").exists()
    assert source_dir_for(root, ".") == root


def test_source_dir_for_missing(tmp_path):
    archive = make_tar(GOOD)
    root = extract_snapshot(archive, tmp_path / "out")
    with pytest.raises(GitHubError) as e:
        source_dir_for(root, "nope")
    assert e.value.code == "analysis_failed"


def test_source_dir_for_symlink_rejected(tmp_path):
    # A symlink inside the tree pointing at the source root: extraction
    # itself must already reject it.
    archive = make_tar(GOOD + [("evil-link", b"sample_mainframe", "symlink")])
    with pytest.raises(GitHubError) as e:
        extract_snapshot(archive, tmp_path / "out")
    assert e.value.code == "unsafe_archive"
