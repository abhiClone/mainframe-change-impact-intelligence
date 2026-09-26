"""Service entry point for the Phase 2A AI explanation layer.

Builds an IntelligenceContext from the sibling Phase 2A models, runs the
selected provider, and validates the result with the hallucination guard.
On any provider failure or guard rejection, falls back to the deterministic
provider so core functionality never depends on an API key.
"""

from __future__ import annotations

from typing import Optional, Sequence

from backend.intelligence.models import (  # parallel track: ImpactContext et al.
    ChecklistItem,
    ImpactContext,
    RecommendedTest,
    RiskSignal,
)

from .ai_models import (
    ExplanationSource,
    IntelligenceContext,
    IntelligenceExplanation,
)
from .guard import HallucinationError, validate_explanation
from .providers import DeterministicProvider, IntelligenceProvider, get_provider

_FALLBACK_PREFIX = "AI explanation unavailable. Deterministic analysis remains available. "


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def explain_change(
    impact_ctx: ImpactContext,
    recommendations: Sequence[RecommendedTest],
    signals: Sequence[RiskSignal],
    checklist: Sequence[ChecklistItem],
    provider: Optional[IntelligenceProvider] = None,
) -> IntelligenceExplanation:
    """Explain a change from Phase 2A intelligence artifacts.

    Builds the strict IntelligenceContext from the sibling models, asks the
    provider (default: get_provider()) for an explanation, and runs the
    hallucination guard. Any failure — provider exception or guard rejection —
    yields the deterministic explanation with a fallback prefix.

    The returned explanation's ``explanation_source`` is set authoritatively
    here (a provider cannot mislabel itself): "deterministic" when the
    deterministic provider or the fallback produced the text, "ai" when a
    validated non-deterministic provider did. The deterministic input
    artifacts are never modified by this function.
    """
    context = IntelligenceContext(
        changed_component=impact_ctx.changed_component,
        impacted_components=_ordered_unique(
            [*impact_ctx.direct_impacts, *impact_ctx.transitive_impacts]
        ),
        dependency_paths=[path.model_dump() for path in impact_ctx.dependency_paths],
        evidence=[ref.model_dump() for ref in impact_ctx.evidence],
        recommended_tests=[test.model_dump() for test in recommendations],
        risk_signals=[signal.model_dump() for signal in signals],
        release_checklist=[item.model_dump() for item in checklist],
    )

    try:
        active_provider = provider if provider is not None else get_provider()
        explanation = active_provider.explain(context)
        explanation = validate_explanation(explanation, context)
        explanation.explanation_source = (
            ExplanationSource.DETERMINISTIC
            if isinstance(active_provider, DeterministicProvider)
            else ExplanationSource.AI
        )
        return explanation
    except (HallucinationError, Exception):
        fallback = DeterministicProvider().explain(context)
        fallback.executive_summary = _FALLBACK_PREFIX + fallback.executive_summary
        return fallback
