"""Optional grounded change-set explanation (Phase 3A AI layer).

The AI may ONLY summarize the already-computed deterministic
ChangeSetIntelligence: release scope, major impacted areas, tests, risk
signals, historical incident themes, and overlap. It may NOT add changed
components, resolve ambiguous files, add impact/tests/risks/incidents,
modify priority, or create dependencies.

Trust boundary: the explanation input is the strict
ChangeSetExplanationContext; the hallucination guard rejects any
explanation referencing identifiers outside it (unknown component ids,
test ids, signal ids, incident ids, change roots). Provider failure
falls back to the deterministic release summary, and
``explanation_source`` is set authoritatively here.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from backend.intelligence.ai.ai_models import ExplanationSource
from backend.intelligence.ai.guard import HallucinationError

from .models import ChangeSetIntelligence

_COMPONENT_RE = re.compile(r"\b(?:program|job|proc|copybook|table):[A-Za-z0-9_#.\-]+\b")
_TEST_ID_RE = re.compile(r"\bTC-[A-Za-z0-9\-]+\b")
# Risk signal ids are UPPER_SNAKE tokens (e.g. SHARED_COPYBOOK_CHANGE).
# Priority levels (MUST_RUN / SHOULD_RUN) share that shape and are
# legitimate prose, so they are allow-listed rather than flagged.
_SIGNAL_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
_SIGNAL_ID_ALLOWLIST = {"MUST_RUN", "SHOULD_RUN"}
_INCIDENT_ID_RE = re.compile(r"\bINC-[A-Za-z0-9\-]+\b")

_FALLBACK_PREFIX = "AI explanation unavailable. Deterministic analysis remains available. "


class ChangeSetExplanationContext(BaseModel):
    """Everything a change-set explanation provider is allowed to see."""

    change_set_id: str = Field(
        ..., description="Deterministic change-set id (sorted change roots)."
    )
    change_roots: list[str] = Field(default_factory=list)
    mapped_files: list[dict] = Field(default_factory=list)
    ambiguous_files: list[dict] = Field(default_factory=list)
    unmapped_files: list[dict] = Field(default_factory=list)
    impacted_components: list[str] = Field(default_factory=list)
    overlap_components: list[str] = Field(default_factory=list)
    recommended_tests: list[dict] = Field(default_factory=list)
    risk_signals: list[dict] = Field(default_factory=list)
    release_checklist: list[dict] = Field(default_factory=list)
    relevant_incidents: list[dict] = Field(default_factory=list)
    summary_metrics: dict = Field(default_factory=dict)
    deterministic_summary: str = ""


class ChangeSetExplanation(BaseModel):
    """Grounded release explanation: summaries only, no new decisions."""

    subject: str = Field(
        ..., description="Must equal the context's change_set_id."
    )
    explanation_source: ExplanationSource
    scope_summary: str = Field(..., description="Release scope: files, components, mapping.")
    impact_summary: str = Field(..., description="Major impacted areas + overlap.")
    testing_summary: str = Field(..., description="What to test and why.")
    release_considerations: str = Field(..., description="Risks and checklist items.")
    incident_summary: str = Field(..., description="Historical incident themes (supplied incidents only).")
    overlap_notes: str = Field(..., description="What the change overlap means for the release.")


def change_set_id_for(roots: list[str]) -> str:
    """Deterministic change-set id from sorted change roots."""
    ordered = sorted(set(roots))
    return "change-set:" + "+".join(ordered) if ordered else "change-set:(empty)"


def build_change_set_context(
    intelligence: ChangeSetIntelligence,
) -> ChangeSetExplanationContext:
    """Project the deterministic result into the strict AI input contract."""
    roots = sorted({p.component_id for p in intelligence.per_change_analysis})
    impacted = [e.component_id for e in intelligence.unique_impacted_components]
    return ChangeSetExplanationContext(
        change_set_id=change_set_id_for(roots),
        change_roots=roots,
        mapped_files=[m.model_dump(mode="json") for m in intelligence.mapped_changes],
        ambiguous_files=[m.model_dump(mode="json") for m in intelligence.ambiguous_changes],
        unmapped_files=[m.model_dump(mode="json") for m in intelligence.unmapped_changes],
        impacted_components=impacted,
        overlap_components=list(intelligence.impacted_by_multiple_changes),
        recommended_tests=[t.model_dump(mode="json") for t in intelligence.recommended_tests],
        risk_signals=[s.model_dump(mode="json") for s in intelligence.risk_signals],
        release_checklist=[c.model_dump(mode="json") for c in intelligence.release_checklist],
        relevant_incidents=[
            {
                "id": a.incident.id,
                "title": a.incident.title,
                "severity": a.incident.severity,
                "primary_reason": a.primary_reason.value,
                "relevant_to_changes": [
                    r.model_dump(mode="json") for r in a.relevant_to_changes
                ],
                "failure_mode": a.incident.failure_mode,
                "root_cause_category": a.incident.root_cause_category,
            }
            for a in intelligence.relevant_incidents
        ],
        summary_metrics=intelligence.summary.model_dump(mode="json"),
        deterministic_summary=intelligence.deterministic_summary,
    )


def validate_change_set_explanation(
    expl: ChangeSetExplanation, ctx: ChangeSetExplanationContext
) -> ChangeSetExplanation:
    """Reject explanations referencing identifiers outside the context.

    Allowed vocabulary: change roots, impacted components, test ids,
    signal ids, incident ids. The subject must equal the context's
    deterministic change-set id. Raises HallucinationError otherwise.
    """
    vocabulary: set[str] = set(ctx.change_roots) | set(ctx.impacted_components)
    for test in ctx.recommended_tests:
        if isinstance(test, dict) and test.get("test_id"):
            vocabulary.add(str(test["test_id"]))
    for signal in ctx.risk_signals:
        if isinstance(signal, dict) and signal.get("id"):
            vocabulary.add(str(signal["id"]))
    for incident in ctx.relevant_incidents:
        if isinstance(incident, dict) and incident.get("id"):
            vocabulary.add(str(incident["id"]))

    if expl.subject != ctx.change_set_id:
        raise HallucinationError(
            [f"subject:{expl.subject or '<empty>'}"]
        )

    candidates: set[str] = set()
    for field in (
        expl.scope_summary,
        expl.impact_summary,
        expl.testing_summary,
        expl.release_considerations,
        expl.incident_summary,
        expl.overlap_notes,
    ):
        candidates.update(_COMPONENT_RE.findall(field))
        candidates.update(_TEST_ID_RE.findall(field))
        candidates.update(
            s for s in _SIGNAL_ID_RE.findall(field)
            if s not in _SIGNAL_ID_ALLOWLIST
        )
        candidates.update(_INCIDENT_ID_RE.findall(field))

    offending = sorted(c for c in candidates if c not in vocabulary)
    if offending:
        raise HallucinationError(offending)
    return expl


class ChangeSetExplainer(ABC):
    """Explains a ChangeSetExplanationContext using only the context."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider identifier (e.g. 'deterministic')."""

    @abstractmethod
    def explain(
        self, context: ChangeSetExplanationContext
    ) -> ChangeSetExplanation:
        """Summarize the supplied deterministic context; invent nothing."""


class DeterministicChangeSetExplainer(ChangeSetExplainer):
    """Template-built release explanation. No LLM, no network, always available."""

    @property
    def name(self) -> str:
        return "deterministic"

    def explain(
        self, context: ChangeSetExplanationContext
    ) -> ChangeSetExplanation:
        m = context.summary_metrics
        roots = ", ".join(context.change_roots) if context.change_roots else "none"
        impacted_n = len(context.impacted_components)
        overlap = (
            ", ".join(context.overlap_components)
            if context.overlap_components
            else "none"
        )
        must = sum(
            1 for t in context.recommended_tests
            if isinstance(t, dict) and t.get("impact_level") == "MUST_RUN"
        )
        tests_n = len(context.recommended_tests)
        signals_n = len(context.risk_signals)
        incidents_n = len(context.relevant_incidents)
        return ChangeSetExplanation(
            subject=context.change_set_id,
            explanation_source=ExplanationSource.DETERMINISTIC,
            scope_summary=(
                f"Release change set {context.change_set_id}: "
                f"{m.get('changed_files', 0)} changed file(s) mapping to "
                f"{len(context.change_roots)} changed component(s) ({roots}). "
                f"{len(context.ambiguous_files)} ambiguous file(s), "
                f"{len(context.unmapped_files)} unmapped file(s)."
            ),
            impact_summary=(
                f"{impacted_n} unique component(s) impacted across the change "
                f"set. Components impacted by more than one change: {overlap}."
            ),
            testing_summary=(
                f"{tests_n} deduplicated test recommendation(s), {must} "
                f"MUST_RUN. Strongest deterministic priority wins per test; "
                f"all per-change reasons are preserved in the release result."
            ),
            release_considerations=(
                f"{signals_n} deduplicated risk signal(s) and "
                f"{len(context.release_checklist)} checklist item(s) apply to "
                f"the release. Severities remain rule-based and are not "
                f"escalated by change overlap."
            ),
            incident_summary=(
                f"{incidents_n} historical incident(s) deterministically "
                f"relevant to the change set (historical severity is not "
                f"current relevance)."
                if incidents_n
                else "No historical incidents are deterministically relevant "
                "to this change set."
            ),
            overlap_notes=(
                f"Overlap components ({overlap}) sit at the intersection of "
                f"several changes; verify them once against each change root "
                f"rather than once per change."
                if context.overlap_components
                else "No component is impacted by more than one change; the "
                "change roots are independent in impact terms."
            ),
        )


class FakeChangeSetExplainer(ChangeSetExplainer):
    """Fixed canned explanation for tests; interpolates only context ids.

    Labeled ``ai`` because it stands in for a real LLM provider on the AI
    code path; the guard still validates every identifier it mentions.
    """

    @property
    def name(self) -> str:
        return "fake"

    def explain(
        self, context: ChangeSetExplanationContext
    ) -> ChangeSetExplanation:
        first_root = context.change_roots[0] if context.change_roots else "none"
        first_test = ""
        if context.recommended_tests and isinstance(context.recommended_tests[0], dict):
            first_test = f" Run {context.recommended_tests[0].get('test_id', '?')}."
        incident_ids = [
            str(i.get("id"))
            for i in context.relevant_incidents
            if isinstance(i, dict) and i.get("id")
        ]
        incident_clause = (
            f" Relevant historical incidents: {', '.join(incident_ids)}."
            if incident_ids
            else " No relevant historical incidents supplied."
        )
        return ChangeSetExplanation(
            subject=context.change_set_id,
            explanation_source=ExplanationSource.AI,
            scope_summary=f"Fake release summary for {first_root}.{first_test}",
            impact_summary=f"Fake impact summary for {first_root}.",
            testing_summary=f"Fake testing summary.{first_test}",
            release_considerations="Fake release considerations.",
            incident_summary=f"Fake incident summary.{incident_clause}",
            overlap_notes="Fake overlap notes.",
        )


class HttpChangeSetExplainer(ChangeSetExplainer):
    """Generic stdlib-only chat-completions client for change-set summaries.

    Configured exclusively via INTELLIGENCE_LLM_ENDPOINT,
    INTELLIGENCE_LLM_API_KEY, INTELLIGENCE_LLM_MODEL. Never instantiated
    unless explicitly configured (CHANGE_SET_EXPLAINER=http).
    """

    SYSTEM_INSTRUCTION = (
        "You summarize a deterministic mainframe change-impact analysis. "
        "Use ONLY the identifiers present in the supplied JSON context "
        "(component ids like 'copybook:WARRCOPY', test ids like 'TC-001', "
        "signal ids, incident ids like 'INC-1001'). Never invent components, "
        "tests, risks, incidents, or dependencies. Return a JSON object with "
        "exactly these string keys: scope_summary, impact_summary, "
        "testing_summary, release_considerations, incident_summary, "
        "overlap_notes."
    )

    def __init__(self) -> None:
        self.endpoint = os.environ.get("INTELLIGENCE_LLM_ENDPOINT", "").strip()
        self.api_key = os.environ.get("INTELLIGENCE_LLM_API_KEY", "").strip()
        self.model = os.environ.get("INTELLIGENCE_LLM_MODEL", "").strip()
        missing = [
            name
            for name, value in (
                ("INTELLIGENCE_LLM_ENDPOINT", self.endpoint),
                ("INTELLIGENCE_LLM_API_KEY", self.api_key),
                ("INTELLIGENCE_LLM_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "HttpChangeSetExplainer requires environment variables: "
                + ", ".join(missing)
            )

    @property
    def name(self) -> str:
        return "http"

    def explain(
        self, context: ChangeSetExplanationContext
    ) -> ChangeSetExplanation:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_INSTRUCTION},
                {"role": "user", "content": context.model_dump_json(indent=2)},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        data.setdefault("subject", context.change_set_id)
        data.setdefault("explanation_source", ExplanationSource.AI.value)
        return ChangeSetExplanation(**data)


def get_change_set_explainer() -> ChangeSetExplainer:
    """Select the change-set explainer from CHANGE_SET_EXPLAINER.

    Accepted values: 'deterministic' (default), 'fake', 'http'. Unknown or
    missing values fall back to deterministic without crashing.
    """
    choice = os.environ.get("CHANGE_SET_EXPLAINER", "deterministic").strip().lower()
    if choice == "http":
        return HttpChangeSetExplainer()
    if choice == "fake":
        return FakeChangeSetExplainer()
    return DeterministicChangeSetExplainer()


def explain_change_set(
    intelligence: ChangeSetIntelligence,
    provider: ChangeSetExplainer | None = None,
) -> ChangeSetExplanation:
    """Explain a computed ChangeSetIntelligence (summaries only).

    Builds the strict context, asks the provider, and runs the
    hallucination guard. Any failure — provider exception or guard
    rejection — yields the deterministic explanation with a fallback
    prefix. The deterministic result is never modified by this function.
    """
    context = build_change_set_context(intelligence)
    try:
        active = provider if provider is not None else get_change_set_explainer()
        explanation = active.explain(context)
        explanation = validate_change_set_explanation(explanation, context)
        explanation.explanation_source = (
            ExplanationSource.DETERMINISTIC
            if isinstance(active, DeterministicChangeSetExplainer)
            else ExplanationSource.AI
        )
        return explanation
    except (HallucinationError, Exception):
        fallback = DeterministicChangeSetExplainer().explain(context)
        fallback.scope_summary = _FALLBACK_PREFIX + fallback.scope_summary
        return fallback
