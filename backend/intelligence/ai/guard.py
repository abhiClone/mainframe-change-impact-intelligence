"""Hallucination guard for the Phase 2A/2B AI explanation layer.

Validates that an IntelligenceExplanation references ONLY identifiers that
appear in the supplied IntelligenceContext:

- component IDs: changed_component + impacted_components
- test IDs: test_id values from recommended_tests
- signal IDs: id values from risk_signals
- incident IDs: id values from relevant_incidents (Phase 2B)

Additionally the explanation must echo the context's ``changed_component``
as ``subject_component``; a mismatch is rejected.

Candidate identifiers are regex-extracted from the seven explanation text
fields. Any candidate outside the allowed vocabulary raises
HallucinationError. Identifiers already known to the context pass through
untouched.

Trust boundary (explicit): identifier grounding is validated
automatically. Natural-language interpretation may still contain
unsupported wording, therefore AI prose is non-authoritative and
deterministic evidence remains the source of truth. No general
natural-language fact checker is attempted here.
"""

from __future__ import annotations

import re

from .ai_models import IntelligenceContext, IntelligenceExplanation

_COMPONENT_RE = re.compile(r"\b(?:program|job|proc|copybook|table):[A-Za-z0-9_#.\-]+\b")
_TEST_ID_RE = re.compile(r"\bTC-[A-Za-z0-9\-]+\b")
_INCIDENT_ID_RE = re.compile(r"\bINC-[A-Za-z0-9\-]+\b")


class HallucinationError(ValueError):
    """Raised when an explanation references identifiers outside the context."""

    def __init__(self, offending: list[str]) -> None:
        self.offending: list[str] = list(offending)
        super().__init__(
            "Explanation references identifiers not present in the context: "
            + ", ".join(self.offending)
        )


def validate_explanation(
    expl: IntelligenceExplanation, ctx: IntelligenceContext
) -> IntelligenceExplanation:
    """Check every candidate ID in the explanation against the context vocabulary.

    Returns the explanation unchanged when all candidates are known.
    Raises HallucinationError listing every offending identifier otherwise.
    """
    vocabulary: set[str] = {ctx.changed_component, *ctx.impacted_components}
    for test in ctx.recommended_tests:
        if isinstance(test, dict):
            test_id = test.get("test_id")
            if test_id:
                vocabulary.add(str(test_id))
    for signal in ctx.risk_signals:
        if isinstance(signal, dict):
            signal_id = signal.get("id")
            if signal_id:
                vocabulary.add(str(signal_id))
    for incident in ctx.relevant_incidents:
        if isinstance(incident, dict):
            incident_id = incident.get("id")
            if incident_id:
                vocabulary.add(str(incident_id))

    # The explanation must be about the component it was asked about.
    if expl.subject_component != ctx.changed_component:
        raise HallucinationError(
            [f"subject_component:{expl.subject_component or '<empty>'}"]
        )

    candidates: set[str] = set()
    for field in (
        expl.executive_summary,
        expl.technical_summary,
        expl.testing_summary,
        expl.release_considerations,
        expl.incident_summary,
        expl.historical_patterns,
        expl.release_history_considerations,
    ):
        candidates.update(_COMPONENT_RE.findall(field))
        candidates.update(_TEST_ID_RE.findall(field))
        candidates.update(_INCIDENT_ID_RE.findall(field))

    offending = sorted(candidate for candidate in candidates if candidate not in vocabulary)
    if offending:
        raise HallucinationError(offending)
    return expl
