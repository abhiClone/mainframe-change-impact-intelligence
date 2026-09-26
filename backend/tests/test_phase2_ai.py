"""Phase 2A AI explanation layer tests.

Covers: provider selection/fallback, the deterministic and fake providers,
the hallucination guard, and the service-level fallback that keeps core
functionality independent of any API key.
"""

import pytest

from backend.intelligence.ai.ai_models import (
    ExplanationSource,
    IntelligenceContext,
    IntelligenceExplanation,
)
from backend.intelligence.ai.guard import HallucinationError, validate_explanation
from backend.intelligence.ai.providers import (
    DeterministicProvider,
    FakeProvider,
    IntelligenceProvider,
    get_provider,
)
from backend.intelligence.ai.service import explain_change
from backend.intelligence.models import (
    ChecklistItem,
    DependencyPath,
    EvidenceRef,
    ImpactContext,
    InvolvedResource,
    PathEdge,
    RecommendedTest,
    RiskSignal,
)

FALLBACK_PREFIX = "AI explanation unavailable. Deterministic analysis remains available. "


def _evidence() -> EvidenceRef:
    return EvidenceRef(file="cobol/WARR001.cbl", line=3, text="COPY WARRCOPY.")


def _edge() -> PathEdge:
    return PathEdge(
        source="copybook:WARRCOPY",
        target="program:WARR001",
        relationship="USES_COPYBOOK",
        evidence=_evidence(),
    )


def make_impact_context() -> ImpactContext:
    return ImpactContext(
        changed_component="copybook:WARRCOPY",
        changed_component_type="copybook",
        direct_impacts=["program:WARR001", "program:WARR002"],
        transitive_impacts=["program:CUST002", "table:WARRANTY"],
        dependency_paths=[
            DependencyPath(impacted="program:WARR001", path=[_edge()]),
            DependencyPath(
                impacted="table:WARRANTY",
                path=[
                    _edge(),
                    PathEdge(
                        source="program:WARR001",
                        target="table:WARRANTY",
                        relationship="READS_TABLE",
                        evidence=EvidenceRef(
                            file="cobol/WARR001.cbl", line=40, text="SELECT * FROM WARRANTY"
                        ),
                    ),
                ],
            ),
        ],
        relationships=["USES_COPYBOOK", "READS_TABLE"],
        evidence=[_edge()],
        affected_programs=["program:WARR001", "program:WARR002", "program:CUST002"],
        affected_copybooks=[],
        affected_jobs=[],
        affected_procs=[],
        affected_tables=["table:WARRANTY"],
        read_tables=["table:WARRANTY"],
        write_tables=["table:WARRANTY"],
        involved_resources=[
            InvolvedResource(
                table="table:WARRANTY",
                access="read",
                used_by=["program:WARR001"],
                evidence=[_evidence()],
            ),
            InvolvedResource(
                table="table:WARRANTY",
                access="write",
                used_by=["program:WARR001"],
                evidence=[_evidence()],
            ),
        ],
        maximum_impact_depth=2,
        total_impacted_components=4,
    )


def make_recommendations() -> list[RecommendedTest]:
    return [
        RecommendedTest(
            test_id="TC-WARR-001",
            test_name="Warranty batch regression",
            test_type="batch",
            matched_components=["program:WARR001", "program:WARR002"],
            impact_level="direct",
            dependency_paths=[],
            rationale="Covers the programs that copy WARRCOPY.",
            evidence=[_evidence()],
        )
    ]


def make_signals() -> list[RiskSignal]:
    return [
        RiskSignal(
            id="RSK-001",
            severity="high",
            title="Shared copybook change",
            explanation="WARRCOPY is shared by two programs.",
            triggered_by=["copybook:WARRCOPY"],
            supporting_components=["program:WARR001", "program:WARR002"],
            evidence=[],
        )
    ]


def make_checklist() -> list[ChecklistItem]:
    return [
        ChecklistItem(
            id="CHK-001",
            title="Recompile affected programs",
            detail="Recompile WARR001 and WARR002 against the new copybook.",
            rule="ALWAYS",
            related_components=["program:WARR001", "program:WARR002"],
        )
    ]


def make_intelligence_context() -> IntelligenceContext:
    impact = make_impact_context()
    return IntelligenceContext(
        changed_component=impact.changed_component,
        impacted_components=[*impact.direct_impacts, *impact.transitive_impacts],
        dependency_paths=[p.model_dump() for p in impact.dependency_paths],
        evidence=[e.model_dump() for e in impact.evidence],
        recommended_tests=[t.model_dump() for t in make_recommendations()],
        risk_signals=[s.model_dump() for s in make_signals()],
        release_checklist=[c.model_dump() for c in make_checklist()],
    )


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTELLIGENCE_PROVIDER", raising=False)
    monkeypatch.delenv("INTELLIGENCE_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("INTELLIGENCE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("INTELLIGENCE_LLM_MODEL", raising=False)


# --- provider selection -----------------------------------------------------


def test_default_provider_is_deterministic(monkeypatch):
    _clear_provider_env(monkeypatch)
    assert get_provider().name == "deterministic"


def test_unknown_provider_value_falls_back_to_deterministic(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "definitely-not-a-provider")
    assert get_provider().name == "deterministic"


def test_fake_provider_selected_by_env(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "fake")
    assert get_provider().name == "fake"


# --- service with default provider ------------------------------------------


def test_service_default_provider_returns_valid_explanation(monkeypatch):
    _clear_provider_env(monkeypatch)
    explanation = explain_change(
        make_impact_context(), make_recommendations(), make_signals(), make_checklist()
    )
    assert isinstance(explanation, IntelligenceExplanation)
    assert "copybook:WARRCOPY" in explanation.executive_summary
    assert not explanation.executive_summary.startswith(FALLBACK_PREFIX)
    # guard passes on the service output too
    validate_explanation(explanation, make_intelligence_context())


def test_fake_provider_returns_valid_response(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "fake")
    provider = get_provider()
    assert isinstance(provider, FakeProvider)
    context = make_intelligence_context()
    explanation = provider.explain(context)
    assert isinstance(explanation, IntelligenceExplanation)
    assert explanation.executive_summary  # non-empty
    validate_explanation(explanation, context)


# --- hallucination guard ------------------------------------------------------


def test_hallucinated_component_rejected():
    context = make_intelligence_context()
    explanation = IntelligenceExplanation(
        subject_component="copybook:WARRCOPY",
        explanation_source=ExplanationSource.AI,
        executive_summary="Change to copybook:WARRCOPY also affects program:FAKE999.",
        technical_summary="All good otherwise.",
        testing_summary="Run TC-WARR-001.",
        release_considerations="None.",
        incident_summary="None.",
        historical_patterns="None.",
        release_history_considerations="None.",
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(explanation, context)
    assert "program:FAKE999" in exc_info.value.offending


def test_hallucinated_test_id_rejected():
    context = make_intelligence_context()
    explanation = IntelligenceExplanation(
        subject_component="copybook:WARRCOPY",
        explanation_source=ExplanationSource.AI,
        executive_summary="Change to copybook:WARRCOPY.",
        technical_summary="Impacts program:WARR001.",
        testing_summary="Run TC-FAKE-999 for extra safety.",
        release_considerations="None.",
        incident_summary="None.",
        historical_patterns="None.",
        release_history_considerations="None.",
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(explanation, context)
    assert "TC-FAKE-999" in exc_info.value.offending


def test_real_ids_from_context_pass_validation():
    context = make_intelligence_context()
    explanation = IntelligenceExplanation(
        subject_component="copybook:WARRCOPY",
        explanation_source=ExplanationSource.AI,
        executive_summary=(
            "Change to copybook:WARRCOPY impacts program:WARR001, program:WARR002, "
            "program:CUST002 and table:WARRANTY."
        ),
        technical_summary="copybook:WARRCOPY is used by program:WARR001.",
        testing_summary="Run TC-WARR-001 against the impacted programs.",
        release_considerations="See RSK-001 and CHK-001.",
        incident_summary="None.",
        historical_patterns="None.",
        release_history_considerations="None.",
    )
    assert validate_explanation(explanation, context) is explanation


def test_deterministic_provider_output_contains_only_known_ids():
    context = make_intelligence_context()
    explanation = DeterministicProvider().explain(context)
    assert isinstance(explanation, IntelligenceExplanation)
    assert validate_explanation(explanation, context) is explanation


# --- service-level fallback ----------------------------------------------------


class _HallucinatingProvider(IntelligenceProvider):
    @property
    def name(self) -> str:
        return "hallucinating"

    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
        return IntelligenceExplanation(
            subject_component="copybook:WARRCOPY",
            explanation_source=ExplanationSource.AI,
            executive_summary="Change affects program:FAKE999 and job:FAKEJOB.",
            technical_summary="Bogus.",
            testing_summary="Bogus.",
            release_considerations="Bogus.",
            incident_summary="None.",
            historical_patterns="None.",
            release_history_considerations="None.",
        )


class _ExplodingProvider(IntelligenceProvider):
    @property
    def name(self) -> str:
        return "exploding"

    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
        raise RuntimeError("simulated provider failure")


def test_service_sanitizes_hallucinating_provider():
    explanation = explain_change(
        make_impact_context(),
        make_recommendations(),
        make_signals(),
        make_checklist(),
        provider=_HallucinatingProvider(),
    )
    assert isinstance(explanation, IntelligenceExplanation)
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)
    assert "FAKE999" not in explanation.executive_summary
    validate_explanation(explanation, make_intelligence_context())


def test_service_falls_back_on_provider_exception():
    explanation = explain_change(
        make_impact_context(),
        make_recommendations(),
        make_signals(),
        make_checklist(),
        provider=_ExplodingProvider(),
    )
    assert isinstance(explanation, IntelligenceExplanation)
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_service_falls_back_when_http_provider_misconfigured(monkeypatch):
    # INTELLIGENCE_PROVIDER=http with no endpoint/key/model configured:
    # core functionality must not depend on an API key.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "http")
    explanation = explain_change(
        make_impact_context(), make_recommendations(), make_signals(), make_checklist()
    )
    assert isinstance(explanation, IntelligenceExplanation)
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)


# --- explanation source labeling --------------------------------------------


def test_service_default_provider_labels_source_deterministic(monkeypatch):
    # No LLM configured: the explanation must be labeled deterministic,
    # never presented as AI-generated.
    _clear_provider_env(monkeypatch)
    explanation = explain_change(
        make_impact_context(), make_recommendations(), make_signals(), make_checklist()
    )
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert not explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_fake_provider_labels_source_ai(monkeypatch):
    # FakeProvider stands in for a real LLM on the AI code path.
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "fake")
    explanation = explain_change(
        make_impact_context(), make_recommendations(), make_signals(), make_checklist()
    )
    assert explanation.explanation_source == ExplanationSource.AI
    assert not explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_fallback_labels_source_deterministic():
    # Guard rejection -> deterministic fallback with the AI-unavailable note.
    explanation = explain_change(
        make_impact_context(),
        make_recommendations(),
        make_signals(),
        make_checklist(),
        provider=_HallucinatingProvider(),
    )
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_provider_exception_labels_source_deterministic():
    explanation = explain_change(
        make_impact_context(),
        make_recommendations(),
        make_signals(),
        make_checklist(),
        provider=_ExplodingProvider(),
    )
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_subject_component_mismatch_rejected():
    # The explanation must be about the component it was asked about.
    context = make_intelligence_context()
    explanation = IntelligenceExplanation(
        subject_component="copybook:WRONG",
        explanation_source=ExplanationSource.AI,
        executive_summary="Change to copybook:WARRCOPY.",
        technical_summary="Impacts program:WARR001.",
        testing_summary="Run TC-WARR-001.",
        release_considerations="None.",
        incident_summary="None.",
        historical_patterns="None.",
        release_history_considerations="None.",
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(explanation, context)
    assert "subject_component" in str(exc_info.value)


def test_service_rejects_wrong_subject_and_falls_back():
    class _WrongSubjectProvider(IntelligenceProvider):
        @property
        def name(self) -> str:
            return "wrong-subject"

        def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
            return IntelligenceExplanation(
                subject_component="copybook:SOMETHING_ELSE",
                explanation_source=ExplanationSource.AI,
                executive_summary="Change to copybook:WARRCOPY.",
                technical_summary="Fine.",
                testing_summary="Fine.",
                release_considerations="Fine.",
                incident_summary="None.",
                historical_patterns="None.",
                release_history_considerations="None.",
            )

    explanation = explain_change(
        make_impact_context(),
        make_recommendations(),
        make_signals(),
        make_checklist(),
        provider=_WrongSubjectProvider(),
    )
    assert explanation.explanation_source == ExplanationSource.DETERMINISTIC
    assert explanation.executive_summary.startswith(FALLBACK_PREFIX)


def test_ai_response_cannot_modify_deterministic_fields():
    # The AI layer has no write path into deterministic artifacts: even a
    # lying provider leaves the input models byte-identical.
    impact_ctx = make_impact_context()
    recs = make_recommendations()
    signals = make_signals()
    checklist = make_checklist()
    before = (
        impact_ctx.model_dump(),
        [r.model_dump() for r in recs],
        [s.model_dump() for s in signals],
        [c.model_dump() for c in checklist],
    )
    explain_change(impact_ctx, recs, signals, checklist,
                   provider=_HallucinatingProvider())
    after = (
        impact_ctx.model_dump(),
        [r.model_dump() for r in recs],
        [s.model_dump() for s in signals],
        [c.model_dump() for c in checklist],
    )
    assert before == after
