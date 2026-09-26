"""Deterministic risk-signal detection over an ImpactContext.

Every signal carries an explicit severity, a human-readable explanation,
the real component ids that triggered it, and supporting components plus
real evidence. No heuristics beyond the documented rules.
"""
from __future__ import annotations

from collections import Counter

from .models import EvidenceRef, ImpactContext, RiskSignal


def _edge_evidence(ctx: ImpactContext,
                   relationship: str | None = None) -> list[EvidenceRef]:
    seen: set[tuple[str, int, str]] = set()
    out: list[EvidenceRef] = []
    for e in ctx.evidence:
        if relationship is not None and e.relationship != relationship:
            continue
        key = (e.evidence.file, e.evidence.line, e.evidence.text)
        if key not in seen:
            seen.add(key)
            out.append(e.evidence)
    return out


def detect_risk_signals(ctx: ImpactContext) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    changed = ctx.changed_component

    # SHARED_COPYBOOK_CHANGE: changed copybook used by >= 2 programs.
    if ctx.changed_component_type == "COPYBOOK":
        users = sorted(
            p for p in ctx.direct_impacts if p.startswith("program:")
        )
        if len(users) >= 2:
            evidence = [
                e.evidence
                for e in ctx.evidence
                if e.relationship == "USES_COPYBOOK"
                and e.target == changed
                and e.source in users
            ]
            signals.append(RiskSignal(
                id="SHARED_COPYBOOK_CHANGE",
                severity="medium",
                title="Shared copybook change",
                explanation=(
                    f"Copybook {changed} is used by {len(users)} programs, "
                    f"so a layout change can break record mappings in all "
                    f"of them at once."
                ),
                triggered_by=[changed],
                supporting_components=users,
                evidence=evidence,
            ))

    # MULTIPLE_PROGRAMS_IMPACTED: >= 2 impacted programs.
    if len(ctx.affected_programs) >= 2:
        signals.append(RiskSignal(
            id="MULTIPLE_PROGRAMS_IMPACTED",
            severity="medium",
            title="Multiple programs impacted",
            explanation=(
                f"{len(ctx.affected_programs)} programs are impacted by this "
                f"change; each needs recompilation and regression coverage."
            ),
            triggered_by=[changed],
            supporting_components=ctx.affected_programs,
            evidence=_edge_evidence(ctx),
        ))

    # MULTIPLE_BATCH_JOBS_IMPACTED: >= 2 impacted batch jobs.
    if len(ctx.affected_jobs) >= 2:
        signals.append(RiskSignal(
            id="MULTIPLE_BATCH_JOBS_IMPACTED",
            severity="medium",
            title="Multiple batch jobs impacted",
            explanation=(
                f"{len(ctx.affected_jobs)} batch jobs "
                f"({', '.join(ctx.affected_jobs)}) run the impacted "
                f"programs; batch scheduling and job recovery need review."
            ),
            triggered_by=[changed],
            supporting_components=ctx.affected_jobs,
            evidence=_edge_evidence(ctx),
        ))

    # DB2_WRITE_INVOLVED: an impacted program (or the changed program
    # itself) has a deterministic WRITES_TABLE edge. Derived from the
    # involved DB2 resources — never from guessed relationships.
    write_resources = [r for r in ctx.involved_resources if r.access == "write"]
    if write_resources:
        tables = sorted({r.table for r in write_resources})
        writers = sorted({p for r in write_resources for p in r.used_by})
        seen_ev: set[tuple[str, int, str]] = set()
        write_evidence: list[EvidenceRef] = []
        for r in write_resources:
            for e in r.evidence:
                key = (e.file, e.line, e.text)
                if key not in seen_ev:
                    seen_ev.add(key)
                    write_evidence.append(e)
        signals.append(RiskSignal(
            id="DB2_WRITE_INVOLVED",
            severity="high",
            title="DB2 write involved",
            explanation=(
                f"Programs in the impact set ({', '.join(writers)}) write "
                f"to DB2 tables ({', '.join(tables)}). A defect here can "
                f"corrupt persistent data, so write paths need rollback "
                f"validation."
            ),
            triggered_by=[changed],
            supporting_components=writers + tables,
            evidence=write_evidence,
        ))

    # MULTIPLE_DB2_TABLES_IMPACTED: >= 2 impacted tables.
    if len(ctx.affected_tables) >= 2:
        signals.append(RiskSignal(
            id="MULTIPLE_DB2_TABLES_IMPACTED",
            severity="medium",
            title="Multiple DB2 tables impacted",
            explanation=(
                f"{len(ctx.affected_tables)} DB2 tables are in the impact "
                f"set; cross-table consistency checks are required."
            ),
            triggered_by=[changed],
            supporting_components=ctx.affected_tables,
            evidence=_edge_evidence(ctx),
        ))

    # TRANSITIVE_IMPACT: any transitive impact at all.
    if ctx.transitive_impacts:
        signals.append(RiskSignal(
            id="TRANSITIVE_IMPACT",
            severity="low",
            title="Transitive impact present",
            explanation=(
                f"{len(ctx.transitive_impacts)} component(s) are impacted "
                f"only indirectly (via other components). Chains must be "
                f"traced before sign-off."
            ),
            triggered_by=[changed],
            supporting_components=ctx.transitive_impacts,
            evidence=_edge_evidence(ctx),
        ))

    # HIGH_FAN_OUT: total impacted components >= 5.
    if ctx.total_impacted_components >= 5:
        signals.append(RiskSignal(
            id="HIGH_FAN_OUT",
            severity="medium",
            title="High impact fan-out",
            explanation=(
                f"The change impacts {ctx.total_impacted_components} "
                f"components; the release window and rollback plan must "
                f"account for this blast radius."
            ),
            triggered_by=[changed],
            supporting_components=ctx.direct_impacts + ctx.transitive_impacts,
            evidence=_edge_evidence(ctx),
        ))

    # MULTIPLE_EXECUTION_PATHS: a component reachable via >= 2 paths.
    counts = Counter(p.impacted for p in ctx.dependency_paths)
    multi = sorted(c for c, n in counts.items() if n >= 2)
    if multi:
        signals.append(RiskSignal(
            id="MULTIPLE_EXECUTION_PATHS",
            severity="low",
            title="Multiple execution paths",
            explanation=(
                f"{len(multi)} impacted component(s) are reachable via more "
                f"than one dependency path ({', '.join(multi)}); test "
                f"coverage must exercise each path."
            ),
            triggered_by=[changed],
            supporting_components=multi,
            evidence=_edge_evidence(ctx),
        ))

    return signals
