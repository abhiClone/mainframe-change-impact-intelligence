"""Normalized component model.

Every node in the dependency graph is a Component with a stable,
human-readable id of the form "<kind>:<NAME>", e.g. "program:WARR001".
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Component:
    id: str            # e.g. "program:WARR001"
    name: str          # e.g. "WARR001"
    type: str          # COBOL_PROGRAM | COPYBOOK | JCL_JOB | JCL_PROC | DB2_TABLE
    source_file: str   # repo-relative path, e.g. "cobol/WARR001.cbl"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "source_file": self.source_file,
        }


def make_component(kind: str, name: str, type_: str, source_file: str) -> Component:
    """Build a Component with the canonical "<kind>:<NAME>" id."""
    return Component(id=f"{kind}:{name}", name=name, type=type_,
                     source_file=source_file)
