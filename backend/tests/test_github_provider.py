"""Phase 3B: status translation, source-scope, and provider tests."""
import pytest

from backend.github import GitHubError
from backend.github.models import SourceScope, validate_source_root
from backend.github.provider import (
    GitHubPullRequestProvider,
    translate_github_files,
)

ROOT = "sample_mainframe"


def raw(filename, status="modified", prev=None):
    return {
        "filename": filename,
        "previous_filename": prev,
        "status": status,
        "additions": 1,
        "deletions": 0,
        "changes": 1,
        "sha": "0" * 40,
    }


# ------------------------------------------------------------------
# Source-root validation
# ------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "..", "../x", "a/../..", "/tmp/x", "/abs", "C:\\repo", "C:/repo",
    "//host/share", "\\\\host\\share", "a/../../b",
])
def test_source_root_rejects_unsafe(bad):
    with pytest.raises(GitHubError) as e:
        validate_source_root(bad)
    assert e.value.code == "invalid_source_root"


@pytest.mark.parametrize("good,expected", [
    (".", "."), ("", "."), ("sample_mainframe", "sample_mainframe"),
    ("a/b", "a/b"), ("./x", "x"), ("x/", "x"),
])
def test_source_root_accepts_safe(good, expected):
    assert validate_source_root(good) == expected


# ------------------------------------------------------------------
# Status translation
# ------------------------------------------------------------------

@pytest.mark.parametrize("gh,eff", [
    ("added", "added"), ("modified", "modified"),
    ("removed", "deleted"), ("renamed", "renamed"),
])
def test_status_translation(gh, eff):
    prev = f"{ROOT}/cobol/OLD.cbl" if gh == "renamed" else None
    name = f"{ROOT}/cobol/NEW.cbl" if gh == "renamed" else f"{ROOT}/cobol/X.cbl"
    (f,) = translate_github_files([raw(name, gh, prev)], ROOT)
    assert f.status.value == gh  # GitHub status preserved
    assert f.effective_status == eff
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE


def test_unknown_status_fails_closed():
    with pytest.raises(GitHubError) as e:
        translate_github_files([raw(f"{ROOT}/x.cbl", "copied")], ROOT)
    assert e.value.code == "unsupported_github_status"


def test_rename_without_previous_filename_fails():
    with pytest.raises(GitHubError) as e:
        translate_github_files([raw(f"{ROOT}/x.cbl", "renamed", None)], ROOT)
    assert e.value.code == "unsupported_github_status"


# ------------------------------------------------------------------
# Scope classification
# ------------------------------------------------------------------

def test_in_scope_modified():
    (f,) = translate_github_files([raw(f"{ROOT}/copybook/WARRCOPY.cpy")], ROOT)
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.source_relative_path == "copybook/WARRCOPY.cpy"
    assert f.effective_status == "modified"


def test_outside_scope_modified():
    (f,) = translate_github_files([raw("README.md")], ROOT)
    assert f.source_scope is SourceScope.OUTSIDE_SOURCE_SCOPE
    assert f.effective_status is None
    assert f.source_relative_path is None


def test_dot_root_scopes_everything():
    (f,) = translate_github_files([raw("README.md")], ".")
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.source_relative_path == "README.md"


def test_nested_source_root():
    (f,) = translate_github_files(
        [raw("nested/source/mainframe/cobol/X.cbl")], "nested/source/mainframe")
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.source_relative_path == "cobol/X.cbl"


# ------------------------------------------------------------------
# Rename boundary: all four cases
# ------------------------------------------------------------------

def test_rename_inside_to_inside():
    (f,) = translate_github_files(
        [raw(f"{ROOT}/cobol/B.cbl", "renamed", f"{ROOT}/cobol/A.cbl")], ROOT)
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.effective_status == "renamed"
    assert f.source_relative_path == "cobol/B.cbl"
    assert f.source_relative_old_path == "cobol/A.cbl"
    assert f.status.value == "renamed"  # GitHub status preserved


def test_rename_outside_to_inside_is_added():
    (f,) = translate_github_files(
        [raw(f"{ROOT}/cobol/C.cbl", "renamed", "docs/C.cbl")], ROOT)
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.effective_status == "added"
    assert f.source_relative_path == "cobol/C.cbl"
    assert f.source_relative_old_path is None
    assert f.status.value == "renamed"


def test_rename_inside_to_outside_is_deleted():
    (f,) = translate_github_files(
        [raw("docs/D.cbl", "renamed", f"{ROOT}/cobol/D.cbl")], ROOT)
    assert f.source_scope is SourceScope.IN_SOURCE_SCOPE
    assert f.effective_status == "deleted"
    assert f.source_relative_path == "cobol/D.cbl"
    assert f.status.value == "renamed"


def test_rename_outside_to_outside_not_analyzed():
    (f,) = translate_github_files(
        [raw("docs/E.md", "renamed", "docs/F.md")], ROOT)
    assert f.source_scope is SourceScope.OUTSIDE_SOURCE_SCOPE
    assert f.effective_status is None


# ------------------------------------------------------------------
# Provider -> Phase 3A ChangeSet
# ------------------------------------------------------------------

def test_provider_excludes_outside_scope(tmp_path):
    files = translate_github_files([
        raw(f"{ROOT}/copybook/WARRCOPY.cpy"),
        raw("README.md"),
        raw("frontend/src/App.tsx"),
    ], ROOT)
    provider = GitHubPullRequestProvider(
        files, ROOT, "a" * 40, "b" * 40)
    change_set = provider.get_changes()
    assert change_set.source == "github-pr"
    assert change_set.base_ref == "a" * 40
    assert change_set.head_ref == "b" * 40
    assert [f.path for f in change_set.files] == ["copybook/WARRCOPY.cpy"]


def test_provider_read_base_source_file(tmp_path):
    base = tmp_path / "base"
    (base / "copybook").mkdir(parents=True)
    (base / "copybook" / "OLD.cbl").write_text("base-bytes")
    (base / "evil.txt").write_text("x")
    files = translate_github_files(
        [raw(f"{ROOT}/copybook/OLD.cbl", "removed")], ROOT)
    provider = GitHubPullRequestProvider(
        files, ROOT, "a" * 40, "b" * 40, base)
    assert provider.read_base_source_file("copybook/OLD.cbl") == "base-bytes"
    assert provider.read_base_source_file("copybook/MISSING.cbl") is None
    # Traversal is contained: never reads outside the snapshot.
    assert provider.read_base_source_file("../../evil.txt") is None
    assert provider.read_base_source_file("/etc/passwd") is None


def test_provider_without_snapshot_returns_none():
    files = translate_github_files(
        [raw(f"{ROOT}/copybook/OLD.cbl", "removed")], ROOT)
    provider = GitHubPullRequestProvider(files, ROOT, "a" * 40, "b" * 40)
    assert provider.read_base_source_file("copybook/OLD.cbl") is None
