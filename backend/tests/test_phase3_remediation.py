"""Phase 3A remediation regression tests (M1-M8, L1, L2).

Each test pins one remediated behavior. Temporary repositories and
directories only; the real project history is never touched.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.changeset import (
    ChangeSetAnalyzer,
    ExplicitFileListProvider,
    build_view,
)
from backend.changeset.models import (
    AggregatedResource,
    AggregatedSignal,
    AggregatedTest,
    ChangedFile,
    ChangeSet,
    MappedChange,
    PerChangeAnalysis,
    PerRootTest,
)
from backend.changeset.providers import GitDiffProvider

REPO = Path(__file__).resolve().parents[2] / "sample_mainframe"

WARRCOPY = "copybook:WARRCOPY"
WARR002 = "program:WARR002"
WARR001 = "program:WARR001"


@pytest.fixture(scope="module")
def analyzer() -> ChangeSetAnalyzer:
    return ChangeSetAnalyzer(build_view(REPO))


def _analyze(analyzer, files, resolutions=None):
    provider = ExplicitFileListProvider(files)
    return analyzer.analyze(
        provider.get_changes(), resolutions=resolutions or {}, provider=provider
    )


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **dict(os.environ),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _normalize_dump(intel) -> dict:
    """Order-normalized dump: input display order may differ, semantics not."""
    d = intel.model_dump(mode="json")
    d["mapped_changes"] = sorted(
        d["mapped_changes"], key=lambda m: m["file"]["path"]
    )
    d["per_change_analysis"] = sorted(
        d["per_change_analysis"], key=lambda p: p["component_id"]
    )
    d["change_set"]["files"] = sorted(
        d["change_set"]["files"], key=lambda f: f["path"]
    )
    return d


# ------------------------------------------------------------------
# M1 — root-order-invariant release prose
# ------------------------------------------------------------------

def test_root_order_invariant_aggregate(analyzer):
    a = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
    )
    b = _analyze(
        analyzer,
        [{"path": "cobol/WARR002.cbl"}, {"path": "copybook/WARRCOPY.cpy"}],
    )
    na, nb = _normalize_dump(a), _normalize_dump(b)
    # Human-readable release prose must be identical...
    for section in (
        "risk_signals",
        "release_checklist",
        "deterministic_summary",
    ):
        assert na[section] == nb[section], section
    # ...and so must every structured aggregate section.
    for section in (
        "unique_impacted_components",
        "recommended_tests",
        "involved_resources",
        "relevant_incidents",
        "changed_components",
        "summary",
        "impacted_by_one_change",
        "impacted_by_multiple_changes",
    ):
        assert na[section] == nb[section], section


def test_release_prose_not_first_root_prose(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "cobol/WARR002.cbl"}, {"path": "copybook/WARRCOPY.cpy"}],
    )
    # Even though WARR002 was processed first, the release explanation
    # is built from merged data (both writers appear, sorted).
    sig = next(s for s in intel.risk_signals if s.id == "DB2_WRITE_INVOLVED")
    assert "program:WARR001" in sig.explanation
    assert "program:WARR002" in sig.explanation
    assert sig.explanation.index("program:WARR001") < sig.explanation.index(
        "program:WARR002"
    )


def test_evidence_order_deterministic(analyzer):
    a = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
    )
    b = _analyze(
        analyzer,
        [{"path": "cobol/WARR002.cbl"}, {"path": "copybook/WARRCOPY.cpy"}],
    )
    for ta, tb in zip(a.recommended_tests, b.recommended_tests):
        assert ta.test_id == tb.test_id
        ka = [(e.file, e.line, e.text) for e in ta.evidence]
        kb = [(e.file, e.line, e.text) for e in tb.evidence]
        assert ka == kb
        # Aggregated evidence order is deterministic (sorted), not
        # first-root-wins.
        assert ka == sorted(ka)


# ------------------------------------------------------------------
# M2 — changed vs downstream impacted
# ------------------------------------------------------------------

def test_warrcopy_warr001_cross_impact(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR001.cbl"}],
    )
    changed = {c.component_id: c for c in intel.changed_components}
    assert set(changed) == {WARRCOPY, WARR001}
    cross = changed[WARR001].also_impacted_by
    assert [(r.change_root, r.snapshot) for r in cross] == [(WARRCOPY, "head")]
    impacted = {e.component_id for e in intel.unique_impacted_components}
    assert WARRCOPY not in impacted and WARR001 not in impacted
    assert intel.summary.cross_impacted_changed_components == 1


# ------------------------------------------------------------------
# M3 — duplicate inputs
# ------------------------------------------------------------------

def test_duplicate_file_deduplicated(analyzer):
    intel = _analyze(
        analyzer,
        [
            {"path": "copybook/WARRCOPY.cpy"},
            {"path": "copybook/WARRCOPY.cpy"},
            {"path": "./copybook/WARRCOPY.cpy"},
        ],
    )
    assert len(intel.per_change_analysis) == 1
    assert intel.summary.changed_files == 1
    assert intel.summary.changed_components == 1
    changed = intel.changed_components[0]
    assert changed.component_id == WARRCOPY
    assert changed.originating_files == ["copybook/WARRCOPY.cpy"]


def test_conflicting_statuses_rejected(analyzer):
    provider = ExplicitFileListProvider(
        [
            {"path": "copybook/WARRCOPY.cpy", "status": "modified"},
            {"path": "copybook/WARRCOPY.cpy", "status": "deleted"},
        ]
    )
    with pytest.raises(ValueError, match="conflicting statuses"):
        analyzer.analyze(provider.get_changes(), provider=provider)


def test_duplicate_ambiguity_resolution_deduplicated(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "sql/schema.sql"}],
        resolutions={"sql/schema.sql": ["table:WARRANTY", "table:WARRANTY"]},
    )
    assert [p.component_id for p in intel.per_change_analysis] == [
        "table:WARRANTY"
    ]
    assert intel.summary.changed_components == 1


def test_two_files_one_component_analyzed_once(analyzer):
    # Unit-level: two mapped files resolving to the same component yield
    # one root-plan entry with both originating files preserved.
    m1 = MappedChange(
        file=ChangedFile(path="copybook/A.cpy"),
        mapping_status="mapped",
        component_ids=[WARRCOPY],
    )
    m2 = MappedChange(
        file=ChangedFile(path="copybook/B.cpy"),
        mapping_status="mapped",
        component_ids=[WARRCOPY],
    )
    plan = analyzer._build_root_plan([m1, m2])
    assert len(plan) == 1
    assert plan[0].component_id == WARRCOPY
    assert plan[0].originating_files == ["copybook/A.cpy", "copybook/B.cpy"]


# ------------------------------------------------------------------
# M4 — snapshot provenance
# ------------------------------------------------------------------

def _mixed_repo(tmp_path: Path) -> Path:
    """Temp git repo: base has DEL (called by KEEP) + MOD; head deletes DEL
    and modifies MOD."""
    repo = tmp_path / "mixed"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "DEL.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. DEL.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'del'.\n"
    )
    (repo / "cobol" / "KEEP.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. KEEP.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'DEL'.\n"
    )
    (repo / "cobol" / "MOD.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MOD.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'v1'.\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "cobol" / "DEL.cbl").unlink()
    (repo / "cobol" / "MOD.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MOD.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'v2'.\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "delete del, modify mod")
    return repo


def test_mixed_snapshot_release(tmp_path: Path):
    repo = _mixed_repo(tmp_path)
    provider = GitDiffProvider(repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert {f.path for f in change_set.files} == {
        "cobol/DEL.cbl",
        "cobol/MOD.cbl",
    }
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

    assert intel.mixed_snapshot_analysis is True
    by_root = {p.component_id: p for p in intel.per_change_analysis}
    assert by_root["program:DEL"].snapshot == "base"
    assert by_root["program:MOD"].snapshot == "head"
    # Base evidence stays attributable: KEEP called DEL in the base graph.
    impacted = {e.component_id: e for e in intel.unique_impacted_components}
    assert "program:KEEP" in impacted
    keep = impacted["program:KEEP"]
    assert [(p.change_root, p.snapshot) for p in keep.per_root] == [
        ("program:DEL", "base")
    ]
    # The deterministic summary says both snapshots contributed.
    assert "base" in intel.deterministic_summary
    assert "head" in intel.deterministic_summary
    # Changed components carry their own snapshots.
    changed = {c.component_id: c for c in intel.changed_components}
    assert changed["program:DEL"].snapshot == "base"
    assert changed["program:MOD"].snapshot == "head"


def test_single_snapshot_release_not_mixed(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
    )
    assert intel.mixed_snapshot_analysis is False
    assert "Mixed snapshot" not in intel.deterministic_summary


# ------------------------------------------------------------------
# M5 — rename semantics
# ------------------------------------------------------------------

def _rename_repo(tmp_path: Path, new_program_id: str) -> Path:
    """Temp git repo: base has AAA (called by CALLER); head renames
    cobol/AAA.cbl -> cobol/ZZZ.cbl, optionally changing PROGRAM-ID."""
    repo = tmp_path / "rn"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "AAA.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AAA.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'aaa'.\n"
    )
    (repo / "cobol" / "CALLER.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CALLER.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'AAA'.\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "mv", "cobol/AAA.cbl", "cobol/ZZZ.cbl")
    (repo / "cobol" / "ZZZ.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {new_program_id}.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'aaa'.\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "rename aaa to zzz")
    return repo


def _analyze_rename(repo: Path) -> object:
    provider = GitDiffProvider(repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    assert len(change_set.files) == 1
    assert change_set.files[0].status == "renamed"
    with tempfile.TemporaryDirectory(prefix="t-head-") as head_tmp, \
         tempfile.TemporaryDirectory(prefix="t-base-") as base_tmp:
        head_root = provider.extract_tree("HEAD", Path(head_tmp))
        base_root = provider.extract_tree("HEAD~1", Path(base_tmp))
        analyzer = ChangeSetAnalyzer(
            build_view(head_root, label="head"),
            build_view(base_root, label="base"),
            catalog=[],
        )
        return analyzer.analyze(change_set, provider=provider)


def test_rename_unchanged_identity_analyzed_once(tmp_path: Path):
    """SQL table identity comes from DDL content, not the filename: a pure
    rename of a single-table DDL file keeps the component identity and is
    analysed exactly once (head)."""
    repo = tmp_path / "rnsql"
    (repo / "sql").mkdir(parents=True)
    (repo / "sql" / "one.sql").write_text(
        "CREATE TABLE SOLO (\n  ID CHAR(8) NOT NULL\n);\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "mv", "sql/one.sql", "sql/two.sql")
    _git(repo, "commit", "-qm", "rename ddl")
    intel = _analyze_rename(repo)
    mapped = intel.mapped_changes[0]
    assert mapped.file.status == "renamed"
    assert mapped.previous_component_ids == ["table:SOLO"]
    assert mapped.current_component_ids == ["table:SOLO"]
    # Same identity on both sides: one analysis, on head.
    assert [p.component_id for p in intel.per_change_analysis] == ["table:SOLO"]
    assert intel.per_change_analysis[0].snapshot == "head"
    assert intel.mixed_snapshot_analysis is False


def test_rename_same_identity_plan_unit(analyzer):
    # Unit-level: previous == current identities analyse once (head).
    m = MappedChange(
        file=ChangedFile(
            path="sql/two.sql", status="renamed", old_path="sql/one.sql"
        ),
        mapping_status="mapped",
        component_ids=["table:SOLO"],
        previous_component_ids=["table:SOLO"],
        current_component_ids=["table:SOLO"],
    )
    plan = analyzer._build_root_plan([m])
    assert len(plan) == 1
    assert plan[0].component_id == "table:SOLO"
    assert plan[0].snapshot == "head"


def test_rename_identity_change(tmp_path: Path):
    intel = _analyze_rename(_rename_repo(tmp_path, "ZZZ"))
    mapped = intel.mapped_changes[0]
    assert mapped.file.status == "renamed"
    assert mapped.previous_component_ids == ["program:AAA"]
    assert mapped.current_component_ids == ["program:ZZZ"]
    assert sorted(mapped.component_ids) == ["program:AAA", "program:ZZZ"]
    # Old identity analysed on base, new identity on head.
    by_root = {p.component_id: p for p in intel.per_change_analysis}
    assert by_root["program:AAA"].snapshot == "base"
    assert by_root["program:ZZZ"].snapshot == "head"
    # Callers of the old component do not disappear: CALLER called AAA
    # in the base graph.
    impacted = {e.component_id: e for e in intel.unique_impacted_components}
    assert "program:CALLER" in impacted
    caller = impacted["program:CALLER"]
    assert [(p.change_root, p.snapshot) for p in caller.per_root] == [
        ("program:AAA", "base")
    ]
    assert intel.mixed_snapshot_analysis is True
    changed = {c.component_id: c for c in intel.changed_components}
    assert changed["program:ZZZ"].previous_component_ids == ["program:AAA"]


def test_pure_copybook_rename(tmp_path: Path):
    repo = tmp_path / "rncp"
    (repo / "copybook").mkdir(parents=True)
    (repo / "copybook" / "OLD.cpy").write_text("      * old layout\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "mv", "copybook/OLD.cpy", "copybook/NEW.cpy")
    _git(repo, "commit", "-qm", "rename copybook")
    intel = _analyze_rename(repo)
    mapped = intel.mapped_changes[0]
    assert mapped.file.status == "renamed"
    assert mapped.previous_component_ids == ["copybook:OLD"]
    assert mapped.current_component_ids == ["copybook:NEW"]


# ------------------------------------------------------------------
# M8 — catalog isolation
# ------------------------------------------------------------------

def _foreign_tree(tmp_path: Path, with_catalog: bool) -> Path:
    tree = tmp_path / "foreign"
    (tree / "cobol").mkdir(parents=True)
    (tree / "cobol" / "EXT.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. EXT.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'ext'.\n"
    )
    if with_catalog:
        (tree / "tests").mkdir(parents=True)
        (tree / "tests" / "test_catalog.yaml").write_text(
            "tests:\n"
            "  - id: TC-EXT-001\n"
            "    name: External tree test\n"
            "    type: batch\n"
            "    covers: [program:EXT]\n"
            "    description: Foreign catalog test.\n"
        )
    return tree


def test_sample_tree_uses_bundled_catalog():
    analyzer = ChangeSetAnalyzer(build_view(REPO))
    assert analyzer._catalog, "bundled sample catalog should load"


def test_foreign_tree_with_own_catalog_wins(tmp_path: Path):
    tree = _foreign_tree(tmp_path, with_catalog=True)
    analyzer = ChangeSetAnalyzer(build_view(tree))
    provider = ExplicitFileListProvider([{"path": "cobol/EXT.cbl"}])
    intel = analyzer.analyze(provider.get_changes(), provider=provider)
    ids = [t.test_id for t in intel.recommended_tests]
    assert "TC-EXT-001" in ids
    assert not any(i.startswith("TC-WARR-") for i in ids)


def test_foreign_tree_without_catalog_controlled_error(tmp_path: Path):
    tree = _foreign_tree(tmp_path, with_catalog=False)
    with pytest.raises(RuntimeError, match="no test catalog found"):
        ChangeSetAnalyzer(build_view(tree))


def test_foreign_tree_no_catalog_opt_out(tmp_path: Path):
    tree = _foreign_tree(tmp_path, with_catalog=False)
    analyzer = ChangeSetAnalyzer(build_view(tree), catalog=[])
    provider = ExplicitFileListProvider([{"path": "cobol/EXT.cbl"}])
    intel = analyzer.analyze(provider.get_changes(), provider=provider)
    assert intel.recommended_tests == []
    assert [p.component_id for p in intel.per_change_analysis] == ["program:EXT"]


def test_no_sample_catalog_leakage(tmp_path: Path):
    tree = _foreign_tree(tmp_path, with_catalog=True)
    analyzer = ChangeSetAnalyzer(build_view(tree))
    provider = ExplicitFileListProvider([{"path": "cobol/EXT.cbl"}])
    intel = analyzer.analyze(provider.get_changes(), provider=provider)
    for t in intel.recommended_tests:
        assert t.test_id.startswith("TC-EXT-")


def test_git_temp_repo_head_catalog_used(tmp_path: Path):
    repo = tmp_path / "gcat"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "G.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. G.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'g'.\n"
    )
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_catalog.yaml").write_text(
        "tests:\n"
        "  - id: TC-G-001\n"
        "    name: G test\n"
        "    type: batch\n"
        "    covers: [program:G]\n"
        "    description: Head catalog test.\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "cobol" / "G.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. G.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'g2'.\n"
    )
    _git(repo, "commit", "-qam", "modify g")
    provider = GitDiffProvider(repo, "HEAD~1", "HEAD", source_prefix="")
    change_set = provider.get_changes()
    with tempfile.TemporaryDirectory(prefix="t-head-") as head_tmp:
        head_root = provider.extract_tree("HEAD", Path(head_tmp))
        analyzer = ChangeSetAnalyzer(build_view(head_root, label="head"))
        intel = analyzer.analyze(change_set, provider=provider)
    assert [t.test_id for t in intel.recommended_tests] == ["TC-G-001"]


# ------------------------------------------------------------------
# L1 — enum validation
# ------------------------------------------------------------------

def test_l1_invalid_enum_values_rejected():
    with pytest.raises(Exception):
        AggregatedTest(
            test_id="TC-X", test_name="X", test_type="batch",
            impact_level="BOGUS", rationale="r",
        )
    with pytest.raises(Exception):
        AggregatedSignal(
            id="S", severity="BOGUS", title="t", explanation="e",
        )
    with pytest.raises(Exception):
        AggregatedResource(table="table:T", access="BOGUS")
    with pytest.raises(Exception):
        PerChangeAnalysis(
            component_id="program:X", source_file="x", snapshot="BOGUS",
            impact=None,  # type: ignore[arg-type]
        )
    with pytest.raises(Exception):
        MappedChange(
            file=ChangedFile(path="x"), mapping_status="BOGUS",  # type: ignore[arg-type]
        )
    with pytest.raises(Exception):
        ChangedFile(path="x", status="BOGUS")  # type: ignore[arg-type]
    with pytest.raises(Exception):
        PerRootTest(
            change_root="program:X", impact_level="BOGUS", rationale="r"
        )


def test_l1_valid_enum_values_accepted():
    t = AggregatedTest(
        test_id="TC-X", test_name="X", test_type="batch",
        impact_level="MUST_RUN", rationale="r",
    )
    assert t.impact_level == "MUST_RUN"
    s = AggregatedSignal(
        id="S", severity="high", title="t", explanation="e",
    )
    assert s.severity == "high"
    r = AggregatedResource(table="table:T", access="write")
    assert r.access == "write"


# ------------------------------------------------------------------
# L2 — controlled CLI error for invalid --source-prefix
# ------------------------------------------------------------------

def test_l2_invalid_source_prefix_no_traceback(tmp_path: Path):
    import os
    import subprocess as sp

    repo = tmp_path / "l2"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "A.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. A.\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "cobol" / "A.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. A.\n"
        "       PROCEDURE DIVISION.\n           DISPLAY 'v2'.\n"
    )
    _git(repo, "commit", "-qam", "bump")
    proc = sp.run(
        [
            os.path.join(os.getcwd(), ".venv", "bin", "python"),
            "changeset.py",
            "--repo", str(repo),
            "--base", "HEAD~1",
            "--head", "HEAD",
            "--source-prefix", "x/../.",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert proc.stderr.strip().startswith("error:")


# ------------------------------------------------------------------
# Primary demo numbers recomputed under the new semantics
# ------------------------------------------------------------------

def test_primary_demo_numbers(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
    )
    s = intel.summary
    assert (s.changed_files, s.changed_components) == (2, 2)
    assert s.cross_impacted_changed_components == 1
    # Downstream impact excludes the two changed roots.
    assert s.unique_impacted_components == 4
    assert s.direct_impact_union == 3
    assert s.transitive_impact_union == 3
    assert s.overlap_impacted_components == 3
    assert s.unique_recommended_tests == 7
    assert (s.must_run_tests, s.should_run_tests) == (6, 1)
    assert (s.involved_db2_reads, s.involved_db2_writes) == (1, 2)
    assert s.risk_signals == 7
    assert s.checklist_items == 7
    assert s.relevant_incidents == 11
