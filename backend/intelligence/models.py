"""Phase 2A intelligence data models (Pydantic v2).

Shared contract for the intelligence track: impact context, test
recommendation, risk signals, and the release checklist. Also consumed
by the (separate) grounded AI layer and the API/UI tracks.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    file: str
    line: int
    text: str


class PathEdge(BaseModel):
    """One dependency edge in the dependency-graph direction.

    ``source`` depends on ``target`` via ``relationship``; e.g.
    source=program:WARR001, target=copybook:WARRCOPY,
    relationship=USES_COPYBOOK.
    """

    source: str
    target: str
    relationship: str
    evidence: EvidenceRef


class DependencyPath(BaseModel):
    impacted: str
    path: list[PathEdge]


class InvolvedResource(BaseModel):
    """A DB2 table used by a program in the impact set.

    ``involved`` is NOT ``impacted``: the table does not depend on the
    change, it is *used by* a component that does. Derived deterministically
    from existing Phase 1 READS_TABLE/WRITES_TABLE edges of the impacted
    COBOL programs (plus the changed component's own edges when the changed
    component is itself a program). Read and write access stay
    distinguishable via ``access``.
    """

    table: str
    access: str  # "read" | "write" — mirrors READS_TABLE / WRITES_TABLE
    used_by: list[str]  # impacted program ids holding this edge
    evidence: list[EvidenceRef]


class ImpactContext(BaseModel):
    changed_component: str
    changed_component_type: str
    direct_impacts: list[str]
    transitive_impacts: list[str]
    dependency_paths: list[DependencyPath]
    relationships: list[str]
    evidence: list[PathEdge]
    affected_programs: list[str]
    affected_copybooks: list[str]
    affected_jobs: list[str]
    affected_procs: list[str]
    affected_tables: list[str]
    # Involved (not impacted) DB2 resources: tables read/written by the
    # impacted programs via existing Phase 1 graph edges. A table listed
    # here does NOT depend on the change.
    read_tables: list[str]
    write_tables: list[str]
    involved_resources: list[InvolvedResource]
    maximum_impact_depth: int
    total_impacted_components: int


class TestCase(BaseModel):
    id: str
    name: str
    type: str
    covers: list[str]
    execution: dict | None = None
    description: str = ""


class RecommendedTest(BaseModel):
    test_id: str
    test_name: str
    test_type: str
    matched_components: list[str]
    impact_level: str
    dependency_paths: list[DependencyPath]
    rationale: str
    evidence: list[EvidenceRef]


class RiskSignal(BaseModel):
    id: str
    severity: str
    title: str
    explanation: str
    triggered_by: list[str]
    supporting_components: list[str]
    evidence: list[EvidenceRef]


class ChecklistItem(BaseModel):
    id: str
    title: str
    detail: str
    rule: str
    related_components: list[str]
