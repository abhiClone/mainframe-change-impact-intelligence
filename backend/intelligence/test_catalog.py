"""Load the synthetic test catalog for test recommendation.

The loader VALIDATES the catalog at load time:

- the file is valid YAML holding a mapping with a ``tests`` list
- every test has a unique, non-empty id
- every test has a non-empty name
- ``covers`` is a non-empty list and, when the Phase 1 component graph is
  supplied, EVERY covered component exists in it
- ``execution.job``, when present, names a real JCL job component
  (either the full ``job:<name>`` id or the bare job name)

Invalid data raises TestCatalogError with a clear message naming the test
and the problem. Invalid data NEVER silently contaminates recommendations:
no invalid coverage entry is dropped, and no invalid id is ignored.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import TestCase

CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "sample_mainframe"
    / "tests"
    / "test_catalog.yaml"
)


class TestCatalogError(ValueError):
    """Raised when the test catalog fails validation at load time."""

    # Not a test class: keep pytest from trying to collect it.
    __test__ = False


def _job_component_id(job_value: str) -> str:
    """Normalise an execution.job value to a full component id.

    The catalog stores the bare JCL job name (e.g. ``WARRBTCH``); the
    Phase 1 graph uses ``job:WARRBTCH``. Both spellings are accepted.
    """
    return job_value if job_value.startswith("job:") else f"job:{job_value}"


def _validate_entry(
    entry: dict,
    index: int,
    seen_ids: set[str],
    valid_component_ids: set[str] | None,
    valid_job_ids: set[str] | None,
) -> TestCase:
    label = entry.get("id") or f"entry #{index}"
    try:
        case = TestCase(**entry)
    except ValidationError as exc:
        raise TestCatalogError(
            f"invalid test {label}: {exc.errors()[0]['msg']}"
        ) from exc

    if not case.id.strip():
        raise TestCatalogError(f"test entry #{index} has an empty id")
    if case.id in seen_ids:
        raise TestCatalogError(f"duplicate test id: {case.id}")
    seen_ids.add(case.id)
    if not case.name.strip():
        raise TestCatalogError(f"test {case.id} has an empty name")
    if not case.covers:
        raise TestCatalogError(f"test {case.id} has an empty covers list")

    if valid_component_ids is not None:
        unknown = [c for c in case.covers if c not in valid_component_ids]
        if unknown:
            raise TestCatalogError(
                f"test {case.id} covers unknown component(s) not present "
                f"in the Phase 1 graph: {', '.join(unknown)}"
            )

    job = (case.execution or {}).get("job")
    if job and valid_job_ids is not None:
        if _job_component_id(str(job)) not in valid_job_ids:
            raise TestCatalogError(
                f"test {case.id} execution.job is not a JCL job in the "
                f"Phase 1 graph: {job!r}"
            )
    return case


def load_catalog(
    path: Path | str = CATALOG_PATH,
    valid_component_ids: set[str] | None = None,
    valid_job_ids: set[str] | None = None,
) -> list[TestCase]:
    """Load and validate the YAML test catalog.

    ``valid_component_ids`` / ``valid_job_ids`` come from the frozen
    Phase 1 graph; passing None disables that validation (used only in
    focused unit tests that supply their own context).
    """
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        # A corrupt catalog must fail with the curated domain error,
        # never leak a raw parser exception through the API.
        raise TestCatalogError(
            f"test catalog is not valid YAML ({path}): {exc}"
        ) from exc
    if not isinstance(data, dict) or "tests" not in data:
        raise TestCatalogError(
            f"test catalog must be a mapping with a 'tests' list: {path}"
        )
    entries = data["tests"]
    if not isinstance(entries, list):
        raise TestCatalogError(f"'tests' must be a list: {path}")

    catalog: list[TestCase] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TestCatalogError(
                f"test entry #{index} is not a mapping"
            )
        catalog.append(
            _validate_entry(
                entry, index, seen_ids,
                valid_component_ids, valid_job_ids,
            )
        )
    return catalog
