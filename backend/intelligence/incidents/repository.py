"""Phase 2B incident repository: abstraction + local file-backed loader.

Only the local YAML implementation is provided for Phase 2B. The
IncidentRepository ABC keeps future external integrations (ServiceNow,
Jira, ...) replaceable without touching the relevance engine.

The loader VALIDATES the dataset at load time:

- every incident has a unique, non-empty id
- occurred_at is a valid date (ISO YYYY-MM-DD)
- severity in {low, medium, high, critical}
- status in {open, investigating, resolved}
- title is non-empty
- at least one linked component
- EVERY linked component exists in the Phase 1 component graph
- duplicate linked components are normalized/deduplicated

Invalid data raises IncidentDatasetError with a clear message naming the
incident and the problem. Invalid data NEVER silently contaminates
intelligence results.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import HistoricalIncident

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}
_VALID_STATUSES = {"open", "investigating", "resolved"}

DATASET_PATH = (
    Path(__file__).resolve().parents[3]
    / "sample_mainframe"
    / "incidents"
    / "incidents.yaml"
)


class IncidentDatasetError(ValueError):
    """Raised when the incident dataset fails validation at load time."""


class IncidentRepository(ABC):
    """Source of historical incident records."""

    @abstractmethod
    def list_incidents(self) -> list[HistoricalIncident]:
        """Return all known historical incidents (validated)."""


class YamlFileIncidentRepository(IncidentRepository):
    """Local YAML-backed incident repository (Phase 2B implementation)."""

    def __init__(
        self,
        path: Path | str = DATASET_PATH,
        valid_component_ids: set[str] | None = None,
    ) -> None:
        self._path = Path(path)
        # The Phase 1 component graph is the authority for linked-component
        # ids. Passing None disables component validation (used only in
        # focused unit tests that supply their own context).
        self._valid_component_ids = valid_component_ids

    def list_incidents(self) -> list[HistoricalIncident]:
        if not self._path.exists():
            raise IncidentDatasetError(
                f"incident dataset not found: {self._path}"
            )
        with open(self._path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict) or "incidents" not in data:
            raise IncidentDatasetError(
                f"incident dataset must be a mapping with an 'incidents' list: {self._path}"
            )
        entries = data["incidents"]
        if not isinstance(entries, list):
            raise IncidentDatasetError(
                f"'incidents' must be a list: {self._path}"
            )

        incidents: list[HistoricalIncident] = []
        seen_ids: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise IncidentDatasetError(
                    f"incident entry #{index} is not a mapping"
                )
            incident = self._validate_entry(entry, index)
            if incident.id in seen_ids:
                raise IncidentDatasetError(
                    f"duplicate incident id: {incident.id}"
                )
            seen_ids.add(incident.id)
            incidents.append(incident)
        return incidents

    def _validate_entry(
        self, entry: dict, index: int
    ) -> HistoricalIncident:
        label = entry.get("id") or f"entry #{index}"
        try:
            incident = HistoricalIncident(**entry)
        except ValidationError as exc:
            raise IncidentDatasetError(
                f"invalid incident {label}: {exc.errors()[0]['msg']}"
            ) from exc

        if not incident.title.strip():
            raise IncidentDatasetError(f"incident {label} has an empty title")
        if not isinstance(incident.occurred_at, date):
            raise IncidentDatasetError(
                f"incident {label} has an invalid occurred_at date"
            )
        if incident.severity not in _VALID_SEVERITIES:
            raise IncidentDatasetError(
                f"incident {label} has invalid severity: {incident.severity!r}"
            )
        if incident.status not in _VALID_STATUSES:
            raise IncidentDatasetError(
                f"incident {label} has invalid status: {incident.status!r}"
            )
        if not incident.linked_components:
            raise IncidentDatasetError(
                f"incident {label} has no linked components"
            )
        # Deduplicate linked components, preserving first-seen order.
        deduped = list(dict.fromkeys(incident.linked_components))
        incident.linked_components = deduped
        if self._valid_component_ids is not None:
            unknown = [
                comp for comp in deduped
                if comp not in self._valid_component_ids
            ]
            if unknown:
                raise IncidentDatasetError(
                    f"incident {incident.id} links unknown component(s) "
                    f"not present in the Phase 1 graph: {', '.join(unknown)}"
                )
        return incident


def load_incidents(
    path: Path | str = DATASET_PATH,
    valid_component_ids: set[str] | None = None,
) -> list[HistoricalIncident]:
    """Load and validate the YAML incident dataset."""
    return YamlFileIncidentRepository(
        path=path, valid_component_ids=valid_component_ids
    ).list_incidents()
