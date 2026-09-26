"""Change impact analyzer.

Given a changed component id, compute:
  - direct_impact:    components that directly depend on it (distance 1)
  - transitive_impact: components that depend on it via longer chains
  - dependency_paths: for each impacted component, the shortest chain(s)
                      of dependency edges explaining WHY it is impacted,
                      each edge linked to its source evidence.

Traversal runs on the reversed graph (impact direction): from the
changed node, follow "is depended on by" edges outward. Distances are
shortest-path distances in that impact view, so direct vs transitive
is unambiguous and cycles cannot inflate the result. Only shortest
paths are reported, so each impacted component is explained once
per distinct shortest chain.
"""
from __future__ import annotations

from collections import deque

from .dependency_graph import DependencyGraph


class ImpactAnalyzer:
    def __init__(self, graph: DependencyGraph) -> None:
        self.graph = graph
        self._impact_view = graph.reversed_view()

    def analyze(self, changed_id: str) -> dict:
        if not self.graph.has(changed_id):
            raise KeyError(f"unknown component: {changed_id}")

        # BFS in impact direction; dist[node] = shortest distance.
        dist: dict[str, int] = {changed_id: 0}
        queue: deque[str] = deque([changed_id])
        while queue:
            node = queue.popleft()
            for nxt in sorted(self._impact_view.successors(node)):
                if nxt not in dist:
                    dist[nxt] = dist[node] + 1
                    queue.append(nxt)

        direct = sorted(n for n, d in dist.items() if d == 1)
        transitive = sorted(n for n, d in dist.items() if d >= 2)

        paths: list[dict] = []
        evidence: list[dict] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for target in direct + transitive:
            for node_path in self._paths(changed_id, target, dist):
                for variant in self._expand_parallel(node_path):
                    steps: list[dict] = []
                    for step in variant:
                        steps.append(step)
                        key = (step["to"], step["from"], step["relationship"])
                        if key not in seen_edges:
                            seen_edges.add(key)
                            evidence.append({
                                "source": step["to"],
                                "target": step["from"],
                                "relationship": step["relationship"],
                                "evidence": step["evidence"],
                            })
                    paths.append({"impacted": target, "path": steps})

        return {
            "changed_component": changed_id,
            "direct_impact": direct,
            "transitive_impact": transitive,
            "dependency_paths": paths,
            "evidence": evidence,
        }

    def _paths(self, changed_id: str, target: str,
               dist: dict[str, int]) -> list[list[str]]:
        """All shortest impact-view node paths changed_id -> target."""
        results: list[list[str]] = []

        def dfs(node: str, path: list[str]) -> None:
            if node == target:
                results.append(list(path))
                return
            for nxt in sorted(self._impact_view.successors(node)):
                if dist.get(nxt) == dist[node] + 1 and nxt not in path:
                    path.append(nxt)
                    dfs(nxt, path)
                    path.pop()

        dfs(changed_id, [changed_id])
        return results

    def _expand_parallel(self, node_path: list[str]) -> list[list[dict]]:
        """Turn a node path into step variants, one per parallel edge.

        In the impact view, edge a->b means: in the dependency graph,
        b --relationship--> a (b depends on a). If several parallel
        dependency edges exist between b and a (e.g. READS_TABLE and
        WRITES_TABLE), each gets its own path variant so every
        relationship is explained with its own evidence.
        """
        variants: list[list[dict]] = [[]]
        for a, b in zip(node_path, node_path[1:]):
            edges = self.graph.edges_between(b, a)
            next_variants: list[list[dict]] = []
            for variant in variants:
                for e in edges:
                    next_variants.append(variant + [{
                        "from": a,
                        "to": b,
                        "relationship": e["relationship"],
                        "evidence": e["evidence"],
                    }])
            variants = next_variants
        return variants
