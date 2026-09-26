"""Phase 2B tests: Historical Incident Intelligence.

Business behavior, not implementation trivia. Every test proves an
observable property of the incident dataset, the deterministic relevance
engine, the AI grounding boundary, or the API contract.

Phase 1 and Phase 2A tests must continue passing alongside these.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.intelligence.ai.ai_models import (
    ExplanationSource,
    IntelligenceContext,
    IntelligenceExplanation,
)
from backend.intelligence.ai.guard import HallucinationError, validate_explanation
from backend.intelligence.ai.providers import DeterministicProvider, FakeProvider
from backend.intelligence.ai.service import explain_change
from backend.intelligence.impact_context import _shared, build_impact_context
from backend.intelligence.incidents.models import (
    HistoricalIncident,
    IncidentIntelligence,
    RelevanceReasonType,
    REASON_PRECEDENCE,
)
from backend.intelligence.incidents.relevance import build_incident_intelligence
from backend.intelligence.incidents.repository import (
    IncidentDatasetError,
    YamlFileIncidentRepository,
    load_incidents,
)
from backend.intelligence.incidents.service import (
    get_incident,
    get_incidents,
    incident_intelligence_for,
)
from backend.intelligence.release_checklist import build_checklist
from backend.intelligence.risk_signals import detect_risk_signals
from backend.intelligence.test_catalog import load_catalog
from backend.intelligence.test_selector import recommend_tests

client = TestClient(app)

WARRCOPY = "copybook:WARRCOPY"
UNUSED = "copybook:UNUSED"
WARR001 = "program:WARR001"
WARRANTY = "table:WARRANTY"
UNKNOWN_COMPONENT = "copybook:DOES_NOT_EXIST"


@pytest.fixture(scope="module")
def valid_ids():
    graph, _ = _shared()
    return {c["id"] for c in graph.components()}


@pytest.fixture(scope="module")
def incidents(valid_ids):
    return load_incidents(valid_component_ids=valid_ids)


# ------------------------------------------------------------------
# Dataset loading and validation
# ------------------------------------------------------------------

def test_dataset_loads_expected_incident_count(incidents):
    assert 15 <= len(incidents) <= 20


def test_incident_ids_are_unique(incidents):
    ids = [i.id for i in incidents]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("INC-") for i in ids)


def test_incident_model_fields(incidents):
    by_id = {i.id: i for i in incidents}
    inc = by_id["INC-1042"]
    assert isinstance(inc, HistoricalIncident)
    assert inc.title == "Duplicate WARRANTY row created"
    assert str(inc.occurred_at) == "2026-02-11"
    assert inc.severity == "high"
    assert inc.status == "resolved"
    assert inc.summary
    assert "SQLCODE -803" in inc.symptoms
    assert set(inc.linked_components) == {"program:WARR001", "table:WARRANTY"}
    assert inc.failure_mode == "duplicate_database_record"
    assert inc.root_cause_category == "application_logic"
    assert inc.root_cause_summary
    assert inc.resolution_summary


def test_valid_linked_components_accepted(valid_ids, tmp_path):
    path = tmp_path / "incidents.yaml"
    path.write_text(
        "incidents:\n"
        "  - id: INC-9001\n"
        "    title: Synthetic valid incident\n"
        "    occurred_at: 2026-01-01\n"
        "    severity: low\n"
        "    status: resolved\n"
        "    summary: fine\n"
        "    linked_components: [program:WARR001, program:WARR001]\n"
    )
    loaded = load_incidents(path=path, valid_component_ids=valid_ids)
    # duplicate linked components are normalized/deduplicated
    assert loaded[0].linked_components == ["program:WARR001"]


def test_unknown_linked_component_rejected(valid_ids, tmp_path):
    path = tmp_path / "incidents.yaml"
    path.write_text(
        "incidents:\n"
        "  - id: INC-9002\n"
        "    title: Bad link incident\n"
        "    occurred_at: 2026-01-01\n"
        "    severity: low\n"
        "    status: resolved\n"
        "    summary: bad\n"
        "    linked_components: [program:FAKE999]\n"
    )
    with pytest.raises(IncidentDatasetError) as exc_info:
        load_incidents(path=path, valid_component_ids=valid_ids)
    assert "program:FAKE999" in str(exc_info.value)
    assert "INC-9002" in str(exc_info.value)


def test_duplicate_incident_id_rejected(valid_ids, tmp_path):
    path = tmp_path / "incidents.yaml"
    path.write_text(
        "incidents:\n"
        "  - id: INC-9003\n"
        "    title: First\n"
        "    occurred_at: 2026-01-01\n"
        "    severity: low\n"
        "    status: resolved\n"
        "    summary: one\n"
        "    linked_components: [program:WARR001]\n"
        "  - id: INC-9003\n"
        "    title: Second\n"
        "    occurred_at: 2026-01-02\n"
        "    severity: low\n"
        "    status: resolved\n"
        "    summary: two\n"
        "    linked_components: [program:WARR002]\n"
    )
    with pytest.raises(IncidentDatasetError) as exc_info:
        load_incidents(path=path, valid_component_ids=valid_ids)
    assert "INC-9003" in str(exc_info.value)


def test_invalid_severity_rejected(valid_ids, tmp_path):
    path = tmp_path / "incidents.yaml"
    path.write_text(
        "incidents:\n"
        "  - id: INC-9004\n"
        "    title: Bad severity\n"
        "    occurred_at: 2026-01-01\n"
        "    severity: catastrophic\n"
        "    status: resolved\n"
        "    summary: bad\n"
        "    linked_components: [program:WARR001]\n"
    )
    with pytest.raises(IncidentDatasetError):
        load_incidents(path=path, valid_component_ids=valid_ids)


# ------------------------------------------------------------------
# Relevance engine: WARRCOPY scenario
# ------------------------------------------------------------------

def _by_id(intel: IncidentIntelligence) -> dict:
    return {r.incident.id: r for r in intel.relevant_incidents}


def test_warrcopy_expected_relevant_incidents(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    ids = _by_id(intel)
    for expected in ("INC-1042", "INC-1088", "INC-1015", "INC-1023",
                     "INC-1031", "INC-1037", "INC-1045", "INC-1050",
                     "INC-1055", "INC-1060", "INC-1095"):
        assert expected in ids, f"{expected} missing for WARRCOPY"
    assert intel.total_relevant_incidents == len(ids)  # no duplicates


def test_warrcopy_excludes_unrelated_incidents(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    ids = _by_id(intel)
    for unrelated in ("INC-1065", "INC-1070", "INC-1075", "INC-1080",
                      "INC-1085", "INC-1090"):
        assert unrelated not in ids


def test_unrelated_high_severity_incident_excluded(incidents):
    # INC-1075 is high severity but linked only to table:CUSTOMER, which
    # has no deterministic relationship to the WARRCOPY change. Severity
    # alone must never make an incident relevant.
    by_id = {i.id: i for i in incidents}
    assert by_id["INC-1075"].severity == "high"
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    assert "INC-1075" not in _by_id(intel)


def test_changed_component_match(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1015"]
    assert rel.primary_reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    assert "copybook:WARRCOPY" in rel.matched_components
    reason = rel.relevance_reasons[0]
    assert reason.reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    assert "changed component" in reason.explanation


def test_direct_impact_match(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1042"]
    reasons = {r.reason for r in rel.relevance_reasons}
    assert RelevanceReasonType.DIRECT_IMPACT_MATCH in reasons
    direct = next(r for r in rel.relevance_reasons
                  if r.reason == RelevanceReasonType.DIRECT_IMPACT_MATCH)
    assert direct.matched_component == "program:WARR001"
    assert "directly impacted" in direct.explanation
    # the deterministic Phase 1 path change -> WARR001 is attached
    assert any(p.impacted == "program:WARR001"
               for p in direct.supporting_paths)


def test_transitive_impact_match(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1088"]
    assert rel.primary_reason == RelevanceReasonType.TRANSITIVE_IMPACT_MATCH
    reason = rel.relevance_reasons[0]
    assert reason.matched_component == "job:DAILY01"
    assert "transitively impacted" in reason.explanation
    # deterministic path WARRCOPY <- WARR001 <- DAILY01 is attached
    assert any(p.impacted == "job:DAILY01"
               for p in reason.supporting_paths)


def test_involved_write_resource_match(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1060"]
    assert rel.primary_reason == RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH
    reason = rel.relevance_reasons[0]
    assert reason.matched_component == "table:WARRANTY"
    assert "involved DB2 resource" in reason.explanation
    assert "not reverse-impacted" in reason.explanation
    # the resource evidence and the impacted programs' paths are attached
    assert reason.evidence
    assert rel.supporting_resources


def test_involved_read_and_write_reasons_both_preserved():
    # Precedence decides the primary reason and ordering only: a table
    # that impacted programs both READ and WRITE yields BOTH relevance
    # reasons. The valid READ reason must not be discarded.
    incident = HistoricalIncident(
        id="INC-READ-1", title="read/write incident",
        occurred_at="2026-01-01", severity="low", status="resolved",
        summary="s", linked_components=["table:WARRANTY"],
    )
    intel = build_incident_intelligence(
        build_impact_context("program:WARR001"), [incident])
    rel = _by_id(intel)["INC-READ-1"]
    reasons = [r.reason for r in rel.relevance_reasons]
    # WARR001 both reads and writes WARRANTY -> both reasons preserved,
    # WRITE primary by documented precedence.
    assert reasons == [
        RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH,
        RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH,
    ]
    assert rel.primary_reason == \
        RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH
    # precedence list itself is the documented order
    assert [r.value for r in REASON_PRECEDENCE] == [
        "CHANGED_COMPONENT_MATCH",
        "DIRECT_IMPACT_MATCH",
        "TRANSITIVE_IMPACT_MATCH",
        "INVOLVED_WRITE_RESOURCE_MATCH",
        "INVOLVED_READ_RESOURCE_MATCH",
    ]


def test_write_only_resource_gets_write_reason_only(incidents):
    # CLAIM_HISTORY is written (by WARR002) but never read in the
    # WARRCOPY context: an incident linked to it gets the write reason
    # and no read reason.
    incident = HistoricalIncident(
        id="INC-WRITE-ONLY", title="write-only incident",
        occurred_at="2026-01-02", severity="low", status="resolved",
        summary="s", linked_components=["table:CLAIM_HISTORY"],
    )
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), [incident])
    rel = _by_id(intel)["INC-WRITE-ONLY"]
    assert [r.reason for r in rel.relevance_reasons] == [
        RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH]


def test_read_only_resource_gets_read_reason_only():
    # In the CUST002 context table:VEHICLE is read (by CUST002) but not
    # written by any in-scope program: read reason only, no write reason.
    ctx = build_impact_context("program:CUST002")
    assert "table:VEHICLE" in ctx.read_tables
    assert "table:VEHICLE" not in ctx.write_tables
    incident = HistoricalIncident(
        id="INC-READ-ONLY", title="read-only incident",
        occurred_at="2026-01-03", severity="low", status="resolved",
        summary="s", linked_components=["table:VEHICLE"],
    )
    intel = build_incident_intelligence(ctx, [incident])
    rel = _by_id(intel)["INC-READ-ONLY"]
    assert [r.reason for r in rel.relevance_reasons] == [
        RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH]


def test_read_and_write_evidence_remain_distinct():
    # The two reasons for a read+written table carry different
    # deterministic evidence: the read statement vs the write statement.
    incident = HistoricalIncident(
        id="INC-RW-EV", title="read/write evidence incident",
        occurred_at="2026-01-04", severity="low", status="resolved",
        summary="s", linked_components=["table:WARRANTY"],
    )
    intel = build_incident_intelligence(
        build_impact_context("program:WARR001"), [incident])
    rel = _by_id(intel)["INC-RW-EV"]
    by_reason = {r.reason: r for r in rel.relevance_reasons}
    write_ev = by_reason[RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH]
    read_ev = by_reason[RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH]
    write_texts = {e.text for e in write_ev.evidence}
    read_texts = {e.text for e in read_ev.evidence}
    assert "INSERT INTO WARRANTY" in write_texts
    assert "FROM WARRANTY" in read_texts
    assert write_texts != read_texts


def test_multiple_relevance_reasons_preserved(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1042"]
    reasons = [r.reason for r in rel.relevance_reasons]
    # linked to program:WARR001 (direct) AND table:WARRANTY (involved,
    # both written and read) -> all three valid reasons preserved
    assert reasons == [
        RelevanceReasonType.DIRECT_IMPACT_MATCH,
        RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH,
        RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH,
    ]
    assert rel.primary_reason == RelevanceReasonType.DIRECT_IMPACT_MATCH
    assert set(rel.matched_components) == {"program:WARR001", "table:WARRANTY"}


def test_summary_distinguishes_primary_tiers_from_all_reasons(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    # primary-tier counts sum to the incident total: no double-counting
    assert sum(intel.primary_tier_counts.values()) == \
        intel.total_relevant_incidents
    # all-reason counts may exceed the total: one incident can carry
    # several valid reasons (e.g. INC-1042 has DIRECT + WRITE + READ)
    assert sum(intel.reason_counts.values()) >= intel.total_relevant_incidents
    assert (intel.reason_counts["INVOLVED_READ_RESOURCE_MATCH"] >
            intel.primary_tier_counts["INVOLVED_READ_RESOURCE_MATCH"])
    # every primary tier key also appears in the reason counts
    assert set(intel.primary_tier_counts) == set(intel.reason_counts)


def test_no_duplicate_incident_in_result(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    ids = [r.incident.id for r in intel.relevant_incidents]
    assert len(ids) == len(set(ids))
    assert intel.total_relevant_incidents == len(ids)
    # primary-tier counts must sum to the total
    assert sum(intel.primary_tier_counts.values()) == \
        intel.total_relevant_incidents


def test_deterministic_ordering(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    items = intel.relevant_incidents
    rank = {r: i for i, r in enumerate(REASON_PRECEDENCE)}
    keys = [(rank[r.primary_reason],
             -r.incident.occurred_at.toordinal(),
             r.incident.id) for r in items]
    assert keys == sorted(keys)
    # strongest tier first
    assert items[0].primary_reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    # the single involved-write incident sorts after all transitive ones
    assert items[-1].incident.id == "INC-1060"


def test_relevance_is_deterministic_across_runs(incidents):
    ctx = build_impact_context(WARRCOPY)
    first = build_incident_intelligence(ctx, incidents).model_dump()
    second = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents).model_dump()
    assert first == second


# ------------------------------------------------------------------
# Other scenarios
# ------------------------------------------------------------------

def test_unused_returns_zero_relevant_incidents(incidents):
    intel = build_incident_intelligence(
        build_impact_context(UNUSED), incidents)
    assert intel.total_relevant_incidents == 0
    assert intel.relevant_incidents == []
    assert all(v == 0 for v in intel.primary_tier_counts.values())
    assert all(v == 0 for v in intel.reason_counts.values())


def test_warr001_changed_component_matching(incidents):
    # The changed program participates in matching without being in its
    # own reverse-impact set.
    intel = build_incident_intelligence(
        build_impact_context(WARR001), incidents)
    rel = _by_id(intel)["INC-1042"]
    assert rel.primary_reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    assert "program:WARR001" in rel.matched_components
    # WARR001 must not appear as its own impacted component
    ctx = build_impact_context(WARR001)
    assert WARR001 not in ctx.direct_impacts
    assert WARR001 not in ctx.transitive_impacts


def test_warranty_table_matching(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRANTY), incidents)
    by_id = _by_id(intel)
    # incident explicitly linked to the changed table
    rel = by_id["INC-1060"]
    assert rel.primary_reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    assert "table:WARRANTY" in rel.matched_components
    # incident linked to the changed table AND an impacted program keeps
    # both reasons, primary = changed
    rel2 = by_id["INC-1042"]
    assert rel2.primary_reason == RelevanceReasonType.CHANGED_COMPONENT_MATCH
    assert RelevanceReasonType.DIRECT_IMPACT_MATCH in \
        {r.reason for r in rel2.relevance_reasons}
    # READS_TABLE / WRITES_TABLE semantics survive in involved resources
    ctx = build_impact_context(WARRANTY)
    assert "table:WARRANTY" in ctx.read_tables
    assert "table:WARRANTY" in ctx.write_tables


def test_evidence_attached_to_relevance_reasons(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    rel = _by_id(intel)["INC-1042"]
    direct = next(r for r in rel.relevance_reasons
                  if r.reason == RelevanceReasonType.DIRECT_IMPACT_MATCH)
    assert direct.evidence
    ev = direct.evidence[0]
    assert ev.file == "cobol/WARR001.cbl"
    assert ev.line == 15
    assert ev.text == "COPY WARRCOPY."
    write_reason = next(r for r in rel.relevance_reasons
                        if r.reason == RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH)
    assert any(e.file == "cobol/WARR001.cbl" and e.line == 31
               for e in write_reason.evidence)


# ------------------------------------------------------------------
# Phase 2A decision logic unchanged by incidents
# ------------------------------------------------------------------

def test_phase2a_test_recommendations_unchanged(incidents):
    ctx = build_impact_context(WARRCOPY)
    catalog = load_catalog()
    before = [t.model_dump() for t in recommend_tests(ctx, catalog)]
    # incident intelligence must not alter test selection
    intel = build_incident_intelligence(ctx, incidents)
    after = [t.model_dump() for t in recommend_tests(ctx, catalog)]
    assert before == after
    assert len(after) == 7  # Phase 2A baseline: 6 MUST_RUN + 1 SHOULD_RUN
    assert sum(1 for t in after if t["impact_level"] == "MUST_RUN") == 6


def test_phase2a_risk_signals_unchanged(incidents):
    ctx = build_impact_context(WARRCOPY)
    before = [s.model_dump() for s in detect_risk_signals(ctx)]
    build_incident_intelligence(ctx, incidents)
    after = [s.model_dump() for s in detect_risk_signals(ctx)]
    assert before == after
    assert {s["id"] for s in after} == {
        "SHARED_COPYBOOK_CHANGE", "MULTIPLE_PROGRAMS_IMPACTED",
        "MULTIPLE_BATCH_JOBS_IMPACTED", "DB2_WRITE_INVOLVED",
        "TRANSITIVE_IMPACT", "HIGH_FAN_OUT", "MULTIPLE_EXECUTION_PATHS",
    }


def test_llm_presence_cannot_change_incident_selection(incidents):
    ctx = build_impact_context(WARRCOPY)
    intel = _context_with_incidents(incidents)
    recs = recommend_tests(ctx, load_catalog())
    signals = detect_risk_signals(ctx)
    checklist = build_checklist(ctx, signals)
    det = explain_change(ctx, recs, signals, checklist,
                         provider=DeterministicProvider(),
                         incident_intelligence=intel)
    fake = explain_change(ctx, recs, signals, checklist,
                          provider=FakeProvider(),
                          incident_intelligence=intel)
    assert det.incident_summary != ""  # incidents were supplied
    assert "INC-1042" in det.incident_summary
    assert "INC-1042" in fake.incident_summary
    # the deterministic result is identical regardless of provider
    assert build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents).model_dump() == intel.model_dump()


# ------------------------------------------------------------------
# AI grounding: incident identifiers
# ------------------------------------------------------------------

def _context_with_incidents(incidents):
    intel = build_incident_intelligence(
        build_impact_context(WARRCOPY), incidents)
    return intel


def test_ai_valid_incident_ids_accepted(incidents):
    ctx = build_impact_context(WARRCOPY)
    intel = _context_with_incidents(incidents)
    signals = detect_risk_signals(ctx)
    explanation = explain_change(
        ctx, recommend_tests(ctx, load_catalog()), signals,
        build_checklist(ctx, signals),
        provider=FakeProvider(),
        incident_intelligence=intel,
    )
    assert explanation.explanation_source == ExplanationSource.AI
    assert "INC-1042" in explanation.incident_summary


def test_ai_hallucinated_incident_id_rejected(incidents):
    intel = _context_with_incidents(incidents)
    context = IntelligenceContext(
        changed_component=WARRCOPY,
        impacted_components=["program:WARR001"],
        relevant_incidents=[
            {"id": r.incident.id} for r in intel.relevant_incidents
        ],
    )
    explanation = IntelligenceExplanation(
        subject_component=WARRCOPY,
        explanation_source=ExplanationSource.AI,
        executive_summary="Change to copybook:WARRCOPY.",
        technical_summary="Impacts program:WARR001.",
        testing_summary="None.",
        release_considerations="None.",
        incident_summary="Also relevant: INC-9999 which was never supplied.",
        historical_patterns="None.",
        release_history_considerations="None.",
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(explanation, context)
    assert "INC-9999" in exc_info.value.offending


def test_ai_cannot_alter_deterministic_incident_result(incidents):
    from backend.intelligence.ai.providers import IntelligenceProvider

    class _MeddlingProvider(IntelligenceProvider):
        @property
        def name(self) -> str:
            return "meddling"

        def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
            # Tries to invent an incident id and drop real ones.
            return IntelligenceExplanation(
                subject_component=WARRCOPY,
                explanation_source=ExplanationSource.AI,
                executive_summary="x",
                technical_summary="x",
                testing_summary="x",
                release_considerations="x",
                incident_summary="Only INC-9999 matters.",
                historical_patterns="x",
                release_history_considerations="x",
            )

    ctx = build_impact_context(WARRCOPY)
    intel = _context_with_incidents(incidents)
    before = intel.model_dump()
    recs = recommend_tests(ctx, load_catalog())
    signals = detect_risk_signals(ctx)
    explanation = explain_change(
        ctx, recs, signals, build_checklist(ctx, signals),
        provider=_MeddlingProvider(),
        incident_intelligence=intel,
    )
    # guard rejected the invented id -> deterministic fallback
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert "INC-9999" not in explanation.incident_summary
    # the deterministic incident result is untouched
    assert intel.model_dump() == before
    assert intel.total_relevant_incidents == 11


def test_provider_failure_falls_back_deterministically(incidents):
    from backend.intelligence.ai.providers import IntelligenceProvider

    class _ExplodingProvider(IntelligenceProvider):
        @property
        def name(self) -> str:
            return "exploding"

        def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
            raise RuntimeError("boom")

    ctx = build_impact_context(WARRCOPY)
    intel = _context_with_incidents(incidents)
    recs = recommend_tests(ctx, load_catalog())
    signals = detect_risk_signals(ctx)
    explanation = explain_change(
        ctx, recs, signals, build_checklist(ctx, signals),
        provider=_ExplodingProvider(),
        incident_intelligence=intel,
    )
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert "INC-1042" in explanation.incident_summary


# ------------------------------------------------------------------
# API
# ------------------------------------------------------------------

def test_api_list_incidents():
    r = client.get("/api/incidents")
    assert r.status_code == 200
    body = r.json()
    assert 15 <= len(body) <= 20
    ids = [i["id"] for i in body]
    assert len(ids) == len(set(ids))
    assert "INC-1042" in ids


def test_api_get_incident():
    r = client.get("/api/incidents/INC-1042")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "INC-1042"
    assert "program:WARR001" in body["linked_components"]


def test_api_unknown_incident_404():
    r = client.get("/api/incidents/INC-9999")
    assert r.status_code == 404


def test_api_incident_intelligence_warrcopy():
    r = client.get(f"/api/incident-intelligence/{WARRCOPY}")
    assert r.status_code == 200
    body = r.json()
    assert body["changed_component"] == WARRCOPY
    assert body["total_relevant_incidents"] == 11
    first = body["relevant_incidents"][0]
    assert first["incident"]["id"] == "INC-1015"
    assert first["primary_reason"] == "CHANGED_COMPONENT_MATCH"
    assert len(first["relevance_reasons"]) >= 1
    # primary-tier summary counts sum to the total (no double counting)
    assert sum(body["primary_tier_counts"].values()) == 11
    # all-reason counts may exceed the total (multiple valid reasons)
    assert sum(body["reason_counts"].values()) >= 11
    by_id = {x["incident"]["id"]: x for x in body["relevant_incidents"]}
    reasons_1060 = [r["reason"] for r in
                    by_id["INC-1060"]["relevance_reasons"]]
    assert reasons_1060 == ["INVOLVED_WRITE_RESOURCE_MATCH",
                            "INVOLVED_READ_RESOURCE_MATCH"]


def test_api_incident_intelligence_unused():
    r = client.get(f"/api/incident-intelligence/{UNUSED}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_relevant_incidents"] == 0
    assert body["relevant_incidents"] == []


def test_api_incident_intelligence_warr001():
    r = client.get(f"/api/incident-intelligence/{WARR001}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_relevant_incidents"] == 9
    assert body["relevant_incidents"][0]["primary_reason"] == \
        "CHANGED_COMPONENT_MATCH"


def test_api_incident_intelligence_warranty():
    r = client.get(f"/api/incident-intelligence/{WARRANTY}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_relevant_incidents"] == 11
    by_id = {x["incident"]["id"]: x for x in body["relevant_incidents"]}
    assert by_id["INC-1060"]["primary_reason"] == "CHANGED_COMPONENT_MATCH"


def test_api_incident_intelligence_unknown_component_404():
    r = client.get(f"/api/incident-intelligence/{UNKNOWN_COMPONENT}")
    assert r.status_code == 404


def test_api_intelligence_bundle_includes_incidents():
    r = client.get(f"/api/intelligence/{WARRCOPY}")
    assert r.status_code == 200
    body = r.json()
    assert "incident_intelligence" in body
    assert body["incident_intelligence"]["total_relevant_incidents"] == 11
    # Phase 2A sections are unchanged by the incident layer
    assert body["impact"]["changed_component"] == WARRCOPY
    assert len(body["recommended_tests"]) == 7
    assert len(body["risk_signals"]) == 7
    # AI explanation now carries the incident sections, still deterministic
    assert body["ai_explanation"]["explanation_source"] == "deterministic"
    assert "INC-1042" in body["ai_explanation"]["incident_summary"]


def test_api_invalid_dataset_fails_clearly(valid_ids, tmp_path, monkeypatch):
    path = tmp_path / "incidents.yaml"
    path.write_text(
        "incidents:\n"
        "  - id: INC-BAD\n"
        "    title: bad\n"
        "    occurred_at: 2026-01-01\n"
        "    severity: low\n"
        "    status: resolved\n"
        "    summary: bad\n"
        "    linked_components: [program:FAKE999]\n"
    )
    import backend.intelligence.incidents.repository as repo
    import backend.api.intelligence as router_module

    def _bad():
        return repo.YamlFileIncidentRepository(
            path=path, valid_component_ids=valid_ids
        ).list_incidents()

    # Patch the names as bound in the router module (it uses from-imports).
    monkeypatch.setattr(router_module, "get_incidents", _bad)
    monkeypatch.setattr(
        router_module, "incident_intelligence_for",
        lambda component_id: (_ for _ in ()).throw(
            repo.IncidentDatasetError("unreachable")),
    )
    r = client.get("/api/incidents")
    assert r.status_code == 500
    assert "FAKE999" in r.json()["detail"]
