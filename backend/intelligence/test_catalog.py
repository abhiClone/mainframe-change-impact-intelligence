"""Load the synthetic test catalog for test recommendation."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import TestCase

CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "sample_mainframe"
    / "tests"
    / "test_catalog.yaml"
)


def load_catalog() -> list[TestCase]:
    """Load and validate the YAML test catalog (path resolved from here)."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return [TestCase(**entry) for entry in data["tests"]]
