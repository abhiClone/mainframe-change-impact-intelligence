"""Build the Phase 2A ImpactContext from Phase 1 output.

The context is derived ONLY from:
  - ``ImpactAnalyzer.analyze(component_id)`` (frozen Phase 1),
  - graph component types via ``DependencyGraph.component(id)["type"]``, and
  - existing outgoing edges via ``DependencyGraph.upstream(program_id)``
    (for involved DB2 resources — reading Phase 1 edges, not traversing).

No impact-graph traversal, no LLM, no new parsing lives here.
"""
from __future__ import annotations

from pathlib import Path

from backend.graph.dependency_graph import DependencyGraph
from backend.graph.impact_analyzer import ImpactAnalyzer
from backend.parsers.repository_scanner import scan_repository

from .models import (
    DependencyPath,
    EvidenceRef,
    ImpactContext,
    InvolvedResource,
    PathEdge,
)

REPO_DIR = Path(__file__).resolve().parents[2] / "sample_mainframe"

_GRAPH: DependencyGraph | None = None
_ANALYZER: ImpactAnalyzer | None = None


def _shared() -> tuple[DependencyGraph, ImpactAnalyzer]:
    """Lazily-built Phase 1 graph + analyzer (built once per process)."""
    global _GRAPH, _ANALYZER
    if _ANALYZER is None:
        components, dependencies = scan_repository(REPO_DIR)
        _GRAPH = DependencyGraph.from_scan(components, dependencies)
        _ANALYZER = ImpactAnalyzer(_GRAPH)
    return _GRAPH, _ANALYZER


def _edge(step: dict) -> PathEdge:
    # In the impact view, a step {from: a, to: b} means the
    # dependency-graph edge b --relationship--> a (b depends on a).
    return PathEdge(
        source=step["to"],
        target=step["from"],
        relationship=step["relationship"],
        evidence=EvidenceRef(**step["evidence"]),
    )


def build_impact_context(component_id: str) -> ImpactContext:
    """Build the deterministic impact context for a component.

    Raises KeyError for an unknown component id (Phase 1 behavior).
    """
    graph, analyzer = _shared()
    if not graph.has(component_id):
        raise KeyError(f"unknown component: {component_id}")

    result = analyzer.analyze(component_id)
    direct: list[str] = result["direct_impact"]
    transitive: list[str] = result["transitive_impact"]

    dependency_paths = [
        DependencyPath(
            impacted=p["impacted"],
            path=[_edge(step) for step in p["path"]],
        )
        for p in result["dependency_paths"]
    ]

    # Evidence entries from analyze() already carry {source, target,
    # relationship, evidence} in the dependency-graph direction.
    evidence = [
        PathEdge(
            source=e["source"],
            target=e["target"],
            relationship=e["relationship"],
            evidence=EvidenceRef(**e["evidence"]),
        )
        for e in result["evidence"]
    ]

    impacted_ids = sorted(set(direct) | set(transitive))

    def _prefixed(prefix: str) -> list[str]:
        return sorted(i for i in impacted_ids if i.startswith(prefix))

    # Involved DB2 resources: outgoing READS_TABLE/WRITES_TABLE edges of the
    # impacted programs (plus the changed program's own edges when the
    # changed component is a program). This is Phase 2 context-enrichment
    # reading the existing Phase 1 graph — it does NOT alter impact
    # semantics: these tables do not depend on the change.
    involved_resources = _involved_resources(
        graph, impacted_ids, component_id,
        graph.component(component_id)["type"],
    )
    read_tables = sorted({r.table for r in involved_resources
                          if r.access == "read"})
    write_tables = sorted({r.table for r in involved_resources
                           if r.access == "write"})

    return ImpactContext(
        changed_component=component_id,
        changed_component_type=graph.component(component_id)["type"],
        direct_impacts=direct,
        transitive_impacts=transitive,
        dependency_paths=dependency_paths,
        relationships=sorted({e.relationship for e in evidence}),
        evidence=evidence,
        affected_programs=_prefixed("program:"),
        affected_copybooks=_prefixed("copybook:"),
        affected_jobs=_prefixed("job:"),
        affected_procs=_prefixed("proc:"),
        affected_tables=_prefixed("table:"),
        read_tables=read_tables,
        write_tables=write_tables,
        involved_resources=involved_resources,
        maximum_impact_depth=max((len(p.path) for p in dependency_paths),
                                 default=0),
        total_impacted_components=len(impacted_ids),
    )


def _involved_resources(
    graph: DependencyGraph,
    impacted_ids: list[str],
    changed_id: str,
    changed_type: str,
) -> list[InvolvedResource]:
    """Collect DB2 tables used by programs in the impact set.

    Reads the existing Phase 1 graph only (``upstream`` = outgoing
    dependency edges of a program). Never invents tables: a resource
    appears here only if a real READS_TABLE/WRITES_TABLE edge exists.
    """
    programs = sorted({i for i in impacted_ids if i.startswith("program:")})
    if changed_type == "COBOL_PROGRAM" and changed_id not in programs:
        programs.append(changed_id)
        programs.sort()

    by_key: dict[tuple[str, str], InvolvedResource] = {}
    for pid in programs:
        for edge in graph.upstream(pid):
            rel = edge["relationship"]
            if rel == "READS_TABLE":
                access = "read"
            elif rel == "WRITES_TABLE":
                access = "write"
            else:
                continue
            ev = EvidenceRef(**edge["evidence"])
            key = (edge["target"], access)
            res = by_key.get(key)
            if res is None:
                by_key[key] = InvolvedResource(
                    table=edge["target"], access=access,
                    used_by=[pid], evidence=[ev],
                )
            else:
                if pid not in res.used_by:
                    res.used_by.append(pid)
                    res.used_by.sort()
                if not any(e.file == ev.file and e.line == ev.line
                           and e.text == ev.text for e in res.evidence):
                    res.evidence.append(ev)
    return sorted(by_key.values(), key=lambda r: (r.table, r.access))
