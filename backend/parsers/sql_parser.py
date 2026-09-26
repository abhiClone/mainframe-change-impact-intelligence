"""DB2 schema parser (Phase 1: regex-based).

Extracts CREATE TABLE <name> definitions into DB2_TABLE components.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models.component import Component, make_component

_CREATE_TABLE_RE = re.compile(r"(?i)\bCREATE\s+TABLE\s+([A-Za-z][A-Za-z0-9_#]*)")


def parse_schema(path: Path, rel: str) -> list[Component]:
    """Parse a DDL file into DB2_TABLE components."""
    text = path.read_text(encoding="utf-8", errors="replace")
    tables: list[Component] = []
    seen: set[str] = set()
    for m in _CREATE_TABLE_RE.finditer(text):
        name = m.group(1).upper()
        if name not in seen:
            seen.add(name)
            tables.append(make_component("table", name, "DB2_TABLE", rel))
    return tables
