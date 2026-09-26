"""Phase 3A tests: multi-root aggregation, provenance, AI guard, API.

All aggregation reuses the frozen Phase 1/2A/2B engines; these tests
assert the Phase 3A rules: deduplication with full root provenance,
strongest-priority-wins, READ/WRITE independence, and that the AI layer
cannot modify the deterministic result.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.changeset import (
    ChangeSetAnalyzer,
    ExplicitFileListProvider,
    build_view,
)
from backend.changeset.ai import (
    DeterministicChangeSetExplainer,
    FakeChangeSetExplainer,
    build_change_set_context,
    change_set_id_for,
    explain_change_set,
    validate_change_set_explanation,
    ChangeSetExplanation,
)
from backend.changeset.service import ChangeSetAnalyzer as Analyzer
from backend.intelligence.ai.guard import HallucinationError
from backend.intelligence.models import EvidenceRef, RecommendedTest

REPO = Path(__file__).resolve().parents[2] / "sample_mainframe"

WARRCOPY = "copybook:WARRCOPY"
WARR002 = "program:WARR002"
UNUSED = "copybook:UNUSED"


@pytest.fixture(scope="module")
def analyzer() -> ChangeSetAnalyzer:
    return ChangeSetAnalyzer(build_view(REPO))


def _analyze(analyzer, files, resolutions=None, explainer=None):
    provider = ExplicitFileListProvider(files)
    return analyzer.analyze(
        provider.get_changes(),
        resolutions=resolutions or {},
        provider=provider,
        explainer=explainer,
    )


@pytest.fixture(scope="module")
def demo(analyzer) -> object:
    return _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
    )


# ------------------------------------------------------------------
# Primary demo: WARRCOPY + WARR002
# ------------------------------------------------------------------

def test_both_files_map_correctly(demo):
    assert [m.file.path for m in demo.mapped_changes] == [
        "copybook/WARRCOPY.cpy",
        "cobol/WARR002.cbl",
    ]
    assert demo.ambiguous_changes == []
    assert demo.unmapped_changes == []


def test_both_change_roots_remain_visible(demo):
    roots = [p.component_id for p in demo.per_change_analysis]
    assert roots == [WARRCOPY, WARR002]


def test_per_change_impact_is_independent(demo):
    by_root = {p.component_id: p for p in demo.per_change_analysis}
    # Each root's impact matches the frozen single-component analysis.
    assert set(by_root[WARRCOPY].impact.direct_impacts) == {
        "program:WARR001", "program:WARR002"
    }
    assert by_root[WARRCOPY].impact.transitive_impacts
    assert by_root[WARR002].impact.direct_impacts


def test_impact_deduplicated_with_provenance(demo):
    entries = {e.component_id: e for e in demo.unique_impacted_components}
    # Changed roots are excluded from downstream impact by definition.
    assert "copybook:WARRCOPY" not in entries
    assert "program:WARR002" not in entries
    # job:WARRBTCH is impacted by both roots: appears once...
    warrbtch = entries["job:WARRBTCH"]
    assert warrbtch.impacted_by == [WARRCOPY, WARR002]
    assert warrbtch.impacted_by_count == 2
    # ...with per-root evidence preserved, each carrying its snapshot.
    assert {p.change_root for p in warrbtch.per_root} == {WARRCOPY, WARR002}
    assert {p.snapshot for p in warrbtch.per_root} == {"head"}


def test_changed_vs_impacted_separation(demo):
    # M2: changed components are reported separately from downstream
    # impact; a changed root impacted by another changed root is kept as
    # cross-impact, never silently dropped.
    changed = {c.component_id: c for c in demo.changed_components}
    assert set(changed) == {WARRCOPY, WARR002}
    assert changed[WARRCOPY].originating_files == ["copybook/WARRCOPY.cpy"]
    assert changed[WARR002].originating_files == ["cobol/WARR002.cbl"]
    cross = changed[WARR002].also_impacted_by
    assert [(r.change_root, r.snapshot) for r in cross] == [
        (WARRCOPY, "head")
    ]
    assert changed[WARRCOPY].also_impacted_by == []
    assert demo.summary.changed_components == 2
    assert demo.summary.cross_impacted_changed_components == 1


def test_overlap_detection(demo):
    assert "job:WARRBTCH" in demo.impacted_by_multiple_changes
    assert "job:DAILY01" in demo.impacted_by_multiple_changes
    overlap = set(demo.impacted_by_multiple_changes)
    single = set(demo.impacted_by_one_change)
    assert overlap.isdisjoint(single)
    assert overlap | single == {
        e.component_id for e in demo.unique_impacted_components
    }


def test_tests_deduplicated_strongest_priority_wins(demo):
    ids = [t.test_id for t in demo.recommended_tests]
    assert len(ids) == len(set(ids))  # no duplicates
    by_id = {t.test_id: t for t in demo.recommended_tests}
    warr1 = by_id["TC-WARR-001"]
    assert [(r.change_root, r.snapshot) for r in warr1.recommended_because_of] == [
        (WARRCOPY, "head"),
        (WARR002, "head"),
    ]
    # All per-root reasons survive.
    assert {p.change_root for p in warr1.per_root} == {WARRCOPY, WARR002}
    for p in warr1.per_root:
        assert p.rationale
        assert p.snapshot == "head"


def test_must_run_beats_should_run():
    """Aggregation rule in isolation: MUST_RUN wins, reasons retained."""
    def rec(root, level):
        return RecommendedTest(
            test_id="TC-X",
            test_name="X",
            test_type="batch",
            matched_components=[root],
            impact_level=level,
            dependency_paths=[],
            rationale=f"because {root}",
            evidence=[],
        )

    from backend.changeset.models import PerChangeAnalysis
    from backend.intelligence.incidents.models import IncidentIntelligence
    from backend.intelligence.models import ImpactContext

    def per_change(root, level):
        ctx = ImpactContext(
            changed_component=root, changed_component_type="COPYBOOK",
            direct_impacts=[], transitive_impacts=[], dependency_paths=[],
            relationships=[], evidence=[], affected_programs=[],
            affected_copybooks=[], affected_jobs=[], affected_procs=[],
            affected_tables=[], read_tables=[], write_tables=[],
            involved_resources=[], maximum_impact_depth=0,
            total_impacted_components=0,
        )
        pc = PerChangeAnalysis(
            component_id=root, source_file="x", impact=ctx,
            recommended_tests=[rec(root, level)],
        )
        intel = IncidentIntelligence(
            changed_component=root, relevant_incidents=[],
            total_relevant_incidents=0, primary_tier_counts={}, reason_counts={},
        )
        return (pc, intel)

    aggregated = Analyzer._aggregate_tests([
        per_change("copybook:A", "SHOULD_RUN"),
        per_change("copybook:B", "MUST_RUN"),
    ])
    assert len(aggregated) == 1
    assert aggregated[0].impact_level == "MUST_RUN"
    assert [r.change_root for r in aggregated[0].recommended_because_of] == [
        "copybook:A",
        "copybook:B",
    ]
    assert {p.change_root: p.impact_level for p in aggregated[0].per_root} == {
        "copybook:A": "SHOULD_RUN",
        "copybook:B": "MUST_RUN",
    }


def test_resources_deduplicated_read_write_independent(demo):
    keys = [(r.table, r.access) for r in demo.involved_resources]
    assert len(keys) == len(set(keys))
    # READ and WRITE of the same table are independent entries.
    assert ("table:WARRANTY", "read") in keys
    assert ("table:WARRANTY", "write") in keys
    write_warranty = next(
        r for r in demo.involved_resources
        if (r.table, r.access) == ("table:WARRANTY", "write")
    )
    assert [
        (r.change_root, r.snapshot)
        for r in write_warranty.associated_change_roots
    ] == [(WARRCOPY, "head"), (WARR002, "head")]
    assert write_warranty.used_by


def test_signals_deduplicated(demo):
    ids = [s.id for s in demo.risk_signals]
    assert len(ids) == len(set(ids))
    db2 = next(s for s in demo.risk_signals if s.id == "DB2_WRITE_INVOLVED")
    assert [(r.change_root, r.snapshot) for r in db2.change_roots] == [
        (WARRCOPY, "head"),
        (WARR002, "head"),
    ]
    assert db2.triggered_by and db2.supporting_components


def test_checklist_deduplicated(demo):
    ids = [c.id for c in demo.release_checklist]
    assert len(ids) == len(set(ids))
    assert len(demo.release_checklist) == demo.summary.checklist_items
    chk = next(c for c in demo.release_checklist if c.id == "CHK-DB2-WRITE")
    assert [(r.change_root, r.snapshot) for r in chk.applicable_change_roots] == [
        (WARRCOPY, "head"),
        (WARR002, "head"),
    ]


def test_incidents_deduplicated_per_change_reasons_survive(demo):
    ids = [a.incident.id for a in demo.relevant_incidents]
    assert len(ids) == len(set(ids))
    inc = next(a for a in demo.relevant_incidents if a.incident.id == "INC-1015")
    assert [(r.change_root, r.snapshot) for r in inc.relevant_to_changes] == [
        (WARRCOPY, "head"),
        (WARR002, "head"),
    ]
    assert {p.change_root for p in inc.per_change} == {WARRCOPY, WARR002}
    for p in inc.per_change:
        assert p.relevance_reasons  # every per-change reason inspectable
        assert p.snapshot == "head"


def test_summary_metrics_consistent(demo):
    s = demo.summary
    assert s.changed_files == 2
    assert s.changed_components == 2
    assert s.cross_impacted_changed_components == 1
    assert s.ambiguous_files == 0 and s.unmapped_files == 0
    assert s.unique_impacted_components == len(demo.unique_impacted_components)
    assert s.overlap_impacted_components == len(demo.impacted_by_multiple_changes)
    assert s.unique_recommended_tests == len(demo.recommended_tests)
    assert s.must_run_tests + s.should_run_tests == s.unique_recommended_tests
    assert s.relevant_incidents == len(demo.relevant_incidents)
    assert demo.deterministic_summary  # always present
    # M2: changed roots are not counted as downstream impact.
    assert s.unique_impacted_components == 4
    assert {e.component_id for e in demo.unique_impacted_components} == {
        "program:WARR001", "job:WARRBTCH", "job:DAILY01", "proc:WARRANTY",
    }


# ------------------------------------------------------------------
# Negative control: UNUSED stays quiet
# ------------------------------------------------------------------

def test_unused_negative_control(analyzer):
    intel = _analyze(analyzer, [{"path": "copybook/UNUSED.cpy"}])
    assert [p.component_id for p in intel.per_change_analysis] == [UNUSED]
    assert intel.unique_impacted_components == []
    assert intel.recommended_tests == []
    assert intel.risk_signals == []
    assert intel.release_checklist == []
    assert intel.relevant_incidents == []
    assert intel.involved_resources == []


# ------------------------------------------------------------------
# Mixed Mainframe + non-Mainframe
# ------------------------------------------------------------------

def test_mixed_mapped_unmapped(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "README.md"}],
    )
    assert [m.file.path for m in intel.mapped_changes] == ["copybook/WARRCOPY.cpy"]
    assert [m.file.path for m in intel.unmapped_changes] == ["README.md"]
    # README.md must not change the Mainframe impact result.
    alone = _analyze(analyzer, [{"path": "copybook/WARRCOPY.cpy"}])
    assert (
        [e.component_id for e in intel.unique_impacted_components]
        == [e.component_id for e in alone.unique_impacted_components]
    )
    assert [t.test_id for t in intel.recommended_tests] == [
        t.test_id for t in alone.recommended_tests
    ]


# ------------------------------------------------------------------
# Ambiguous file through the service
# ------------------------------------------------------------------

def test_ambiguous_file_needs_resolution(analyzer):
    intel = _analyze(analyzer, [{"path": "sql/schema.sql"}])
    assert len(intel.ambiguous_changes) == 1
    assert intel.per_change_analysis == []  # nothing guessed
    assert intel.unique_impacted_components == []


def test_ambiguous_file_resolved(analyzer):
    intel = _analyze(
        analyzer,
        [{"path": "sql/schema.sql"}],
        resolutions={"sql/schema.sql": ["table:WARRANTY"]},
    )
    assert intel.ambiguous_changes == []
    assert [p.component_id for p in intel.per_change_analysis] == ["table:WARRANTY"]


# ------------------------------------------------------------------
# AI layer: grounded, guarded, non-mutating
# ------------------------------------------------------------------

def test_ai_cannot_change_deterministic_result(analyzer, demo):
    before = demo.model_dump(mode="json")
    explainer = FakeChangeSetExplainer()
    intel = _analyze(
        analyzer,
        [{"path": "copybook/WARRCOPY.cpy"}, {"path": "cobol/WARR002.cbl"}],
        explainer=explainer,
    )
    after = intel.model_dump(mode="json")
    # The deterministic sections are identical with/without the AI path.
    for key in (
        "mapped_changes", "per_change_analysis", "unique_impacted_components",
        "recommended_tests", "risk_signals", "release_checklist",
        "relevant_incidents", "summary", "deterministic_summary",
    ):
        assert after[key] == before[key], key
    assert intel.ai_explanation["explanation_source"] == "ai"


def test_guard_rejects_hallucinated_component_id(demo):
    ctx = build_change_set_context(demo)
    bad = DeterministicChangeSetExplainer().explain(ctx)
    bad.impact_summary += " Also check program:PHANTOM for regressions."
    with pytest.raises(HallucinationError, match="program:PHANTOM"):
        validate_change_set_explanation(bad, ctx)


def test_guard_rejects_hallucinated_test_signal_incident_ids(demo):
    ctx = build_change_set_context(demo)
    bad = DeterministicChangeSetExplainer().explain(ctx)
    bad.testing_summary += " Run TC-9999 and watch FAKE_SIGNAL_NOW."
    bad.incident_summary += " See also INC-9999."
    with pytest.raises(HallucinationError) as exc:
        validate_change_set_explanation(bad, ctx)
    offending = str(exc.value)
    assert "TC-9999" in offending
    assert "FAKE_SIGNAL_NOW" in offending
    assert "INC-9999" in offending


def test_guard_rejects_wrong_subject(demo):
    ctx = build_change_set_context(demo)
    bad = DeterministicChangeSetExplainer().explain(ctx)
    bad.subject = "change-set:copybook:WARRCOPY"
    with pytest.raises(HallucinationError, match="subject"):
        validate_change_set_explanation(bad, ctx)


def test_guard_rejects_unknown_change_root(demo):
    ctx = build_change_set_context(demo)
    bad = DeterministicChangeSetExplainer().explain(ctx)
    bad.scope_summary = bad.scope_summary.replace(
        "copybook:WARRCOPY", "copybook:WARRCOPY2"
    )
    with pytest.raises(HallucinationError, match="copybook:WARRCOPY2"):
        validate_change_set_explanation(bad, ctx)


def test_explain_change_set_falls_back_on_guard_failure(demo):
    class EvilExplainer(FakeChangeSetExplainer):
        @property
        def name(self):
            return "evil"

        def explain(self, context):
            expl = super().explain(context)
            expl.impact_summary += " program:INVENTED did it."
            return expl

    explanation = explain_change_set(demo, provider=EvilExplainer())
    assert explanation.explanation_source.value == "deterministic"
    assert explanation.scope_summary.startswith(
        "AI explanation unavailable. Deterministic analysis remains available."
    )


def test_change_set_id_deterministic():
    assert change_set_id_for(["program:B", "copybook:A"]) == (
        change_set_id_for(["copybook:A", "program:B"])
    )
    assert change_set_id_for([]) == "change-set:(empty)"


def test_deterministic_explainer_mentions_only_known_ids(demo):
    ctx = build_change_set_context(demo)
    expl = DeterministicChangeSetExplainer().explain(ctx)
    # Must pass its own guard.
    validate_change_set_explanation(expl, ctx)
    assert expl.explanation_source.value == "deterministic"


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

from backend.api.app import app

client = TestClient(app)


def test_api_change_set_analyze_ok():
    r = client.post(
        "/api/change-set/analyze",
        json={"files": [
            {"path": "copybook/WARRCOPY.cpy"},
            {"path": "cobol/WARR002.cbl", "status": "modified"},
        ]},
    )
    assert r.status_code == 200
    body = r.json()
    assert [p["component_id"] for p in body["per_change_analysis"]] == [
        WARRCOPY, WARR002
    ]
    assert body["summary"]["unique_impacted_components"] == len(
        body["unique_impacted_components"]
    )
    assert body["ai_explanation"]["explanation_source"] == "deterministic"


def test_api_ambiguous_file():
    r = client.post(
        "/api/change-set/analyze", json={"files": [{"path": "sql/schema.sql"}]}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["ambiguous_changes"]) == 1
    assert body["per_change_analysis"] == []


def test_api_invalid_resolution_is_400():
    r = client.post(
        "/api/change-set/analyze",
        json={
            "files": [{"path": "sql/schema.sql"}],
            "resolutions": {"sql/schema.sql": ["table:NOPE"]},
        },
    )
    assert r.status_code == 400


def test_api_invalid_status_is_422():
    r = client.post(
        "/api/change-set/analyze",
        json={"files": [{"path": "x.cbl", "status": "bogus"}]},
    )
    assert r.status_code == 422


def test_api_existing_endpoints_unaffected():
    assert client.get("/api/summary").status_code == 200
    assert client.get("/api/intelligence/copybook:WARRCOPY").status_code == 200
    assert client.get("/api/incidents").status_code == 200
