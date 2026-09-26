"""Deterministic test recommendation.

Rule: a test is recommended iff the set of components it covers
intersects the impact set (changed component + direct + transitive
impacts). Impact level:
  - MUST_RUN   if any covered component is the changed component or a
               direct impact
  - SHOULD_RUN if every matched component is transitively impacted only
"""
from __future__ import annotations

from .models import DependencyPath, EvidenceRef, ImpactContext, RecommendedTest, TestCase


def _chain(path: list) -> str:
    # Dependency-direction presentation: "dependent --REL--> depended-upon".
    return " -> ".join(
        f"{e.source} --{e.relationship}--> {e.target}" for e in path
    )


def recommend_tests(
    ctx: ImpactContext, catalog: list[TestCase]
) -> list[RecommendedTest]:
    changed = ctx.changed_component
    direct = set(ctx.direct_impacts)
    transitive = set(ctx.transitive_impacts)
    impact_set = {changed} | direct | transitive

    def _priority(component_id: str) -> int:
        # Representative match for the rationale: direct first, then
        # transitive, then the changed component itself.
        if component_id in direct:
            return 0
        if component_id in transitive:
            return 1
        return 2

    recommendations: list[RecommendedTest] = []
    for test in catalog:
        matched = sorted(set(test.covers) & impact_set)
        if not matched:
            continue

        if set(matched) & ({changed} | direct):
            level = "MUST_RUN"
        else:
            level = "SHOULD_RUN"

        representative = min(matched, key=lambda c: (_priority(c), c))
        level_word = (
            "transitively impacted" if representative in transitive
            else "directly impacted"
        )

        paths: list[DependencyPath] = [
            p for p in ctx.dependency_paths if p.impacted in matched
        ]
        first_edge = paths[0].path[0] if paths else None

        if first_edge is not None:
            ev = first_edge.evidence
            rationale = (
                f"{test.id} '{test.name}' covers {representative}, "
                f"{level_word} by the change to {changed} via "
                f"{_chain(paths[0].path)} ({ev.file}:{ev.line})."
            )
        else:
            # Representative is the changed component itself (a test that
            # covers exactly the changed component); no impact chain to show.
            rationale = (
                f"{test.id} '{test.name}' covers {representative}, the "
                f"component changed, so it is {level_word}."
            )
        others = [c for c in matched if c != representative]
        if others:
            rationale += f" Also matches: {', '.join(others)}."

        seen: set[tuple[str, int, str]] = set()
        evidence: list[EvidenceRef] = []
        for p in paths:
            for e in p.path:
                key = (e.evidence.file, e.evidence.line, e.evidence.text)
                if key not in seen:
                    seen.add(key)
                    evidence.append(e.evidence)

        recommendations.append(
            RecommendedTest(
                test_id=test.id,
                test_name=test.name,
                test_type=test.type,
                matched_components=matched,
                impact_level=level,
                dependency_paths=paths,
                rationale=rationale,
                evidence=evidence,
            )
        )

    recommendations.sort(key=lambda r: (r.impact_level, r.test_id))
    return recommendations
