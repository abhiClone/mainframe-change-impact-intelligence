"""Phase 2B incident data models (Pydantic v2).

HistoricalIncident is structured synthetic historical evidence: every
linked component MUST be a real Phase 1 component ID (validated by the
repository loader, never derived from prose by an LLM).

RelevantIncident / IncidentIntelligence are the deterministic output of
the relevance engine (backend/intelligence/incidents/relevance.py).
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from backend.intelligence.models import (
    DependencyPath,
    EvidenceRef,
    InvolvedResource,
)

Severity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "investigating", "resolved"]


class HistoricalIncident(BaseModel):
    """One synthetic historical production incident.

    ``linked_components`` are authoritative structured data: real Phase 1
    component IDs (e.g. ``program:WARR001``). The repository validates
    every entry against the Phase 1 component graph at load time.
    """

    id: str
    title: str
    occurred_at: date
    severity: Severity
    status: IncidentStatus
    summary: str
    symptoms: list[str] = Field(default_factory=list)
    linked_components: list[str] = Field(default_factory=list)
    failure_mode: str = ""
    root_cause_category: str = ""
    root_cause_summary: str = ""
    resolution_summary: str = ""


class RelevanceReasonType(str, Enum):
    """Deterministic relevance reason types, in precedence order.

    The enum order IS the precedence order used for primary-reason
    selection and result ordering (see docs/incident-relevance.md).
    """

    CHANGED_COMPONENT_MATCH = "CHANGED_COMPONENT_MATCH"
    DIRECT_IMPACT_MATCH = "DIRECT_IMPACT_MATCH"
    TRANSITIVE_IMPACT_MATCH = "TRANSITIVE_IMPACT_MATCH"
    INVOLVED_WRITE_RESOURCE_MATCH = "INVOLVED_WRITE_RESOURCE_MATCH"
    INVOLVED_READ_RESOURCE_MATCH = "INVOLVED_READ_RESOURCE_MATCH"


# The single authoritative precedence list: strongest reason first.
REASON_PRECEDENCE: list[RelevanceReasonType] = list(RelevanceReasonType)


class RelevanceReason(BaseModel):
    """One deterministic reason an incident is relevant to a change.

    ``explanation`` is deterministic template prose built only from the
    reason type, the matched component, and the change context — never
    LLM output. ``evidence`` carries real Phase 1 file/line/text refs.
    """

    reason: RelevanceReasonType
    matched_component: str
    explanation: str
    supporting_paths: list[DependencyPath] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class RelevantIncident(BaseModel):
    """An incident selected by the deterministic relevance engine.

    Multiple valid reasons are preserved; ``primary_reason`` is the
    strongest by REASON_PRECEDENCE and drives ordering/display only.
    """

    incident: HistoricalIncident
    primary_reason: RelevanceReasonType
    relevance_reasons: list[RelevanceReason]  # all reasons, precedence order
    matched_components: list[str]  # sorted linked components that matched
    # The involved DB2 resource entries behind INVOLVED_* reasons
    # (empty for pure impact-component matches).
    supporting_resources: list[InvolvedResource] = Field(default_factory=list)


class IncidentIntelligence(BaseModel):
    """Deterministic historical-incident intelligence for a change.

    The two count maps are deliberately distinct:

    - ``primary_tier_counts``: incidents counted by PRIMARY reason tier;
      sums to ``total_relevant_incidents`` (no double-counting).
    - ``reason_counts``: every valid relevance reason counted; may exceed
      the total because one incident can carry multiple reasons (e.g. an
      incident linked to a table that is both read and written).
    """

    changed_component: str
    relevant_incidents: list[RelevantIncident]
    total_relevant_incidents: int
    primary_tier_counts: dict[str, int]
    reason_counts: dict[str, int]
