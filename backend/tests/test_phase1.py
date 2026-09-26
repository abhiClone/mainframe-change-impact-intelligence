"""Phase 1 acceptance tests.

These tests scan the REAL synthetic repository (sample_mainframe/) and
assert the exact relationships the master prompt requires:

  Test 1: COPY WARRCOPY in WARR001  -> WARR001 USES_COPYBOOK WARRCOPY
  Test 2: CALL 'CUST002' in WARR001  -> WARR001 CALLS CUST002
  Test 3: SELECT ... FROM WARRANTY   -> WARR001 READS_TABLE WARRANTY
  Test 4: UPDATE WARRANTY in WARR002 -> WARR002 WRITES_TABLE WARRANTY
  Test 5: EXEC PGM=WARR001 in DAILY01 -> DAILY01 EXECUTES_PROGRAM WARR001
  Test 6: EXEC PROC=WARRANTY in DAILY01 -> DAILY01 USES_PROC WARRANTY
  Test 7: changing WARRCOPY impacts WARR001 + DAILY01 with correct path
  Test 8: unrelated components are NOT impacted

Plus the mandatory negative test (UNUSED.cpy -> zero impact) and an
evidence-completeness test (every dependency carries file/line/text).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.graph.dependency_graph import DependencyGraph
from backend.graph.impact_analyzer import ImpactAnalyzer
from backend.parsers.repository_scanner import scan_repository

REPO = Path(__file__).resolve().parents[2] / "sample_mainframe"


@pytest.fixture(scope="module")
def scan():
    return scan_repository(REPO)


@pytest.fixture(scope="module")
def graph(scan):
    components, dependencies = scan
    return DependencyGraph.from_scan(components, dependencies)


@pytest.fixture(scope="module")
def analyzer(graph):
    return ImpactAnalyzer(graph)


def _find(deps, source, target, relationship):
    return [d for d in deps
            if d.source == source and d.target == target
            and d.relationship == relationship]


# ---- Acceptance tests 1-6: extraction --------------------------------

def test_1_copy_extraction(scan):
    _, deps = scan
    found = _find(deps, "program:WARR001", "copybook:WARRCOPY", "USES_COPYBOOK")
    assert len(found) == 1, "WARR001 USES_COPYBOOK WARRCOPY not discovered"
    ev = found[0].evidence
    assert ev.file == "cobol/WARR001.cbl"
    assert ev.line > 0
    assert "COPY WARRCOPY" in ev.text.upper()


def test_2_call_extraction(scan):
    _, deps = scan
    found = _find(deps, "program:WARR001", "program:CUST002", "CALLS")
    assert len(found) == 1, "WARR001 CALLS CUST002 not discovered"
    ev = found[0].evidence
    assert ev.file == "cobol/WARR001.cbl"
    assert ev.line > 0
    assert "CALL" in ev.text.upper() and "CUST002" in ev.text.upper()


def test_3_select_read_extraction(scan):
    _, deps = scan
    found = _find(deps, "program:WARR001", "table:WARRANTY", "READS_TABLE")
    assert len(found) == 1, "WARR001 READS_TABLE WARRANTY not discovered"
    ev = found[0].evidence
    assert "WARRANTY" in ev.text.upper()


def test_4_update_write_extraction(scan):
    _, deps = scan
    found = _find(deps, "program:WARR002", "table:WARRANTY", "WRITES_TABLE")
    assert len(found) == 1, "WARR002 WRITES_TABLE WARRANTY not discovered"
    ev = found[0].evidence
    assert "UPDATE" in ev.text.upper() and "WARRANTY" in ev.text.upper()


def test_5_jcl_pgm_extraction(scan):
    _, deps = scan
    found = _find(deps, "job:DAILY01", "program:WARR001", "EXECUTES_PROGRAM")
    assert len(found) == 1, "DAILY01 EXECUTES_PROGRAM WARR001 not discovered"
    ev = found[0].evidence
    assert ev.file == "jcl/DAILY01.jcl"
    assert ev.line > 0
    assert "PGM=WARR001" in ev.text.upper()


def test_6_jcl_proc_extraction(scan):
    _, deps = scan
    found = _find(deps, "job:DAILY01", "proc:WARRANTY", "USES_PROC")
    assert len(found) == 1, "DAILY01 USES_PROC WARRANTY not discovered"
    ev = found[0].evidence
    assert ev.file == "jcl/DAILY01.jcl"
    assert "PROC=WARRANTY" in ev.text.upper()


# ---- Acceptance test 7: impact path correctness -----------------------

def test_7_impact_paths(analyzer):
    result = analyzer.analyze("copybook:WARRCOPY")
    impacted = set(result["direct_impact"]) | set(result["transitive_impact"])
    assert "program:WARR001" in result["direct_impact"]
    assert "job:DAILY01" in impacted

    # The path explaining DAILY01 must run through WARR001.
    chains = [
        [s["from"] for s in p["path"]] + [p["impacted"]]
        for p in result["dependency_paths"]
        if p["impacted"] == "job:DAILY01"
    ]
    assert any(
        c == ["copybook:WARRCOPY", "program:WARR001", "job:DAILY01"]
        for c in chains
    ), f"no correct WARRCOPY <- WARR001 <- DAILY01 path, got {chains}"

    # Every path step must carry evidence with file/line/text.
    for p in result["dependency_paths"]:
        for step in p["path"]:
            ev = step["evidence"]
            assert ev["file"] and ev["line"] > 0 and ev["text"]
            assert step["relationship"]


# ---- Acceptance test 8: unrelated components excluded -----------------

def test_8_unrelated_not_impacted(analyzer):
    result = analyzer.analyze("copybook:WARRCOPY")
    impacted = set(result["direct_impact"]) | set(result["transitive_impact"])
    for unrelated in ("program:VEH001", "program:CUST002", "job:NIGHT01",
                      "proc:CUSTOMER", "table:VEHICLE", "copybook:UNUSED"):
        assert unrelated not in impacted, \
            f"{unrelated} falsely reported as impacted by WARRCOPY change"


# ---- Negative test: UNUSED.cpy ----------------------------------------

def test_unused_copybook_zero_impact(analyzer):
    result = analyzer.analyze("copybook:UNUSED")
    assert result["direct_impact"] == []
    assert result["transitive_impact"] == []
    assert result["dependency_paths"] == []


# ---- Impact direction semantics ---------------------------------------

def test_impact_flows_to_dependents_not_dependencies(analyzer):
    # WARR001 CALLs CUST002, i.e. WARR001 depends on CUST002.
    # Changing the callee (CUST002) must impact the caller (WARR001),
    # but changing the caller must NOT impact the callee.
    callee_changed = analyzer.analyze("program:CUST002")
    impacted = (set(callee_changed["direct_impact"])
                | set(callee_changed["transitive_impact"]))
    assert "program:WARR001" in impacted
    assert "program:CUST001" in impacted

    caller_changed = analyzer.analyze("program:WARR001")
    impacted = (set(caller_changed["direct_impact"])
                | set(caller_changed["transitive_impact"]))
    assert "program:CUST002" not in impacted


# ---- Evidence completeness --------------------------------------------

def test_every_dependency_has_evidence(scan):
    _, deps = scan
    assert len(deps) > 0
    for d in deps:
        ev = d.evidence
        assert ev.file, f"missing evidence file for {d}"
        assert isinstance(ev.line, int) and ev.line > 0, \
            f"missing evidence line for {d}"
        assert ev.text.strip(), f"missing evidence text for {d}"


# ---- Repository shape --------------------------------------------------

def test_repository_counts(scan):
    components, deps = scan
    by_type: dict[str, int] = {}
    for c in components:
        by_type[c.type] = by_type.get(c.type, 0) + 1
    assert by_type.get("COBOL_PROGRAM") == 5
    assert by_type.get("COPYBOOK") == 4      # 3 used + UNUSED.cpy
    assert by_type.get("JCL_JOB") == 3
    assert by_type.get("JCL_PROC") == 2
    assert by_type.get("DB2_TABLE") == 4
    assert len(deps) == 30


def test_unknown_component_raises(analyzer):
    with pytest.raises(KeyError):
        analyzer.analyze("program:DOESNOTEXIST")
