"""Phase 2B deterministic incident relevance engine.

Decides which historical incidents are relevant to a proposed change using
ONLY deterministic data: the changed component, the Phase 2A ImpactContext
(direct/transitive impact sets, dependency paths, evidence) and the
involved DB2 resources. No LLM, no embeddings, no scoring model.

Relevance reason precedence (strongest first) — see
docs/incident-relevance.md:

1. CHANGED_COMPONENT_MATCH      — incident linked to the changed component
2. DIRECT_IMPACT_MATCH          — incident linked to a directly impacted component
3. TRANSITIVE_IMPACT_MATCH      — incident linked to a transitively impacted component
4. INVOLVED_WRITE_RESOURCE_MATCH — incident linked to a table an impacted
                                   program WRITES (involved, not impacted)
5. INVOLVED_READ_RESOURCE_MATCH  — incident linked to a table an impacted
                                   program READS (involved, not impacted)

Incident severity never influences relevance: a critical incident with no
deterministic relationship to the change is excluded.

Read and write resource matches are independent: an incident linked to a
table that impacted programs both READ and WRITE receives BOTH reasons
(each with its own deterministic evidence); precedence decides the
primary reason and ordering only, never deletes a valid secondary reason.

Result ordering: incidents are ordered by primary-reason tier, then by
occurred_at (most recent first) as a deterministic tie-breaker. The same
(repository, dataset, changed component) always yields the same result,
whether or not an LLM is configured. This engine never claims a
probability of recurrence.
"""
from __future__ import annotations

from backend.intelligence.models import (
    DependencyPath,
    EvidenceRef,
    ImpactContext,
    InvolvedResource,
)

from .models import (
    HistoricalIncident,
    IncidentIntelligence,
    RelevanceReason,
    RelevanceReasonType,
    RelevantIncident,
    REASON_PRECEDENCE,
)

_REASON_RANK = {reason: rank for rank, reason in enumerate(REASON_PRECEDENCE)}


def _paths_to(impact_ctx: ImpactContext, component_id: str) -> list[DependencyPath]:
    """Deterministic Phase 1 paths from the change to a component."""
    return sorted(
        (p for p in impact_ctx.dependency_paths if p.impacted == component_id),
        key=lambda p: (len(p.path), [e.source for e in p.path]),
    )


def _paths_evidence(paths: list[DependencyPath]) -> list[EvidenceRef]:
    seen: set[tuple[str, int, str]] = set()
    out: list[EvidenceRef] = []
    for path in paths:
        for edge in path.path:
            ev = edge.evidence
            key = (ev.file, ev.line, ev.text)
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out


def _involved_resource(
    impact_ctx: ImpactContext, table_id: str, access: str
) -> InvolvedResource | None:
    for resource in impact_ctx.involved_resources:
        if resource.table == table_id and resource.access == access:
            return resource
    return None


def _reason_changed(incident: HistoricalIncident, changed: str) -> RelevanceReason:
    return RelevanceReason(
        reason=RelevanceReasonType.CHANGED_COMPONENT_MATCH,
        matched_component=changed,
        explanation=(
            f"{incident.id} is linked to {changed}. "
            f"{changed} is the changed component itself."
        ),
        supporting_paths=[],
        evidence=[],
    )


def _reason_impact(
    incident: HistoricalIncident,
    changed: str,
    component: str,
    kind: RelevanceReasonType,
    impact_ctx: ImpactContext,
) -> RelevanceReason:
    kind_word = "directly" if kind is RelevanceReasonType.DIRECT_IMPACT_MATCH else "transitively"
    paths = _paths_to(impact_ctx, component)
    return RelevanceReason(
        reason=kind,
        matched_component=component,
        explanation=(
            f"{incident.id} is linked to {component}. "
            f"{component} is {kind_word} impacted by the change to {changed}."
        ),
        supporting_paths=paths,
        evidence=_paths_evidence(paths),
    )


def _reason_involved(
    incident: HistoricalIncident,
    changed: str,
    table: str,
    kind: RelevanceReasonType,
    impact_ctx: ImpactContext,
) -> RelevanceReason:
    access = "write" if kind is RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH else "read"
    verb = "written" if access == "write" else "read"
    resource = _involved_resource(impact_ctx, table, access)
    programs = resource.used_by if resource else []
    # Dependency paths of the impacted programs that use the table.
    paths: list[DependencyPath] = []
    for program in programs:
        paths.extend(_paths_to(impact_ctx, program))
    paths = sorted(paths, key=lambda p: (p.impacted, len(p.path)))
    program_clause = (
        f" It is {verb} by {', '.join(programs)}, which "
        f"{'is' if len(programs) == 1 else 'are'} impacted by the change to {changed}."
        if programs
        else f" It is {verb} by a program impacted by the change to {changed}."
    )
    return RelevanceReason(
        reason=kind,
        matched_component=table,
        explanation=(
            f"{incident.id} is linked to {table}. "
            f"{table} is an involved DB2 resource (not reverse-impacted by the change)."
            + program_clause
        ),
        supporting_paths=paths,
        evidence=(list(resource.evidence) if resource else []),
    )


def _reasons_for(
    incident: HistoricalIncident, impact_ctx: ImpactContext
) -> list[RelevanceReason]:
    """All deterministic relevance reasons for one incident (may be empty)."""
    changed = impact_ctx.changed_component
    direct = set(impact_ctx.direct_impacts)
    transitive = set(impact_ctx.transitive_impacts)
    write_tables = set(impact_ctx.write_tables)
    read_tables = set(impact_ctx.read_tables)

    reasons: list[RelevanceReason] = []
    seen: set[tuple[RelevanceReasonType, str]] = set()

    def add(reason: RelevanceReason) -> None:
        key = (reason.reason, reason.matched_component)
        if key not in seen:
            seen.add(key)
            reasons.append(reason)

    for component in incident.linked_components:
        if component == changed:
            # The changed-component match subsumes any involved-resource
            # reading of the same id (e.g. a changed table that is also
            # listed as involved): one deterministic reason, no duplication.
            add(_reason_changed(incident, changed))
        elif component in direct:
            add(_reason_impact(incident, changed, component,
                              RelevanceReasonType.DIRECT_IMPACT_MATCH,
                              impact_ctx))
        elif component in transitive:
            add(_reason_impact(incident, changed, component,
                              RelevanceReasonType.TRANSITIVE_IMPACT_MATCH,
                              impact_ctx))
        else:
            # Involved-resource matches. Read and write are independent
            # checks (not elif): a table that impacted programs both READ
            # and WRITE yields BOTH reasons, each with its own evidence.
            # Precedence decides the primary reason and ordering only; it
            # never deletes a valid secondary reason.
            if component in write_tables:
                add(_reason_involved(incident, changed, component,
                                    RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH,
                                    impact_ctx))
            if component in read_tables:
                add(_reason_involved(incident, changed, component,
                                    RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH,
                                    impact_ctx))
        # else: no deterministic relationship — the incident is not relevant.

    reasons.sort(key=lambda r: _REASON_RANK[r.reason])
    return reasons


def build_incident_intelligence(
    impact_ctx: ImpactContext,
    incidents: list[HistoricalIncident],
) -> IncidentIntelligence:
    """Build deterministic historical-incident intelligence for a change.

    Pure function of (impact context, incident dataset): no LLM, no
    network, no randomness. Incidents with no deterministic relationship
    to the change are excluded regardless of severity.
    """
    relevant: list[RelevantIncident] = []
    for incident in incidents:
        reasons = _reasons_for(incident, impact_ctx)
        if not reasons:
            continue
        primary = reasons[0].reason  # reasons already in precedence order
        matched = sorted({r.matched_component for r in reasons})
        supporting_resources: list[InvolvedResource] = []
        seen_resources: set[tuple[str, str]] = set()
        for reason in reasons:
            if reason.reason in (
                RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH,
                RelevanceReasonType.INVOLVED_READ_RESOURCE_MATCH,
            ):
                access = (
                    "write"
                    if reason.reason
                    is RelevanceReasonType.INVOLVED_WRITE_RESOURCE_MATCH
                    else "read"
                )
                resource = _involved_resource(
                    impact_ctx, reason.matched_component, access
                )
                if resource is not None:
                    key = (resource.table, resource.access)
                    if key not in seen_resources:
                        seen_resources.add(key)
                        supporting_resources.append(resource)
        relevant.append(
            RelevantIncident(
                incident=incident,
                primary_reason=primary,
                relevance_reasons=reasons,
                matched_components=matched,
                supporting_resources=supporting_resources,
            )
        )

    # Deterministic ordering: primary-reason tier, then most recent first.
    relevant.sort(
        key=lambda r: (
            _REASON_RANK[r.primary_reason],
            # negative ordinal => most recent first, deterministic
            -r.incident.occurred_at.toordinal(),
            r.incident.id,
        )
    )

    primary_tier_counts: dict[str, int] = {
        reason.value: 0 for reason in REASON_PRECEDENCE}
    reason_counts: dict[str, int] = {
        reason.value: 0 for reason in REASON_PRECEDENCE}
    for item in relevant:
        primary_tier_counts[item.primary_reason.value] += 1
        for reason in item.relevance_reasons:
            reason_counts[reason.reason.value] += 1

    return IncidentIntelligence(
        changed_component=impact_ctx.changed_component,
        relevant_incidents=relevant,
        total_relevant_incidents=len(relevant),
        primary_tier_counts=primary_tier_counts,
        reason_counts=reason_counts,
    )
