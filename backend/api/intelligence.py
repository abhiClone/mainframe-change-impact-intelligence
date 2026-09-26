"""Phase 2A API router: Change Impact Intelligence & Test Recommendation.

Deterministic endpoints built on top of the frozen Phase 1 dependency
graph; they compose the backend.intelligence services (no duplicated
dependency logic):

  GET /api/intelligence/{component_id}       -> full intelligence bundle
  GET /api/test-recommendations/{component_id} -> list[RecommendedTest]
  GET /api/risk-signals/{component_id}        -> list[RiskSignal]
  GET /api/test-catalog                       -> list[TestCase]

The AI explanation layer is optional and grounded: explain_change() falls
back to the deterministic explanation when no provider is configured or
the hallucination guard rejects output.

Component ids contain ':' (e.g. "copybook:WARRCOPY"); pass them
URL-encoded or raw - ':' is legal in a path segment.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.intelligence.ai.service import explain_change
from backend.intelligence.impact_context import build_impact_context
from backend.intelligence.models import (
    ImpactContext,
    RecommendedTest,
    RiskSignal,
    TestCase,
)
from backend.intelligence.ai.ai_models import IntelligenceExplanation
from backend.intelligence.release_checklist import build_checklist
from backend.intelligence.risk_signals import detect_risk_signals
from backend.intelligence.test_catalog import load_catalog
from backend.intelligence.test_selector import recommend_tests

router = APIRouter()


def _require(component_id: str) -> None:
    """404 on unknown component, same contract as Phase 1's _require."""
    try:
        build_impact_context(component_id)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"unknown component: {component_id}")


@router.get("/api/intelligence/{component_id}",
            response_model=dict,
            summary="Full Phase 2A intelligence bundle for a component")
def get_intelligence(component_id: str) -> dict:
    _require(component_id)
    ctx = build_impact_context(component_id)
    catalog = load_catalog()
    recommendations = recommend_tests(ctx, catalog)
    signals = detect_risk_signals(ctx)
    checklist = build_checklist(ctx, signals)
    explanation = explain_change(ctx, recommendations, signals, checklist)
    return {
        "changed_component": component_id,
        "impact": ctx.model_dump(),
        "recommended_tests": [t.model_dump() for t in recommendations],
        "risk_signals": [s.model_dump() for s in signals],
        "release_checklist": [c.model_dump() for c in checklist],
        "ai_explanation": explanation.model_dump(),
    }


@router.get("/api/test-recommendations/{component_id}",
            response_model=list[RecommendedTest],
            summary="Deterministic test recommendations for a component")
def get_test_recommendations(component_id: str) -> list[RecommendedTest]:
    _require(component_id)
    ctx = build_impact_context(component_id)
    return recommend_tests(ctx, load_catalog())


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
    return load_catalog()
