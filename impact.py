#!/usr/bin/env python3
"""CLI proof step 2: change impact for one component.

Usage:
    python impact.py <component-id> [repo_path]

Example:
    python impact.py copybook:WARRCOPY
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.graph.dependency_graph import DependencyGraph
from backend.graph.impact_analyzer import ImpactAnalyzer
from backend.parsers.repository_scanner import scan_repository


def _short(component_id: str) -> str:
    return component_id.split(":", 1)[1]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python impact.py <component-id> [repo_path]",
              file=sys.stderr)
        return 1
    changed_id = sys.argv[1]
    repo = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("sample_mainframe")
    if not repo.is_dir():
        print(f"error: repository directory not found: {repo}", file=sys.stderr)
        return 1

    components, dependencies = scan_repository(repo)
    graph = DependencyGraph.from_scan(components, dependencies)
    analyzer = ImpactAnalyzer(graph)

    try:
        result = analyzer.analyze(changed_id)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Changed component:\n{_short(changed_id)}\n")
    print("Direct impact:")
    if result["direct_impact"]:
        for c in result["direct_impact"]:
            print(f"- {_short(c)}")
    else:
        print("- (none)")
    print()
    print("Transitive impact:")
    if result["transitive_impact"]:
        for c in result["transitive_impact"]:
            print(f"- {_short(c)}")
    else:
        print("- (none)")
    print()
    print("Dependency paths:")
    for p in result["dependency_paths"]:
        chain = " <- ".join(s["from"] for s in p["path"])
        chain += f" <- {p['impacted']}"
        print(f"- {chain}")
    if not result["dependency_paths"]:
        print("- (none)")
    print()
    print("Evidence:")
    print()
    for e in result["evidence"]:
        ev = e["evidence"]
        print(f"{_short(e['source'])} -> {_short(e['target'])} "
              f"[{e['relationship']}]")
        print(f"{ev['file']}:{ev['line']}")
        print(f"{ev['text']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
