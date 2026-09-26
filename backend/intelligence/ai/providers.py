"""Explanation providers for the Phase 2A AI explanation layer.

- DeterministicProvider: template-built explanation over the context only.
  No LLM, no network, always available. This is the default and the fallback.
- FakeProvider: fixed canned explanation for tests (interpolates only IDs
  that the supplied context contains, so it passes the hallucination guard).
- HttpLlmProvider: generic stdlib-only (urllib) chat-completions client,
  configured exclusively via environment variables. Never instantiated
  unless explicitly configured.
"""

from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod

from .ai_models import (
    ExplanationSource,
    IntelligenceContext,
    IntelligenceExplanation,
)


class IntelligenceProvider(ABC):
    """Explains an IntelligenceContext in four sections."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider identifier (e.g. 'deterministic')."""

    @abstractmethod
    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
        """Build an explanation using ONLY the supplied context."""


def _unique(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _incident_sections(context: IntelligenceContext) -> tuple[str, str, str]:
    """Build the three incident explanation sections from the supplied
    relevant incidents only (no selection, no invention)."""
    incidents = [
        i for i in context.relevant_incidents if isinstance(i, dict)
    ]
    if not incidents:
        return (
            "No historical incidents are deterministically relevant to this change.",
            "No historical failure patterns to report for this change.",
            "No historical incident considerations for this release.",
        )

    def _label(i: dict) -> str:
        return f"{i.get('id', '?')} — {i.get('title', '?')}"

    incident_summary = (
        f"{len(incidents)} historical incident{'s' if len(incidents) != 1 else ''} "
        f"deterministically relevant to the change to {context.changed_component}: "
        + "; ".join(
            f"{_label(i)} [primary reason: {i.get('primary_reason', '?')}, "
            f"historical severity: {i.get('severity', '?')}]"
            for i in incidents
        )
        + "."
    )

    failure_modes = _unique(
        [str(i.get("failure_mode", "?")) for i in incidents if i.get("failure_mode")]
    )
    root_causes = _unique(
        [
            str(i.get("root_cause_category", "?"))
            for i in incidents
            if i.get("root_cause_category")
        ]
    )
    historical_patterns = (
        f"Recurring failure modes in the supplied history: "
        f"{', '.join(failure_modes) if failure_modes else 'none recorded'}. "
        f"Root-cause categories observed: "
        f"{', '.join(root_causes) if root_causes else 'none recorded'}."
    )

    release_history_considerations = (
        "Based on the supplied history, the release team should be aware that: "
        + " ".join(
            f"{_label(i)} was previously resolved by: "
            f"{i.get('resolution_summary', 'not recorded')}"
            for i in incidents
        )
    )
    return incident_summary, historical_patterns, release_history_considerations


class DeterministicProvider(IntelligenceProvider):
    """Template-based explanation. No LLM, no network, always available.

    Emits only identifiers taken from the supplied context, so the output
    always passes the hallucination guard.
    """

    @property
    def name(self) -> str:
        return "deterministic"

    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
        impacted = _unique(context.impacted_components)
        n = len(impacted)
        tests = context.recommended_tests
        signals = context.risk_signals
        checklist = context.release_checklist

        high_signals = [s for s in signals if str(s.get("severity", "")).lower() == "high"]

        impacted_clause = (
            f" The impacted components are: {', '.join(impacted)}."
            if impacted
            else " No other components are impacted."
        )
        executive_summary = (
            f"Change to {context.changed_component} impacts {n} component"
            f"{'s' if n != 1 else ''}.{impacted_clause}"
            f" {len(tests)} test{'s' if len(tests) != 1 else ''} recommended,"
            f" {len(high_signals)} high-severity risk signal{'s' if len(high_signals) != 1 else ''},"
            f" {len(checklist)} release checklist item{'s' if len(checklist) != 1 else ''}."
        )

        path_lines = []
        for path in context.dependency_paths:
            edges = path.get("path", []) if isinstance(path, dict) else []
            target = path.get("impacted", "?") if isinstance(path, dict) else "?"
            endpoints = []
            for edge in edges if isinstance(edges, list) else []:
                if not isinstance(edge, dict):
                    continue
                endpoints.append(f"{edge.get('source', '?')} -[{edge.get('relationship', '?')}]-> {edge.get('target', '?')}")
            if endpoints:
                path_lines.append(f"{target}: " + "; ".join(endpoints))
            else:
                path_lines.append(f"{target}: reachable ({len(edges) if isinstance(edges, list) else 0} dependency edge(s))")
        technical_summary = (
            f"Impact analysis for {context.changed_component}: {n} impacted component"
            f"{'s' if n != 1 else ''} across {len(path_lines)} dependency path"
            f"{'s' if len(path_lines) != 1 else ''}, grounded in {len(context.evidence)} evidence reference(s)."
            + ("" if not path_lines else " Paths: " + " | ".join(path_lines) + ".")
        )

        test_lines = [
            f"{t.get('test_id', '?')} — {t.get('test_name', '?')} "
            f"[{t.get('test_type', '?')}, {t.get('impact_level', '?')} impact; "
            f"covers {len(t.get('matched_components', []) or [])} impacted component(s)]"
            for t in tests
            if isinstance(t, dict)
        ]
        testing_summary = (
            f"{len(tests)} test{'s' if len(tests) != 1 else ''} recommended to cover the impact set."
            + ("" if not test_lines else " " + " ".join(test_lines))
        )

        signal_lines = [
            f"{s.get('id', '?')}: {s.get('title', '?')} [{s.get('severity', '?')}]"
            for s in signals
            if isinstance(s, dict)
        ]
        checklist_lines = [
            f"{c.get('id', '?')}: {c.get('title', '?')} (rule: {c.get('rule', '?')})"
            for c in checklist
            if isinstance(c, dict)
        ]
        release_considerations = (
            f"{len(signals)} risk signal{'s' if len(signals) != 1 else ''} and "
            f"{len(checklist)} release checklist item{'s' if len(checklist) != 1 else ''} apply."
            + ("" if not signal_lines else " Risk signals: " + "; ".join(signal_lines) + ".")
            + ("" if not checklist_lines else " Checklist: " + "; ".join(checklist_lines) + ".")
        )

        incident_sections = _incident_sections(context)

        return IntelligenceExplanation(
            subject_component=context.changed_component,
            explanation_source=ExplanationSource.DETERMINISTIC,
            executive_summary=executive_summary,
            technical_summary=technical_summary,
            testing_summary=testing_summary,
            release_considerations=release_considerations,
            incident_summary=incident_sections[0],
            historical_patterns=incident_sections[1],
            release_history_considerations=incident_sections[2],
        )


class FakeProvider(IntelligenceProvider):
    """Fixed canned explanation for tests.

    Uses only identifiers present in the supplied context so the canned
    text passes the hallucination guard. Labeled ``ai`` because it stands
    in for a real LLM provider on the AI code path.
    """

    @property
    def name(self) -> str:
        return "fake"

    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
        first_impacted = (
            context.impacted_components[0]
            if context.impacted_components
            else context.changed_component
        )
        test_clause = ""
        if context.recommended_tests and isinstance(context.recommended_tests[0], dict):
            t = context.recommended_tests[0]
            test_clause = f" Run {t.get('test_id', '?')} ({t.get('test_name', '?')})."
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
        return IntelligenceExplanation(
            subject_component=context.changed_component,
            explanation_source=ExplanationSource.AI,
            executive_summary=(
                f"Canned explanation: change to {context.changed_component} "
                f"affects {first_impacted}."
            ),
            technical_summary=(
                f"Canned technical detail: {len(context.dependency_paths)} dependency "
                f"path(s) and {len(context.evidence)} evidence reference(s) supplied."
            ),
            testing_summary=f"Canned testing guidance.{test_clause}",
            release_considerations=(
                f"Canned release guidance: {len(context.risk_signals)} risk signal(s), "
                f"{len(context.release_checklist)} checklist item(s)."
            ),
            incident_summary=f"Canned incident summary.{incident_clause}",
            historical_patterns="Canned historical patterns from supplied incidents.",
            release_history_considerations=(
                "Canned history considerations from supplied incidents."
            ),
        )


class HttpLlmProvider(IntelligenceProvider):
    """Generic stdlib-only chat-completions client.

    Configured exclusively via environment variables:
      INTELLIGENCE_LLM_ENDPOINT, INTELLIGENCE_LLM_API_KEY, INTELLIGENCE_LLM_MODEL.
    Never instantiated unless explicitly configured (INTELLIGENCE_PROVIDER=http).
    """

    SYSTEM_INSTRUCTION = (
        "You are an assistant explaining a mainframe change-impact analysis. "
        "You may explain ONLY the supplied information. Do not introduce "
        "components, dependencies, tests, tables, jobs, incidents or evidence "
        "not present in the context. You may summarize ONLY the relevant "
        "incidents already supplied; you must not select additional incidents, "
        "create incidents, modify relevance reasons, or change their order. "
        "Respond with a JSON object with exactly these keys: "
        "executive_summary, technical_summary, testing_summary, "
        "release_considerations, incident_summary, historical_patterns, "
        "release_history_considerations."
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
                "HttpLlmProvider requires environment variables: " + ", ".join(missing)
            )

    @property
    def name(self) -> str:
        return "http"

    def explain(self, context: IntelligenceContext) -> IntelligenceExplanation:
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
        # The model is not required to echo these; fill them in so the
        # guard can still verify the subject it claims to address.
        data.setdefault("subject_component", context.changed_component)
        data.setdefault("explanation_source", ExplanationSource.AI.value)
        return IntelligenceExplanation(**data)


def get_provider() -> IntelligenceProvider:
    """Select the explanation provider from INTELLIGENCE_PROVIDER.

    Accepted values: 'deterministic' (default), 'fake', 'http'.
    Any unknown or missing value falls back to deterministic without crashing.
    """
    choice = os.environ.get("INTELLIGENCE_PROVIDER", "deterministic").strip().lower()
    if choice == "http":
        return HttpLlmProvider()
    if choice == "fake":
        return FakeProvider()
    return DeterministicProvider()
