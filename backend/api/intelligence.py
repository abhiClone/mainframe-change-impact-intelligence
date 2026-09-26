"""Phase 2A API router: Change Impact Intelligence & Test Recommendation.

Deterministic endpoints built on top of the frozen Phase 1 dependency
graph; they compose the backend.intelligence services (no duplicated
dependency logic):

  GET /api/intelligence/{component_id}       -> full intelligence bundle
  GET /api/test-recommendations/{component_id} -> list[RecommendedTest]
  GET /api/risk-signals/{component_id}        -> list[RiskSignal]
  GET /api/test-catalog                       -> list[TestCase]

Phase 2B adds Historical Incident Intelligence (additive layer; the
Phase 2A deterministic sections are unchanged):

  GET /api/incidents                          -> list[HistoricalIncident]
  GET /api/incidents/{incident_id}            -> one incident (404 if unknown)
  GET /api/incident-intelligence/{component_id} -> IncidentIntelligence

The AI explanation layer is optional and grounded: explain_change() falls
back to the deterministic explanation when no provider is configured or
the hallucination guard rejects output.

Component ids contain ':' (e.g. "copybook:WARRCOPY"); pass them
URL-encoded or raw - ':' is legal in a path segment.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.intelligence.ai.service import explain_change
from backend.intelligence.impact_context import _shared, build_impact_context
from backend.intelligence.incidents.models import (
    HistoricalIncident,
    IncidentIntelligence,
)
from backend.intelligence.incidents.repository import IncidentDatasetError
from backend.intelligence.incidents.service import (
    get_incident,
    get_incidents,
    incident_intelligence_for,
)
from backend.intelligence.models import (
    ImpactContext,
    RecommendedTest,
    RiskSignal,
    TestCase,
)
from backend.intelligence.ai.ai_models import IntelligenceExplanation
from backend.intelligence.release_checklist import build_checklist
from backend.intelligence.risk_signals import detect_risk_signals
from backend.intelligence.test_catalog import TestCatalogError, load_catalog
from backend.intelligence.test_selector import recommend_tests

router = APIRouter()


def _require(component_id: str) -> None:
    """404 on unknown component, same contract as Phase 1's _require."""
    try:
        build_impact_context(component_id)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"unknown component: {component_id}")


def _catalog() -> list[TestCase]:
    """Load the test catalog validated against the frozen Phase 1 graph.

    ``covers[]`` entries must be real component ids and ``execution.job``
    must name a real JCL job — the same validation standard as the
    historical incident dataset. Invalid catalog data fails clearly
    (HTTP 500 with the curated message), never silently.
    """
    graph, _ = _shared()
    components = {c["id"]: c for c in graph.components()}
    valid_ids = set(components)
    valid_jobs = {
        cid for cid, comp in components.items()
        if comp["type"] == "JCL_JOB"
    }
    try:
        return load_catalog(
            valid_component_ids=valid_ids, valid_job_ids=valid_jobs
        )
    except TestCatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _incident_intelligence_or_500(component_id: str) -> IncidentIntelligence:
    try:
        return incident_intelligence_for(component_id)
    except IncidentDatasetError as exc:
        # Invalid historical data must fail clearly, never silently.
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/intelligence/{component_id}",
            response_model=dict,
            summary="Full Phase 2A+2B intelligence bundle for a component")
def get_intelligence(component_id: str) -> dict:
    _require(component_id)
    ctx = build_impact_context(component_id)
    catalog = _catalog()
    recommendations = recommend_tests(ctx, catalog)
    signals = detect_risk_signals(ctx)
    checklist = build_checklist(ctx, signals)
    incident_intelligence = _incident_intelligence_or_500(component_id)
    explanation = explain_change(
        ctx, recommendations, signals, checklist,
        incident_intelligence=incident_intelligence,
    )
    return {
        "changed_component": component_id,
        "impact": ctx.model_dump(),
        "recommended_tests": [t.model_dump() for t in recommendations],
        "risk_signals": [s.model_dump() for s in signals],
        "release_checklist": [c.model_dump() for c in checklist],
        "incident_intelligence": incident_intelligence.model_dump(),
        "ai_explanation": explanation.model_dump(),
    }


@router.get("/api/test-recommendations/{component_id}",
            response_model=list[RecommendedTest],
            summary="Deterministic test recommendations for a component")
def get_test_recommendations(component_id: str) -> list[RecommendedTest]:
    _require(component_id)
    ctx = build_impact_context(component_id)
    return recommend_tests(ctx, _catalog())


@router.get("/api/risk-signals/{component_id}",
            response_model=list[RiskSignal],
            summary="Deterministic risk signals for a component")
def get_risk_signals(component_id: str) -> list[RiskSignal]:
    _require(component_id)
    ctx = build_impact_context(component_id)
    return detect_risk_signals(ctx)


@router.get("/api/test-catalog",
            response_model=list[TestCase],
            summary="Full test catalog (12 deterministic test cases)")
def get_test_catalog() -> list[TestCase]:
    return _catalog()


# ------------------------------------------------------------------
# Phase 2B: Historical Incident Intelligence
# ------------------------------------------------------------------

@router.get("/api/incidents",
            response_model=list[HistoricalIncident],
            summary="All validated historical incidents")
def list_incidents() -> list[HistoricalIncident]:
    try:
        return get_incidents()
    except IncidentDatasetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/incidents/{incident_id}",
            response_model=HistoricalIncident,
            summary="One historical incident by id (404 if unknown)")
def get_incident_by_id(incident_id: str) -> HistoricalIncident:
    try:
        incident = get_incident(incident_id)
    except IncidentDatasetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if incident is None:
        raise HTTPException(status_code=404,
                            detail=f"unknown incident: {incident_id}")
    return incident


@router.get("/api/incident-intelligence/{component_id}",
            response_model=IncidentIntelligence,
            summary="Deterministic historical-incident intelligence for a component")
def get_incident_intelligence(component_id: str) -> IncidentIntelligence:
    _require(component_id)
    return _incident_intelligence_or_500(component_id)
