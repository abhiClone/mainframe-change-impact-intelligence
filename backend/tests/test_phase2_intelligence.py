"""Phase 2A intelligence tests - business behavior, not implementation.

Each test proves an observable behavior of the intelligence core:
impact-context construction, deterministic test recommendation,
risk-signal detection, and release-checklist generation.
"""
from __future__ import annotations

import pytest

from backend.intelligence.impact_context import build_impact_context
from backend.intelligence.release_checklist import build_checklist
from backend.intelligence.risk_signals import detect_risk_signals
from backend.intelligence.test_catalog import load_catalog
from backend.intelligence.test_selector import recommend_tests


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


# ------------------------------------------------------------------
# Impact context
# ------------------------------------------------------------------

def test_warrcopy_context_counts():
    ctx = build_impact_context("copybook:WARRCOPY")
    assert ctx.changed_component == "copybook:WARRCOPY"
    assert ctx.changed_component_type == "COPYBOOK"
    assert ctx.direct_impacts == ["program:WARR001", "program:WARR002"]
    assert ctx.transitive_impacts == [
        "job:DAILY01", "job:WARRBTCH", "proc:WARRANTY"]
    assert ctx.total_impacted_components == 5


def test_warrcopy_context_affected_groups():
    ctx = build_impact_context("copybook:WARRCOPY")
    assert ctx.affected_programs == ["program:WARR001", "program:WARR002"]
    assert ctx.affected_jobs == ["job:DAILY01", "job:WARRBTCH"]
    assert ctx.affected_procs == ["proc:WARRANTY"]
    assert ctx.affected_copybooks == []
    assert ctx.affected_tables == []


def test_table_warranty_context_read_write_tables():
    # Changing table:WARRANTY: impacted programs WARR001/WARR002 use tables
    # via existing Phase 1 edges. WARR001 reads+ writes WARRANTY; WARR002
    # writes WARRANTY and CLAIM_HISTORY. Read vs write stays distinguishable.
    ctx = build_impact_context("table:WARRANTY")
    assert ctx.read_tables == ["table:WARRANTY"]
    assert ctx.write_tables == ["table:CLAIM_HISTORY", "table:WARRANTY"]
    assert "READS_TABLE" in ctx.relationships
    assert "WRITES_TABLE" in ctx.relationships


def test_read_write_tables_distinguishable():
    # CLAIM_HISTORY is only ever written, never read. Involved resources are
    # derived from the impacted program's (WARR002) outgoing edges, so
    # WARRANTY — also written by WARR002 — is involved too.
    ctx = build_impact_context("table:CLAIM_HISTORY")
    assert ctx.read_tables == []
    assert ctx.write_tables == ["table:CLAIM_HISTORY", "table:WARRANTY"]


def test_warrcopy_involved_db2_resources():
    # Impact paths from a copybook change never touch table edges, so
    # WARRANTY must NOT be in the reverse impact set...
    ctx = build_impact_context("copybook:WARRCOPY")
    assert "table:WARRANTY" not in ctx.affected_tables
    assert "READS_TABLE" not in ctx.relationships
    assert "WRITES_TABLE" not in ctx.relationships
    # ...but it IS an involved DB2 resource: impacted programs WARR001 and
    # WARR002 use it via existing Phase 1 edges. Read/write stay distinct.
    # (WARR002 additionally writes CLAIM_HISTORY.)
    assert ctx.read_tables == ["table:WARRANTY"]
    assert ctx.write_tables == ["table:CLAIM_HISTORY", "table:WARRANTY"]
    by_access = {(r.table, r.access): r for r in ctx.involved_resources}
    assert set(by_access) == {
        ("table:WARRANTY", "read"),
        ("table:WARRANTY", "write"),
        ("table:CLAIM_HISTORY", "write"),
    }
    read_res = by_access[("table:WARRANTY", "read")]
    write_res = by_access[("table:WARRANTY", "write")]
    claim_res = by_access[("table:CLAIM_HISTORY", "write")]
    assert read_res.used_by == ["program:WARR001"]
    assert write_res.used_by == ["program:WARR001", "program:WARR002"]
    assert claim_res.used_by == ["program:WARR002"]
    for res in (read_res, write_res, claim_res):
        assert res.evidence  # real file/line/text evidence
        assert all(e.file == "cobol/WARR001.cbl" or e.file == "cobol/WARR002.cbl"
                   for e in res.evidence)


def test_warrcopy_db2_write_signal_fires():
    # Impacted programs write WARRANTY, so DB2_WRITE_INVOLVED must fire
    # even though the changed component is a copybook.
    ctx = build_impact_context("copybook:WARRCOPY")
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    sig = signals["DB2_WRITE_INVOLVED"]
    assert sig.severity == "high"
    assert "table:WARRANTY" in sig.supporting_components
    assert {"program:WARR001", "program:WARR002"} <= set(sig.supporting_components)
    assert sig.evidence


def test_warrcopy_checklist_has_db2_write_item():
    ctx = build_impact_context("copybook:WARRCOPY")
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    item = rules["db2_write_involved"]
    assert item.title == "Validate DB2 write behavior and rollback scenarios"
    assert "table:WARRANTY" in item.related_components


def test_unused_has_no_involved_resources():
    # No impacted programs -> no involved DB2 resources -> no DB2 signal,
    # no DB2 checklist items.
    ctx = build_impact_context("copybook:UNUSED")
    assert ctx.affected_programs == []
    assert ctx.involved_resources == []
    assert ctx.read_tables == []
    assert ctx.write_tables == []
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    assert "DB2_WRITE_INVOLVED" not in signals
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    assert "db2_write_involved" not in rules
    assert "db2_read_involved" not in rules


def test_program_change_uses_own_db2_edges():
    # Changing a program: its own outgoing DB2 edges count as involved
    # resources, so DB2_WRITE_INVOLVED fires for program:WARR001 too.
    ctx = build_impact_context("program:WARR001")
    assert "table:WARRANTY" in ctx.write_tables
    assert "table:WARRANTY" in ctx.read_tables
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    assert signals["DB2_WRITE_INVOLVED"].severity == "high"


def test_warrcopy_context_depth_and_relationships():
    ctx = build_impact_context("copybook:WARRCOPY")
    assert ctx.maximum_impact_depth >= 2
    assert "USES_COPYBOOK" in ctx.relationships
    assert "EXECUTES_PROGRAM" in ctx.relationships
    assert ctx.relationships == sorted(ctx.relationships)


def test_unused_context_is_empty():
    ctx = build_impact_context("copybook:UNUSED")
    assert ctx.direct_impacts == []
    assert ctx.transitive_impacts == []
    assert ctx.dependency_paths == []
    assert ctx.maximum_impact_depth == 0
    assert ctx.total_impacted_components == 0


def test_unknown_component_raises_keyerror():
    with pytest.raises(KeyError):
        build_impact_context("bogus:NOPE")


# ------------------------------------------------------------------
# Test recommendation
# ------------------------------------------------------------------

def test_selection_is_deterministic(catalog):
    ctx = build_impact_context("copybook:WARRCOPY")
    first = recommend_tests(ctx, catalog)
    second = recommend_tests(ctx, catalog)
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]


def test_must_run_for_direct_impact_coverage(catalog):
    ctx = build_impact_context("copybook:WARRCOPY")
    recs = {r.test_id: r for r in recommend_tests(ctx, catalog)}
    # Covers the changed copybook and both directly impacted programs.
    rec = recs["TC-WARR-002"]
    assert rec.impact_level == "MUST_RUN"
    assert rec.matched_components == [
        "copybook:WARRCOPY", "program:WARR001", "program:WARR002"]


def test_should_run_for_transitive_only_coverage(catalog):
    # Changing WARRCOPY impacts job:DAILY01 only transitively (via
    # WARR001); TC-CUST-001 covers DAILY01 and nothing else in the
    # impact set, so it must be SHOULD_RUN, not MUST_RUN.
    ctx = build_impact_context("copybook:WARRCOPY")
    recs = {r.test_id: r for r in recommend_tests(ctx, catalog)}
    rec = recs["TC-CUST-001"]
    assert rec.impact_level == "SHOULD_RUN"
    assert rec.matched_components == ["job:DAILY01"]
    assert set(rec.matched_components) <= set(ctx.transitive_impacts)


def test_unrelated_test_not_selected(catalog):
    ctx = build_impact_context("copybook:WARRCOPY")
    recs = {r.test_id for r in recommend_tests(ctx, catalog)}
    # Vehicle-only test has no overlap with the WARRCOPY impact set.
    assert "TC-VEH-002" not in recs


def test_unused_selects_nothing(catalog):
    ctx = build_impact_context("copybook:UNUSED")
    assert recommend_tests(ctx, catalog) == []


def test_every_recommendation_has_rationale_and_evidence(catalog):
    ctx = build_impact_context("copybook:WARRCOPY")
    recs = recommend_tests(ctx, catalog)
    assert recs  # sanity: the change must select several tests
    for rec in recs:
        assert rec.rationale.strip()
        assert rec.test_id in rec.rationale
        assert rec.evidence
        for ev in rec.evidence:
            assert ev.file and ev.text


def test_output_sorted_by_level_then_id(catalog):
    ctx = build_impact_context("copybook:WARRCOPY")
    recs = recommend_tests(ctx, catalog)
    keys = [(r.impact_level, r.test_id) for r in recs]
    assert keys == sorted(keys)


# ------------------------------------------------------------------
# Risk signals
# ------------------------------------------------------------------

def test_db2_write_signal_for_table_warranty():
    ctx = build_impact_context("table:WARRANTY")
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    sig = signals["DB2_WRITE_INVOLVED"]
    assert sig.severity == "high"
    assert sig.triggered_by == ["table:WARRANTY"]
    assert sig.evidence
    # Read and write tables stay distinguishable in the context.
    assert "table:WARRANTY" in ctx.read_tables
    assert "table:WARRANTY" in ctx.write_tables


def test_shared_copybook_signal_for_warrcopy():
    ctx = build_impact_context("copybook:WARRCOPY")
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    sig = signals["SHARED_COPYBOOK_CHANGE"]
    assert sig.severity == "medium"
    assert set(sig.supporting_components) == {
        "program:WARR001", "program:WARR002"}
    assert sig.evidence
    assert all(e.text.upper().startswith("COPY") for e in sig.evidence)


def test_warrcopy_signal_set():
    ctx = build_impact_context("copybook:WARRCOPY")
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    assert signals["MULTIPLE_PROGRAMS_IMPACTED"].severity == "medium"
    assert signals["MULTIPLE_BATCH_JOBS_IMPACTED"].severity == "medium"
    assert signals["HIGH_FAN_OUT"].severity == "medium"
    assert signals["TRANSITIVE_IMPACT"].severity == "low"
    assert signals["MULTIPLE_EXECUTION_PATHS"].severity == "low"
    # Impacted programs write WARRANTY, so the DB2 write signal fires even
    # though the changed component is a copybook.
    assert signals["DB2_WRITE_INVOLVED"].severity == "high"
    # No tables are in the WARRCOPY reverse impact set, so this must NOT fire.
    assert "MULTIPLE_DB2_TABLES_IMPACTED" not in signals


def test_unused_has_no_risk_signals():
    ctx = build_impact_context("copybook:UNUSED")
    assert detect_risk_signals(ctx) == []


def test_signal_fields_are_grounded():
    ctx = build_impact_context("copybook:WARRCOPY")
    for sig in detect_risk_signals(ctx):
        assert sig.id and sig.severity and sig.title and sig.explanation
        assert sig.triggered_by  # real component ids
        assert sig.evidence  # real evidence


# ------------------------------------------------------------------
# Changed-program involved resources (program:WARR001)
#
# The program resource scope is affected_programs + the changed
# component itself when it is a COBOL_PROGRAM. WARR001's own
# READS_TABLE/WRITES_TABLE edges must surface as involved resources,
# while WARR001 must NOT appear in its own impacted-components set.
# ------------------------------------------------------------------

def test_changed_program_not_in_own_impacted_set():
    ctx = build_impact_context("program:WARR001")
    assert "program:WARR001" not in ctx.direct_impacts
    assert "program:WARR001" not in ctx.transitive_impacts
    assert "program:WARR001" not in ctx.affected_programs
    assert ctx.affected_programs == []


def test_changed_program_involved_read_write_resources():
    ctx = build_impact_context("program:WARR001")
    by_key = {(r.table, r.access): r for r in ctx.involved_resources}
    read = by_key[("table:WARRANTY", "read")]
    write = by_key[("table:WARRANTY", "write")]
    assert read.used_by == ["program:WARR001"]
    assert write.used_by == ["program:WARR001"]
    # read vs write stay distinguishable
    assert ctx.read_tables == ["table:WARRANTY"]
    assert ctx.write_tables == ["table:WARRANTY"]


def test_changed_program_involved_evidence_is_real():
    ctx = build_impact_context("program:WARR001")
    by_key = {(r.table, r.access): r for r in ctx.involved_resources}
    read_ev = by_key[("table:WARRANTY", "read")].evidence[0]
    assert (read_ev.file, read_ev.line, read_ev.text) == (
        "cobol/WARR001.cbl", 27, "FROM WARRANTY")
    write_ev = by_key[("table:WARRANTY", "write")].evidence[0]
    assert (write_ev.file, write_ev.line, write_ev.text) == (
        "cobol/WARR001.cbl", 31, "INSERT INTO WARRANTY")


def test_changed_program_db2_write_signal_fires():
    ctx = build_impact_context("program:WARR001")
    signals = {s.id: s for s in detect_risk_signals(ctx)}
    sig = signals["DB2_WRITE_INVOLVED"]
    assert sig.severity == "high"
    assert sig.triggered_by == ["program:WARR001"]
    assert set(sig.supporting_components) == {
        "program:WARR001", "table:WARRANTY"}
    assert any(e.text == "INSERT INTO WARRANTY" for e in sig.evidence)


def test_changed_program_db2_checklist_rules_fire():
    ctx = build_impact_context("program:WARR001")
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    assert set(rules) == {"jobs_impacted", "procs_affected",
                          "transitive_impact", "db2_write_involved",
                          "db2_read_involved"}
    assert (rules["db2_write_involved"].title ==
            "Validate DB2 write behavior and rollback scenarios")
    assert (rules["db2_read_involved"].title ==
            "Validate DB2 read behavior against impacted tables")
    assert "table:WARRANTY" in \
        rules["db2_write_involved"].related_components


# ------------------------------------------------------------------
# Release checklist
# ------------------------------------------------------------------

def _rules(items):
    return {i.rule: i for i in items}


def test_checklist_rules_fire_for_warrcopy():
    ctx = build_impact_context("copybook:WARRCOPY")
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    assert rules["jobs_impacted"].title == "Validate impacted batch jobs"
    assert (rules["shared_copybook_change"].title
            == "Compile and regression-test all dependent programs")
    assert rules["procs_affected"].title == "Validate PROC execution chain"
    assert (rules["transitive_impact"].title
            == "Trace transitive impact chains before sign-off")
    for item in rules.values():
        assert item.rule and item.related_components


def test_checklist_db2_rules_fire_for_table_warranty():
    ctx = build_impact_context("table:WARRANTY")
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    assert (rules["db2_write_involved"].title
            == "Validate DB2 write behavior and rollback scenarios")
    related = rules["db2_write_involved"].related_components
    assert "table:WARRANTY" in related
    assert "program:WARR001" in related  # involved writer, not just the table
    assert rules["db2_read_involved"].title == \
        "Validate DB2 read behavior against impacted tables"


def test_checklist_empty_for_unused():
    ctx = build_impact_context("copybook:UNUSED")
    assert build_checklist(ctx, detect_risk_signals(ctx)) == []


def test_checklist_skips_rules_that_do_not_apply():
    # program:WARR002's own outgoing edges write WARRANTY and CLAIM_HISTORY
    # (no reads), so the db2 write rule fires from involved resources; it is
    # not a copybook, so the shared-copybook rule must NOT fire.
    ctx = build_impact_context("program:WARR002")
    rules = _rules(build_checklist(ctx, detect_risk_signals(ctx)))
    assert set(rules) == {"jobs_impacted", "procs_affected",
                          "transitive_impact", "db2_write_involved"}
    assert "shared_copybook_change" not in rules
    assert "db2_read_involved" not in rules
