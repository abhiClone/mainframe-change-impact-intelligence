"""Phase 3A tests: deterministic file -> component mapping and providers.

Mapping uses authoritative Phase 1 metadata only (never filename
guessing). Git provider tests use temporary Git repositories created by
the test — the real project history is never mutated.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.changeset.mapping import FileComponentMapper, build_file_index
from backend.changeset.models import ChangedFile
from backend.changeset.providers import (
    ExplicitFileListProvider,
    GitDiffProvider,
    validate_ref,
)
from backend.parsers.repository_scanner import scan_repository

REPO = Path(__file__).resolve().parents[2] / "sample_mainframe"


@pytest.fixture(scope="module")
def mapper() -> FileComponentMapper:
    components, _ = scan_repository(REPO)
    return FileComponentMapper(components)


# ------------------------------------------------------------------
# Mapping: one file -> one component, from Phase 1 metadata
# ------------------------------------------------------------------

def test_program_mapping(mapper: FileComponentMapper):
    m = mapper.map_file(ChangedFile(path="cobol/WARR002.cbl"))
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["program:WARR002"]


def test_copybook_mapping(mapper: FileComponentMapper):
    m = mapper.map_file(ChangedFile(path="copybook/WARRCOPY.cpy"))
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["copybook:WARRCOPY"]


def test_jcl_mapping(mapper: FileComponentMapper):
    m = mapper.map_file(ChangedFile(path="jcl/WARRBTCH.jcl"))
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["job:WARRBTCH"]


def test_proc_mapping_via_parser_fallback():
    """PROC files map deterministically despite scanner metadata.

    The frozen Phase 1 scanner materializes PROCs referenced by JCL with
    source_file="unknown" before proc/*.proc is walked, and setdefault
    keeps the materialized entry. The mapper's parser fallback recovers
    proc:WARRANTY from the actual file using the unchanged Phase 1
    parser — Phase 1 itself is not modified.
    """
    components, _ = scan_repository(REPO)
    mapper = FileComponentMapper(components, repo_root=REPO)
    # Sanity: the frozen metadata really is "unknown" for this component.
    by_id = {c.id: c for c in components}
    assert by_id["proc:WARRANTY"].source_file == "unknown"
    m = mapper.map_file(ChangedFile(path="proc/WARRANTY.proc"))
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["proc:WARRANTY"]
    assert "Phase 1 parsers" in m.note


def test_proc_mapping_end_to_end_impact():
    """A changed PROC file produces real impact through the service."""
    from backend.changeset import ChangeSetAnalyzer, build_view

    analyzer = ChangeSetAnalyzer(build_view(REPO))
    provider = ExplicitFileListProvider([ChangedFile(path="proc/WARRANTY.proc")])
    intel = analyzer.analyze(provider.get_changes(), provider=provider)
    assert [p.component_id for p in intel.per_change_analysis] == ["proc:WARRANTY"]
    # Jobs executing the PROC are impacted.
    assert "job:WARRBTCH" in {
        e.component_id for e in intel.unique_impacted_components
    }


def test_unmapped_file_creates_no_impact(mapper: FileComponentMapper):
    for path in ("README.md", "backend/api/app.py", "docs/ARCHITECTURE.md"):
        m = mapper.map_file(ChangedFile(path=path))
        assert m.mapping_status == "unmapped", path
        assert m.component_ids == []


def test_unresolved_phase1_targets_never_map(mapper: FileComponentMapper):
    # program:CUST002 exists in the graph with source_file "unknown";
    # no file may claim it.
    assert "program:CUST002" not in mapper.file_index.get("cobol/CUST002.cbl", [])
    m = mapper.map_file(ChangedFile(path="cobol/CUST002.cbl"))
    assert m.mapping_status == "unmapped"


# ------------------------------------------------------------------
# Ambiguous files: candidates listed, nothing chosen
# ------------------------------------------------------------------

def test_ambiguous_multi_component_file(mapper: FileComponentMapper):
    m = mapper.map_file(ChangedFile(path="sql/schema.sql"))
    assert m.mapping_status == "ambiguous"
    assert m.component_ids == []
    assert m.candidate_components == [
        "table:CLAIM_HISTORY",
        "table:CUSTOMER",
        "table:VEHICLE",
        "table:WARRANTY",
    ]


def test_valid_ambiguity_resolution(mapper: FileComponentMapper):
    m = mapper.map_file(
        ChangedFile(path="sql/schema.sql"), selected=["table:WARRANTY"]
    )
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["table:WARRANTY"]
    assert m.selected_component_ids == ["table:WARRANTY"]


def test_valid_multi_resolution(mapper: FileComponentMapper):
    m = mapper.map_file(
        ChangedFile(path="sql/schema.sql"),
        selected=["table:CUSTOMER", "table:WARRANTY"],
    )
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["table:CUSTOMER", "table:WARRANTY"]


def test_invalid_ambiguity_resolution_rejected(mapper: FileComponentMapper):
    with pytest.raises(ValueError, match="not in candidates"):
        mapper.map_file(
            ChangedFile(path="sql/schema.sql"), selected=["table:NOPE"]
        )


def test_empty_resolution_rejected(mapper: FileComponentMapper):
    with pytest.raises(ValueError, match="selected no components"):
        mapper.map_file(ChangedFile(path="sql/schema.sql"), selected=[])


# ------------------------------------------------------------------
# Deleted files without a base snapshot: honest uncertainty
# ------------------------------------------------------------------

def test_deleted_file_without_base_snapshot(mapper: FileComponentMapper):
    # A deleted file that is NOT in the current tree cannot be resolved
    # safely without a base snapshot: honest uncertainty, no guessed impact.
    m = mapper.map_file(
        ChangedFile(path="cobol/GONE.cbl", status="deleted")
    )
    assert m.mapping_status == "requires_base_snapshot"
    assert m.component_ids == []


def test_deleted_status_with_head_file_still_maps(mapper: FileComponentMapper):
    # If the file still exists in the scanned tree, head metadata is
    # authoritative and the mapping is deterministic.
    m = mapper.map_file(
        ChangedFile(path="cobol/WARR002.cbl", status="deleted")
    )
    assert m.mapping_status == "mapped"
    assert m.component_ids == ["program:WARR002"]


# ------------------------------------------------------------------
# Deleted files WITH a base snapshot: deterministic parser mapping
# ------------------------------------------------------------------

def test_deleted_base_file_maps_via_parsers(mapper: FileComponentMapper):
    content = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. WARR002.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'WARR001'.\n"
    )
    m = mapper.map_deleted_base_file(
        ChangedFile(path="cobol/WARR002.cbl", status="deleted"), content
    )
    assert m.mapping_status == "mapped"
    assert m.snapshot == "base"
    assert m.component_ids == ["program:WARR002"]


def test_deleted_base_file_unmapped_when_no_component(mapper: FileComponentMapper):
    m = mapper.map_deleted_base_file(
        ChangedFile(path="notes.txt", status="deleted"), "hello\n"
    )
    assert m.mapping_status == "unmapped"
    assert m.snapshot == "base"


# ------------------------------------------------------------------
# Explicit file-list provider
# ------------------------------------------------------------------

def test_explicit_provider_passthrough():
    provider = ExplicitFileListProvider(
        [
            {"path": "copybook/WARRCOPY.cpy", "status": "modified"},
            {"path": "cobol/WARR002.cbl", "status": "modified"},
        ]
    )
    change_set = provider.get_changes()
    assert change_set.source == "explicit"
    assert [f.path for f in change_set.files] == [
        "copybook/WARRCOPY.cpy",
        "cobol/WARR002.cbl",
    ]
    assert provider.read_base_file("copybook/WARRCOPY.cpy") is None


# ------------------------------------------------------------------
# Git diff provider: temporary repositories only
# ------------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **dict(__import__("os").environ),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


@pytest.fixture()
def mini_repo(tmp_path: Path) -> Path:
    """A temporary Git repo with a mini Mainframe tree at its root."""
    repo = tmp_path / "mini"
    (repo / "cobol").mkdir(parents=True)
    (repo / "copybook").mkdir(parents=True)
    (repo / "cobol" / "AAA.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AAA.\n"
        "       PROCEDURE DIVISION.\n"
        "           COPY BBB.\n"
    )
    (repo / "copybook" / "BBB.cpy").write_text("      * copybook BBB\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo


def test_git_provider_modified_and_added(mini_repo: Path):
    (mini_repo / "cobol" / "AAA.cbl").write_text(
        (mini_repo / "cobol" / "AAA.cbl").read_text() + "      * touch\n"
    )
    (mini_repo / "copybook" / "NEW.cpy").write_text("      * new\n")
    _git(mini_repo, "add", ".")
    _git(mini_repo, "commit", "-qm", "head")

    provider = GitDiffProvider(mini_repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert change_set.source == "git-diff"
    by_path = {f.path: f.status for f in change_set.files}
    assert by_path == {
        "cobol/AAA.cbl": "modified",
        "copybook/NEW.cpy": "added",
    }


def test_git_provider_rename(mini_repo: Path):
    _git(mini_repo, "mv", "copybook/BBB.cpy", "copybook/CCC.cpy")
    _git(mini_repo, "commit", "-qm", "rename")

    provider = GitDiffProvider(mini_repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert len(change_set.files) == 1
    entry = change_set.files[0]
    assert entry.status == "renamed"
    assert entry.path == "copybook/CCC.cpy"
    assert entry.old_path == "copybook/BBB.cpy"


def test_git_provider_deletion_and_base_content(mini_repo: Path):
    (mini_repo / "cobol" / "AAA.cbl").unlink()
    _git(mini_repo, "add", "-A")
    _git(mini_repo, "commit", "-qm", "delete aaa")

    provider = GitDiffProvider(mini_repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert len(change_set.files) == 1
    assert change_set.files[0].status == "deleted"
    assert change_set.files[0].path == "cobol/AAA.cbl"
    # Base snapshot bytes are available for the deleted file.
    content = provider.read_base_file("cobol/AAA.cbl")
    assert content is not None and "PROGRAM-ID. AAA." in content


def test_git_provider_rejects_unsafe_ref(mini_repo: Path):
    with pytest.raises(ValueError, match="invalid git ref"):
        GitDiffProvider(mini_repo, "HEAD; rm -rf /", "HEAD", source_prefix="")


def test_validate_ref_allows_normal_refs():
    for ref in ("HEAD", "main", "v1.0.0", "feature/phase3", "abc1234"):
        assert validate_ref(ref) == ref
    with pytest.raises(ValueError):
        validate_ref("HEAD --upload-pack=x")


def test_git_end_to_end_deleted_file_base_snapshot(tmp_path: Path):
    """Full git-mode analysis of a deletion using the base snapshot.

    Base tree: program:MAIN CALLs program:WORKER. Head deletes WORKER.
    The deleted component must map from base bytes (Phase 1 parsers) and
    its impact must be analyzed against the base graph — deterministically,
    without touching the real project history.
    """
    import tempfile

    from backend.changeset import ChangeSetAnalyzer, build_view
    from backend.changeset.providers import GitDiffProvider

    repo = tmp_path / "delrepo"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "MAIN.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MAIN.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'WORKER'.\n"
    )
    (repo / "cobol" / "WORKER.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. WORKER.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'work'.\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "cobol" / "WORKER.cbl").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "delete worker")

    provider = GitDiffProvider(repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert [f.path for f in change_set.files] == ["cobol/WORKER.cbl"]

    with tempfile.TemporaryDirectory(prefix="t-head-") as head_tmp, \
         tempfile.TemporaryDirectory(prefix="t-base-") as base_tmp:
        head_root = provider.extract_tree("HEAD", Path(head_tmp))
        base_root = provider.extract_tree("HEAD~1", Path(base_tmp))
        analyzer = ChangeSetAnalyzer(
            build_view(head_root, label="head"),
            build_view(base_root, label="base"),
            catalog=[],
        )
        intel = analyzer.analyze(change_set, provider=provider)

    assert len(intel.mapped_changes) == 1
    mapped = intel.mapped_changes[0]
    assert mapped.component_ids == ["program:WORKER"]
    assert mapped.snapshot == "base"
    # Impact analyzed against the base graph: MAIN depends on WORKER.
    assert [p.component_id for p in intel.per_change_analysis] == ["program:WORKER"]
    root = intel.per_change_analysis[0]
    assert root.snapshot == "base"
    assert root.impact.direct_impacts == ["program:MAIN"]
    impacted = {e.component_id: e for e in intel.unique_impacted_components}
    assert impacted["program:MAIN"].impacted_by == ["program:WORKER"]


def test_git_provider_source_prefix_strips(mini_repo: Path, tmp_path: Path):
    # source_prefix selects the Mainframe subtree; other files stay visible.
    (mini_repo / "README.md").write_text("# hi\n")
    _git(mini_repo, "add", ".")
    _git(mini_repo, "commit", "-qm", "add readme")
    (mini_repo / "README.md").write_text("# hi v2\n")
    _git(mini_repo, "commit", "-qam", "bump readme")

    provider = GitDiffProvider(
        mini_repo, "HEAD~1", "HEAD", source_prefix="does-not-exist"
    )
    change_set = provider.get_changes()
    assert change_set.files[0].path == "README.md"

    from backend.changeset import ChangeSetAnalyzer, build_view

    # Foreign tree: the sample test catalog does not apply; pass an
    # explicit (empty) catalog so mapping behavior stays testable.
    analyzer = ChangeSetAnalyzer(build_view(mini_repo, label="head"), catalog=[])
    intel = analyzer.analyze(change_set, provider=provider)
    assert intel.unmapped_changes[0].file.path == "README.md"
    assert intel.per_change_analysis == []


# ---------------------------------------------------------------------------
# M6 — path containment: no repository file read may escape the repo root.
# ---------------------------------------------------------------------------

import pathlib as _pathlib


@pytest.fixture()
def contained_repo(tmp_path: Path):
    """A repo root with an in-tree COBOL file and an outside secret.

    Layout::

        tmp/
          repo/                <- repo_root
            cobol/AAA.cbl      <- valid in-tree source
            link.cbl           <- symlink -> ../outside/secret.cbl (escape)
          outside/
            secret.cbl         <- must never be read
            outside.cbl        <- target of ../outside.cbl traversal
    """
    repo = tmp_path / "repo"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "AAA.cbl").write_text(
        "IDENTIFICATION DIVISION.\nPROGRAM-ID. AAA.\n"
        "PROCEDURE DIVISION.\n    STOP RUN.\n"
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.cbl").write_text(
        "IDENTIFICATION DIVISION.\nPROGRAM-ID. SECRET.\n"
        "PROCEDURE DIVISION.\n    STOP RUN.\n"
    )
    (outside / "outside.cbl").write_text("junk\n")
    (repo / "link.cbl").symlink_to(outside / "secret.cbl")
    return repo


@pytest.fixture()
def read_spy(monkeypatch):
    """Record every pathlib read_text call; fail loudly if any occurs."""
    calls: list[str] = []
    original = _pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        calls.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(_pathlib.Path, "read_text", spy)
    return calls


def _contained_mapper(repo: Path) -> FileComponentMapper:
    # The index points at a path that does not exist, so the parser
    # fallback (and its file read) is the only path that can touch disk.
    from backend.models.component import make_component

    comp = make_component("program", "AAA", "PROGRAM", "cobol/OTHER.cbl")
    return FileComponentMapper([comp], repo_root=repo)


@pytest.mark.parametrize(
    "evil",
    [
        "../outside.cbl",          # .. traversal into sibling dir
        "../../secret",            # deeper .. traversal
        "/etc/hostname",           # absolute POSIX path
        "C:\\Windows\\secret.cbl", # Windows drive-letter absolute
        "C:/Windows/secret.cbl",   # Windows drive-letter with slashes
        "\\\\host\\share\\x.cbl",  # Windows UNC absolute
        "cobol/../../outside.cbl", # normalized traversal escaping root
        "link.cbl",                # symlink escaping the repository root
    ],
)
def test_parse_head_file_never_reads_outside_repo(
    contained_repo: Path, read_spy: list[str], evil: str
):
    mapper = _contained_mapper(contained_repo)
    assert mapper._parse_head_file(evil) is None
    assert read_spy == [], f"read_text() called for {evil!r}: {read_spy}"


def test_parse_head_file_valid_in_tree_source(
    contained_repo: Path, read_spy: list[str]
):
    mapper = _contained_mapper(contained_repo)
    assert mapper._parse_head_file("cobol/AAA.cbl") == "program:AAA"
    # The parser fallback may re-read via a temp copy of the content it
    # already read; every read must be the in-tree file or its temp copy.
    assert read_spy, "expected the in-tree source to be read"
    assert read_spy[0].endswith("cobol/AAA.cbl")


def test_resolve_contained_path_rejects_escapes(tmp_path: Path):
    from backend.changeset.mapping import resolve_contained_path

    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError):
        resolve_contained_path(repo, "../outside.cbl")
    with pytest.raises(ValueError):
        resolve_contained_path(repo, "/abs/path.cbl")
    with pytest.raises(ValueError):
        resolve_contained_path(repo, "C:\\abs\\path.cbl")
    # In-tree paths are accepted (the second read is the parser's temp copy
    # of the already-read content).
    assert resolve_contained_path(repo, "cobol/AAA.cbl") == (
        repo / "cobol/AAA.cbl"
    ).resolve()
    with pytest.raises(ValueError):
        resolve_contained_path(repo, "cobol/../copybook/X.cpy")


def test_git_provider_rejects_unsafe_source_prefix(mini_repo: Path):
    with pytest.raises(ValueError):
        GitDiffProvider(mini_repo, "HEAD~1", "HEAD", source_prefix="x/../.")
    with pytest.raises(ValueError):
        GitDiffProvider(mini_repo, "HEAD~1", "HEAD", source_prefix="/abs")
