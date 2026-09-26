"""Phase 2B: Historical Incident Intelligence package."""
from .models import (
    HistoricalIncident,
    IncidentIntelligence,
    RelevanceReason,
    RelevanceReasonType,
    RelevantIncident,
    REASON_PRECEDENCE,
)
from .relevance import build_incident_intelligence
from .repository import (
    IncidentDatasetError,
    IncidentRepository,
    YamlFileIncidentRepository,
    load_incidents,
)

__all__ = [
    "HistoricalIncident",
    "IncidentIntelligence",
    "RelevanceReason",
    "RelevanceReasonType",
    "RelevantIncident",
    "REASON_PRECEDENCE",
    "build_incident_intelligence",
    "IncidentDatasetError",
    "IncidentRepository",
    "YamlFileIncidentRepository",
    "load_incidents",
]
