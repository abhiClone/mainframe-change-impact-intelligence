"""Normalized dependency model.

Every dependency carries mandatory source evidence: the file it was
discovered in, the 1-based line number, the source statement text, and
the dependency type. A dependency without evidence is not emitted.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    file: str   # repo-relative path, e.g. "cobol/WARR001.cbl"
    line: int   # 1-based line number in `file`
    text: str   # the stripped source statement

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "text": self.text}


@dataclass(frozen=True)
class Dependency:
    # Semantic direction: `source` DEPENDS ON `target`.
    # e.g. program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY
    source: str
    target: str
    relationship: str  # CALLS | USES_COPYBOOK | READS_TABLE | WRITES_TABLE
                       #          | EXECUTES_PROGRAM | USES_PROC
    evidence: Evidence

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "evidence": self.evidence.to_dict(),
        }
