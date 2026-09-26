"""Phase 3A: deterministic change-set & release-candidate analysis.

Sits above the frozen layers (Phase 1 dependencies/impact, Phase 2A
release intelligence, Phase 2B incident relevance) and aggregates them
per change set. Never reimplements them; no LLM decides mapping, impact,
tests, risks, checklist items, or incidents.
"""
from .models import (
    AggregatedChecklistItem,
    AggregatedIncident,
    AggregatedResource,
    AggregatedSignal,
    AggregatedTest,
    ChangedFile,
    ChangeSet,
    ChangeSetIntelligence,
    ChangeSetSummary,
    ImpactedComponentEntry,
    MappedChange,
    PerChangeAnalysis,
)
from .providers import (
    ChangeSetProvider,
    ExplicitFileListProvider,
    GitDiffProvider,
)
from .service import ChangeSetAnalyzer, RepositoryView, build_view

__all__ = [
    "AggregatedChecklistItem",
    "AggregatedIncident",
    "AggregatedResource",
    "AggregatedSignal",
    "AggregatedTest",
    "ChangedFile",
    "ChangeSet",
    "ChangeSetAnalyzer",
    "ChangeSetIntelligence",
    "ChangeSetProvider",
    "ChangeSetSummary",
    "ExplicitFileListProvider",
    "GitDiffProvider",
    "ImpactedComponentEntry",
    "MappedChange",
    "PerChangeAnalysis",
    "RepositoryView",
    "build_view",
]
