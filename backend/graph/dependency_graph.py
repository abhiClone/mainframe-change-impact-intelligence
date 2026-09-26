"""Dependency graph (NetworkX MultiDiGraph-backed, swappable for Neo4j later).

Edge semantic:  source --relationship--> target  means
"source DEPENDS ON target", e.g.
    program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY

A MultiDiGraph is used so that parallel relationships between the same
pair (e.g. a program that both READS and WRITES a table) are kept as
separate edges, each with its own evidence.

Change-impact traversal walks REVERSE edges: the dependents
(predecessors) of a changed component are the impacted ones.
"""
from __future__ import annotations

import networkx as nx

from ..models.component import Component
from ..models.dependency import Dependency


class DependencyGraph:
    def __init__(self) -> None:
        self._g = nx.MultiDiGraph()

    # -- construction -------------------------------------------------
    def add_component(self, comp: Component) -> None:
        self._g.add_node(comp.id, name=comp.name, type=comp.type,
                         source_file=comp.source_file)

    def add_dependency(self, dep: Dependency) -> None:
        if dep.source not in self._g:
            self._g.add_node(dep.source)
        if dep.target not in self._g:
            self._g.add_node(dep.target)
        self._g.add_edge(dep.source, dep.target,
                         relationship=dep.relationship,
                         evidence=dep.evidence.to_dict())

    @classmethod
    def from_scan(cls, components: list[Component],
                  dependencies: list[Dependency]) -> "DependencyGraph":
        graph = cls()
        for c in components:
            graph.add_component(c)
        for d in dependencies:
            graph.add_dependency(d)
        return graph

    # -- queries -------------------------------------------------------
    def has(self, component_id: str) -> bool:
        return component_id in self._g

    def component(self, component_id: str) -> dict:
        attrs = dict(self._g.nodes[component_id])
        return {"id": component_id, **attrs}

    def components(self) -> list[dict]:
        return [self.component(n) for n in sorted(self._g.nodes)]

    def dependencies(self) -> list[dict]:
        return [
            {"source": u, "target": v, **attrs}
            for u, v, attrs in sorted(
                self._g.edges(data=True),
                key=lambda e: (e[0], e[1], e[2].get("relationship", "")))
        ]

    def _edge_rows(self, source: str, target: str) -> list[dict]:
        data = self._g.get_edge_data(source, target, default={})
        return [
            {"source": source, "target": target,
             "relationship": attrs["relationship"],
             "evidence": attrs["evidence"]}
            for _, attrs in sorted(data.items())
        ]

    def upstream(self, component_id: str) -> list[dict]:
        """Edges for what component_id directly depends on (successors)."""
        rows: list[dict] = []
        for v in sorted(self._g.successors(component_id)):
            rows.extend(self._edge_rows(component_id, v))
        return rows

    def downstream(self, component_id: str) -> list[dict]:
        """Edges for what directly depends on component_id (predecessors)."""
        rows: list[dict] = []
        for u in sorted(self._g.predecessors(component_id)):
            rows.extend(self._edge_rows(u, component_id))
        return rows

    def edges_between(self, source: str, target: str) -> list[dict]:
        """All parallel dependency edges source -> target, each with evidence."""
        return self._edge_rows(source, target)

    def reversed_view(self) -> nx.MultiDiGraph:
        """Impact-direction view: edge X->Y means 'X is impacted by Y'."""
        return self._g.reverse(copy=True)

    def counts(self) -> dict[str, int]:
        by_type: dict[str, int] = {}
        for _, attrs in self._g.nodes(data=True):
            t = attrs.get("type", "UNKNOWN")
            by_type[t] = by_type.get(t, 0) + 1
        by_type["DEPENDENCIES"] = self._g.number_of_edges()
        return by_type
