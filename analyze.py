#!/usr/bin/env python3
"""CLI proof step 1: repository summary.

Usage:
    python analyze.py [repo_path]

Prints component counts by type and the total dependency count.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.graph.dependency_graph import DependencyGraph
from backend.parsers.repository_scanner import scan_repository

TYPE_LABELS = {
    "COBOL_PROGRAM": "COBOL programs",
    "COPYBOOK": "Copybooks",
    "JCL_JOB": "JCL jobs",
    "JCL_PROC": "PROCs",
    "DB2_TABLE": "DB2 tables",
}


def main() -> int:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_mainframe")
    if not repo.is_dir():
        print(f"error: repository directory not found: {repo}", file=sys.stderr)
        return 1

    components, dependencies = scan_repository(repo)
    graph = DependencyGraph.from_scan(components, dependencies)
    counts = graph.counts()

    print("Repository Analysis")
    print()
    for ctype, label in TYPE_LABELS.items():
        print(f"{label}: {counts.get(ctype, 0)}")
    print()
    print(f"Dependencies discovered: {counts.get('DEPENDENCIES', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
