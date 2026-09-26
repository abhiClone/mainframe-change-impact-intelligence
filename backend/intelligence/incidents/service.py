"""Phase 2B service helpers: validated incident loading + intelligence.

Builds IncidentIntelligence for a component by composing the frozen
Phase 1 graph (for component-id validation), the Phase 2A impact context,
and the deterministic relevance engine. Additively layered: it never
modifies Phase 2A decision logic.
"""
from __future__ import annotations

from backend.intelligence.impact_context import _shared, build_impact_context
from backend.intelligence.models import ImpactContext

from .models import HistoricalIncident, IncidentIntelligence
from .relevance import build_incident_intelligence
from .repository import IncidentDatasetError, load_incidents

_VALID_COMPONENT_IDS: set[str] | None = None
_INCIDENTS: list[HistoricalIncident] | None = None


def valid_component_ids() -> set[str]:
    """All Phase 1 component ids (cached per process)."""
    global _VALID_COMPONENT_IDS
    if _VALID_COMPONENT_IDS is None:
        graph, _ = _shared()
        _VALID_COMPONENT_IDS = {c["id"] for c in graph.components()}
    return _VALID_COMPONENT_IDS


def get_incidents() -> list[HistoricalIncident]:
    """Load and validate the incident dataset (cached per process).

    Raises IncidentDatasetError with a clear message on invalid data;
    invalid data is never silently accepted.
    """
    global _INCIDENTS
    if _INCIDENTS is None:
        _INCIDENTS = load_incidents(
            valid_component_ids=valid_component_ids()
        )
    return _INCIDENTS


def get_incident(component_id: str) -> HistoricalIncident | None:
    for incident in get_incidents():
        if incident.id == component_id:
            return incident
    return None


def incident_intelligence_for(component_id: str) -> IncidentIntelligence:
    """Deterministic historical-incident intelligence for a changed component.

    Raises KeyError for an unknown component id (Phase 1 contract).
    """
    impact_ctx: ImpactContext = build_impact_context(component_id)
    return build_incident_intelligence(impact_ctx, get_incidents())
