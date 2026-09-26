"""Phase 3A change-set data models (Pydantic v2).

Typed contracts for deterministic change-set & release-candidate
analysis. The change-set layer sits ABOVE the frozen layers:

  Phase 1 dependencies -> Phase 1 impact -> Phase 2A release intelligence
  -> Phase 2B incident relevance -> Phase 3A aggregation (this package).

It aggregates them; it never reimplements them and never lets an LLM
decide mapping, impact, tests, risks, checklist items, or incidents.

Release semantics (fixed by the Phase 3A remediation):

- ``changed_components`` = components explicitly changed in the release.
- ``unique_impacted_components`` = downstream impacted components,
  EXCLUDING the explicitly changed roots.
- A changed root that is itself impacted by another changed root is
  preserved in ``ChangedComponent.also_impacted_by`` (cross-impact);
  it is never silently dropped and never double-counted as downstream.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.intelligence.incidents.models import (
    HistoricalIncident,
    RelevanceReason,
    RelevanceReasonType,
)
from backend.intelligence.models import (
    ChecklistItem,
    DependencyPath,
    EvidenceRef,
    ImpactContext,
    InvolvedResource,
    RecommendedTest,
    RiskSignal,
)

ChangeStatus = Literal["modified", "added", "deleted", "renamed", "unknown"]
MappingStatus = Literal[
    "mapped", "ambiguous", "unmapped", "requires_base_snapshot"
]
Snapshot = Literal["base", "head"]
TestImpactLevel = Literal["MUST_RUN", "SHOULD_RUN"]
RiskSeverity = Literal["low", "medium", "high"]
ResourceAccess = Literal["read", "write"]


class ChangedFile(BaseModel):
    """One file in a change set, as supplied by a provider."""

    path: str = Field(
        ..., description="Repository-relative path, e.g. 'copybook/WARRCOPY.cpy'."
    )
    status: ChangeStatus = Field(
        default="modified",
        description="modified | added | deleted | renamed | unknown.",
    )
    old_path: str | None = Field(
        default=None,
        description="Previous path for renames (preserved from Git when supplied).",
    )


class ChangeSet(BaseModel):
    """The raw input to Phase 3A: a set of changed files."""

    files: list[ChangedFile] = Field(default_factory=list)
    source: str = Field(
        default="explicit",
        description="How the change set was produced: 'explicit' | 'git-diff'.",
    )
    base_ref: str | None = Field(default=None)
    head_ref: str | None = Field(default=None)


class MappedChange(BaseModel):
    """Deterministic file -> component mapping outcome for one file.

    ``component_ids`` holds the CONFIRMED changed components for this
    file (empty unless mapping_status == "mapped"). Ambiguous files list
    every candidate component and select nothing; unmapped files create
    no impact; deleted files without a base snapshot cannot be resolved
    safely and are reported as requires_base_snapshot.

    Renames are ONE file event (status == "renamed") with
    ``previous_component_ids`` (old path, base snapshot) and
    ``current_component_ids`` (new path, head snapshot); ``component_ids``
    is their union. The old path and the rename status are preserved in
    the user-facing result.
    """

    file: ChangedFile
    mapping_status: MappingStatus
    component_ids: list[str] = Field(default_factory=list)
    candidate_components: list[str] = Field(default_factory=list)
    selected_component_ids: list[str] = Field(default_factory=list)
    previous_component_ids: list[str] = Field(default_factory=list)
    current_component_ids: list[str] = Field(default_factory=list)
    snapshot: Snapshot = Field(
        default="head",
        description="'head' when mapped against the current tree, "
        "'base' when mapped against the Git base snapshot (deletions).",
    )
    note: str = Field(default="")


class PerChangeAnalysis(BaseModel):
    """Independent per-root analysis reusing the frozen engines.

    Every section is produced by the existing Phase 1 / 2A / 2B code on
    the unchanged single-component semantics; Phase 3A only calls them
    once per confirmed changed component.
    """

    component_id: str
    source_file: str
    snapshot: Snapshot = "head"
    impact: ImpactContext
    recommended_tests: list[RecommendedTest] = Field(default_factory=list)
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    release_checklist: list[ChecklistItem] = Field(default_factory=list)
    # Phase 2B incident intelligence for this single root (unchanged
    # per-component semantics; serialized form to keep this model light).
    incident_intelligence: dict = Field(default_factory=dict)


class ChangeRootRef(BaseModel):
    """A changed root together with the snapshot it was analysed on."""

    change_root: str
    snapshot: Snapshot


class ChangedComponent(BaseModel):
    """One component explicitly changed in the release.

    ``originating_files`` preserves every normalized input file path
    that resolved to this component (deduplication never erases file
    provenance). ``previous_component_ids`` records the base-snapshot
    identity for renames. ``also_impacted_by`` records cross-impact:
    other changed roots whose impact includes this changed component.
    """

    component_id: str
    originating_files: list[str] = Field(default_factory=list)
    snapshot: Snapshot = "head"
    previous_component_ids: list[str] = Field(default_factory=list)
    also_impacted_by: list[ChangeRootRef] = Field(default_factory=list)


class ImpactProvenance(BaseModel):
    """Per-root provenance for one impacted component."""

    change_root: str
    snapshot: Snapshot
    depth: int
    dependency_paths: list[DependencyPath] = Field(default_factory=list)


class ImpactedComponentEntry(BaseModel):
    """One release-level DOWNSTREAM impacted component.

    Changed roots are excluded here by definition; see
    ``ChangedComponent.also_impacted_by`` for cross-impact between
    changed roots. Every per-root reference carries its snapshot so
    mixed base/head evidence stays attributable.
    """

    component_id: str
    impacted_by: list[str] = Field(
        ..., description="Sorted changed roots whose impact includes this component."
    )
    impacted_by_count: int
    per_root: list[ImpactProvenance] = Field(default_factory=list)


class PerRootTest(BaseModel):
    change_root: str
    snapshot: Snapshot = "head"
    impact_level: TestImpactLevel
    rationale: str
    matched_components: list[str] = Field(default_factory=list)


class AggregatedTest(BaseModel):
    """One deduplicated release-level test recommendation.

    The release priority is the strongest deterministic priority across
    roots (MUST_RUN beats SHOULD_RUN); every original per-root reason
    remains inspectable in ``per_root``.
    """

    test_id: str
    test_name: str
    test_type: str
    impact_level: TestImpactLevel
    rationale: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    recommended_because_of: list[ChangeRootRef] = Field(default_factory=list)
    per_root: list[PerRootTest] = Field(default_factory=list)


class AggregatedResource(BaseModel):
    """One deduplicated involved DB2 resource (read and write stay distinct)."""

    table: str
    access: ResourceAccess
    used_by: list[str] = Field(default_factory=list)
    associated_change_roots: list[ChangeRootRef] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AggregatedSignal(BaseModel):
    """One deduplicated release-level risk signal.

    Severity stays rule-based: the strongest deterministic severity
    across roots is kept (documented Phase 3 rule); severity is never
    escalated merely because several changes triggered the same signal.
    The human-readable ``explanation`` is regenerated deterministically
    from the MERGED structured fields (never inherited from the first
    processed root), so root input order cannot change release prose.
    """

    id: str
    severity: RiskSeverity
    title: str
    explanation: str
    triggered_by: list[str] = Field(default_factory=list)
    supporting_components: list[str] = Field(default_factory=list)
    change_roots: list[ChangeRootRef] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AggregatedChecklistItem(BaseModel):
    """One deduplicated release-level checklist item.

    Like signals, ``detail`` is regenerated from the merged structured
    fields (sorted) rather than copied from the first root.
    """

    id: str
    title: str
    detail: str
    rule: str
    related_components: list[str] = Field(default_factory=list)
    applicable_change_roots: list[ChangeRootRef] = Field(default_factory=list)


class PerChangeIncidentReason(BaseModel):
    change_root: str
    snapshot: Snapshot = "head"
    primary_reason: RelevanceReasonType
    relevance_reasons: list[RelevanceReason] = Field(default_factory=list)
    matched_components: list[str] = Field(default_factory=list)


class AggregatedIncident(BaseModel):
    """One deduplicated historically relevant incident.

    ``primary_reason`` is the strongest deterministic reason across all
    change roots (existing REASON_PRECEDENCE); every per-change reason
    remains inspectable. No AI relevance score is ever created.
    """

    incident: HistoricalIncident
    relevant_to_changes: list[ChangeRootRef] = Field(default_factory=list)
    per_change: list[PerChangeIncidentReason] = Field(default_factory=list)
    primary_reason: RelevanceReasonType


class ChangeSetSummary(BaseModel):
    """Deterministic release summary metrics (no opaque risk score)."""

    changed_files: int
    changed_components: int
    cross_impacted_changed_components: int
    ambiguous_files: int
    unmapped_files: int
    unresolved_files: int
    direct_impact_union: int
    transitive_impact_union: int
    unique_impacted_components: int
    overlap_impacted_components: int
    unique_recommended_tests: int
    must_run_tests: int
    should_run_tests: int
    involved_db2_reads: int
    involved_db2_writes: int
    risk_signals: int
    checklist_items: int
    relevant_incidents: int


class ChangeSetIntelligence(BaseModel):
    """The release-level Phase 3A result: ChangeSetIntelligence."""

    change_set: ChangeSet
    mapped_changes: list[MappedChange] = Field(default_factory=list)
    ambiguous_changes: list[MappedChange] = Field(default_factory=list)
    unmapped_changes: list[MappedChange] = Field(default_factory=list)
    unresolved_changes: list[MappedChange] = Field(default_factory=list)
    per_change_analysis: list[PerChangeAnalysis] = Field(default_factory=list)
    changed_components: list[ChangedComponent] = Field(default_factory=list)
    unique_impacted_components: list[ImpactedComponentEntry] = Field(
        default_factory=list
    )
    impacted_by_one_change: list[str] = Field(default_factory=list)
    impacted_by_multiple_changes: list[str] = Field(default_factory=list)
    involved_resources: list[AggregatedResource] = Field(default_factory=list)
    recommended_tests: list[AggregatedTest] = Field(default_factory=list)
    risk_signals: list[AggregatedSignal] = Field(default_factory=list)
    release_checklist: list[AggregatedChecklistItem] = Field(
        default_factory=list
    )
    relevant_incidents: list[AggregatedIncident] = Field(default_factory=list)
    mixed_snapshot_analysis: bool = Field(
        default=False,
        description="True when the release combines base-snapshot roots "
        "(deletions / rename-away identities) and head-snapshot roots.",
    )
    summary: ChangeSetSummary
    deterministic_summary: str = Field(
        default="", description="Template-built release summary (always present)."
    )
    ai_explanation: dict = Field(
        default_factory=dict,
        description="Serialized ChangeSetExplanation (grounded; optional).",
    )
