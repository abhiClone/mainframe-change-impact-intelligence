"""Pydantic v2 contracts for the Phase 2A AI explanation layer.

IntelligenceContext is the STRICT input contract: the explanation layer
receives only this object. No repository paths, no raw source text, no
unfiltered graph access.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExplanationSource(str, Enum):
    """Who actually produced the explanation text.

    DETERMINISTIC: template-built by DeterministicProvider (or the
        deterministic fallback) — no LLM was involved.
    AI: produced by a real LLM provider (or its test double, FakeProvider)
        and successfully validated by the hallucination guard.
    """

    DETERMINISTIC = "deterministic"
    AI = "ai"


class IntelligenceContext(BaseModel):
    """Everything an explanation provider is allowed to see."""

    changed_component: str = Field(
        ..., description="Component ID of the changed component, e.g. 'copybook:WARRCOPY'."
    )
    impacted_components: list[str] = Field(
        default_factory=list,
        description="Component IDs impacted by the change (direct + transitive).",
    )
    dependency_paths: list[dict] = Field(
        default_factory=list,
        description="Serialized DependencyPath entries (impacted component + path edges).",
    )
    evidence: list[dict] = Field(
        default_factory=list,
        description="Serialized EvidenceRef entries (file, line, text).",
    )
    recommended_tests: list[dict] = Field(
        default_factory=list,
        description="Serialized RecommendedTest entries.",
    )
    risk_signals: list[dict] = Field(
        default_factory=list,
        description="Serialized RiskSignal entries.",
    )
    release_checklist: list[dict] = Field(
        default_factory=list,
        description="Serialized ChecklistItem entries.",
    )


class IntelligenceExplanation(BaseModel):
    """Four-section explanation produced by an explanation provider.

    ``subject_component`` echoes the changed component the explanation was
    asked about; the hallucination guard rejects any explanation whose
    subject does not match the supplied context. ``explanation_source``
    tells the UI/API consumer whether an LLM generated the text.
    """

    subject_component: str = Field(
        ...,
        description="Changed component id this explanation is about; must equal the context's changed_component.",
    )
    explanation_source: ExplanationSource = Field(
        ..., description="Whether the text was produced by an LLM ('ai') or deterministically."
    )
    executive_summary: str = Field(..., description="One-paragraph summary for non-technical readers.")
    technical_summary: str = Field(..., description="Impact mechanics: paths, components, dependencies.")
    testing_summary: str = Field(..., description="What to test and why.")
    release_considerations: str = Field(..., description="Risks and checklist items for the release.")
