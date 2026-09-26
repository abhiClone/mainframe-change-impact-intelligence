"""Phase 3A aggregation service: multi-root deterministic analysis.

For every confirmed changed component the service reuses the frozen
engines with unchanged single-component semantics:

- Phase 1: ``ImpactAnalyzer`` (via ``build_impact_context_on``),
- Phase 2A: ``recommend_tests`` / ``detect_risk_signals`` / ``build_checklist``,
- Phase 2B: ``build_incident_intelligence``.

Phase 3A only AGGREGATES these per-root results (deduplication with
full root provenance). It never reimplements dependency, impact, test,
risk, checklist, or incident logic, and no LLM takes part in any
decision here.

Release semantics (fixed by the Phase 3A remediation):

- changed components = components explicitly changed in the release;
- impacted components = downstream impact EXCLUDING changed roots;
- a changed root impacted by another changed root is preserved as
  cross-impact (``ChangedComponent.also_impacted_by``), never dropped
  and never double-counted as downstream;
- release-level prose is regenerated from merged structured fields, so
  root input order cannot change it;
- every per-root aggregate reference carries its snapshot (base/head).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.graph.dependency_graph import DependencyGraph
from backend.graph.impact_analyzer import ImpactAnalyzer
from backend.intelligence.impact_context import build_impact_context_on
from backend.intelligence.incidents.models import (
    REASON_PRECEDENCE,
    IncidentIntelligence,
    RelevanceReasonType,
)
from backend.intelligence.incidents.relevance import build_incident_intelligence
from backend.intelligence.incidents.service import get_incidents
from backend.intelligence.models import (
    EvidenceRef,
    ImpactContext,
)
from backend.intelligence.release_checklist import build_checklist
from backend.intelligence.risk_signals import detect_risk_signals
from backend.intelligence.test_catalog import TestCatalogError, load_catalog
from backend.intelligence.test_selector import recommend_tests
from backend.models.component import Component
from backend.parsers.repository_scanner import scan_repository

from .mapping import FileComponentMapper, normalize_path
from .models import (
    AggregatedChecklistItem,
    AggregatedIncident,
    AggregatedResource,
    AggregatedSignal,
    AggregatedTest,
    ChangedComponent,
    ChangedFile,
    ChangeRootRef,
    ChangeSet,
    ChangeSetIntelligence,
    ChangeSetSummary,
    ImpactedComponentEntry,
    ImpactProvenance,
    MappedChange,
    PerChangeAnalysis,
    PerChangeIncidentReason,
    PerRootTest,
    Snapshot,
)
from .prose import (
    release_checklist_detail,
    release_checklist_title,
    release_signal_explanation,
    release_signal_title,
)
from .providers import ChangeSetProvider

_PRIORITY_ORDER = {"SHOULD_RUN": 0, "MUST_RUN": 1}
_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass
class RepositoryView:
    """One scanned Mainframe source tree with its frozen engines."""

    label: str  # "head" | "base"
    repo_root: Path
    components: list[Component]
    graph: DependencyGraph
    analyzer: ImpactAnalyzer
    mapper: FileComponentMapper


def build_view(repo_root: str | Path, label: str = "head") -> RepositoryView:
    """Scan a Mainframe source tree and wire the frozen Phase 1 engines."""
    root = Path(repo_root)
    components, dependencies = scan_repository(root)
    graph = DependencyGraph.from_scan(components, dependencies)
    return RepositoryView(
        label=label,
        repo_root=root,
        components=components,
        graph=graph,
        analyzer=ImpactAnalyzer(graph),
        # repo_root enables the deterministic parser fallback for files
        # whose scanner metadata is "unknown" (e.g. PROCs materialized
        # during JCL scanning); Phase 1 itself is untouched.
        mapper=FileComponentMapper(components, repo_root=root),
    )


@dataclass
class _RootPlan:
    """One confirmed changed component to analyse exactly once."""

    component_id: str
    snapshot: Snapshot
    originating_files: list[str] = field(default_factory=list)
    previous_component_ids: list[str] = field(default_factory=list)


_SAMPLE_MAINFRAME = Path(__file__).resolve().parents[2] / "sample_mainframe"
_DEFAULT_CATALOG = _SAMPLE_MAINFRAME / "tests" / "test_catalog.yaml"


def _catalog_for(view: RepositoryView):
    """Load the test catalog validated against a tree's component set.

    The catalog is release metadata authored for a specific tree:
    the tree's own ``tests/test_catalog.yaml`` wins; the sample demo tree
    falls back to the bundled catalog. A foreign tree never silently
    inherits the sample catalog — that would recommend sample tests
    for foreign components. Invalid catalog data fails clearly, never
    silently.
    """
    by_id = {c["id"]: c for c in view.graph.components()}
    valid_jobs = {
        cid for cid, comp in by_id.items() if comp["type"] == "JCL_JOB"
    }
    tree_catalog = Path(view.repo_root) / "tests" / "test_catalog.yaml"
    if tree_catalog.exists():
        path = tree_catalog
    elif Path(view.repo_root).resolve() == _SAMPLE_MAINFRAME.resolve():
        path = _DEFAULT_CATALOG
    else:
        raise RuntimeError(
            "no test catalog found for this tree: test recommendations are "
            "unavailable. Pass catalog=[] explicitly (CLI: --no-test-catalog) "
            "to analyze without test recommendations."
        )
    try:
        return load_catalog(
            path, valid_component_ids=set(by_id), valid_job_ids=valid_jobs
        )
    except TestCatalogError as exc:
        raise RuntimeError(f"invalid test catalog: {exc}") from exc


def _dedup_evidence(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    """Deduplicate evidence and order it deterministically.

    First-seen order depends on root input order, so the aggregate is
    sorted by (file, line, text) after dedup: identical input sets always
    produce identical evidence order.
    """
    seen: set[tuple[str, int, str]] = set()
    out: list[EvidenceRef] = []
    for ref in refs:
        key = (ref.file, ref.line, ref.text)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    out.sort(key=lambda r: (r.file, r.line, r.text))
    return out


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted(set(values))


def _root_refs(roots: dict[str, Snapshot]) -> list[ChangeRootRef]:
    """Deterministic ChangeRootRef list from a {root: snapshot} map."""
    return [
        ChangeRootRef(change_root=root, snapshot=roots[root])
        for root in sorted(roots)
    ]


class ChangeSetAnalyzer:
    """Deterministic multi-root change-set analysis over repository views."""

    def __init__(
        self,
        head_view: RepositoryView,
        base_view: RepositoryView | None = None,
        catalog: list | None = None,
    ) -> None:
        self._views = {"head": head_view}
        if base_view is not None:
            self._views["base"] = base_view
        # The test catalog is release-level metadata authored against the
        # head tree; validate once against head and reuse for base roots so
        # a base tree that predates a covered component cannot fail loudly
        # on data that is valid for the release under analysis. An explicit
        # catalog override is accepted for foreign trees (CLI:
        # --no-test-catalog, tests); the default path always validates and
        # fails clearly on bad or inapplicable data.
        if catalog is None:
            catalog = _catalog_for(head_view)
        self._catalog = catalog
        self._incidents = get_incidents()

    # -- public ------------------------------------------------------
    def analyze(
        self,
        change_set: ChangeSet,
        resolutions: dict[str, list[str]] | None = None,
        provider: ChangeSetProvider | None = None,
        explainer=None,
    ) -> ChangeSetIntelligence:
        """Run the full deterministic change-set analysis."""
        # M3: normalize the input set before any semantic work.
        normalized = self._normalize_inputs(change_set)
        resolutions = {
            normalize_path(k): list(dict.fromkeys(v))
            for k, v in (resolutions or {}).items()
        }
        mapped = self._map_files(normalized, resolutions, provider)

        plan = self._build_root_plan(mapped)
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]] = [
            self._analyze_root(item) for item in plan
        ]
        changed_ids = {item.component_id for item in plan}

        impacted = self._aggregate_impact(per_root, changed_ids)
        tests = self._aggregate_tests(per_root)
        resources = self._aggregate_resources(per_root)
        signals = self._aggregate_signals(per_root, len(impacted))
        checklist = self._aggregate_checklist(per_root, len(impacted))
        incidents = self._aggregate_incidents(per_root)

        direct_union = _sorted_unique(
            d
            for p, _ in per_root
            for d in p.impact.direct_impacts
            if d not in changed_ids
        )
        transitive_union = _sorted_unique(
            t
            for p, _ in per_root
            for t in p.impact.transitive_impacts
            if t not in changed_ids
        )
        changed = self._build_changed_components(plan, per_root)
        mixed = len({p.snapshot for p, _ in per_root}) > 1
        summary = self._build_summary(
            normalized, mapped, changed, impacted, tests, resources,
            signals, checklist, incidents,
            direct_union, transitive_union,
        )
        deterministic_summary = self._deterministic_summary(
            mapped, changed, per_root, impacted, tests, resources,
            signals, checklist, incidents, summary, mixed,
        )

        intelligence = ChangeSetIntelligence(
            change_set=normalized,
            mapped_changes=[m for m in mapped if m.mapping_status == "mapped"],
            ambiguous_changes=[m for m in mapped if m.mapping_status == "ambiguous"],
            unmapped_changes=[m for m in mapped if m.mapping_status == "unmapped"],
            unresolved_changes=[
                m for m in mapped if m.mapping_status == "requires_base_snapshot"
            ],
            per_change_analysis=[p for p, _ in per_root],
            changed_components=changed,
            unique_impacted_components=impacted,
            impacted_by_one_change=sorted(
                e.component_id for e in impacted if e.impacted_by_count == 1
            ),
            impacted_by_multiple_changes=sorted(
                e.component_id for e in impacted if e.impacted_by_count > 1
            ),
            involved_resources=resources,
            recommended_tests=tests,
            risk_signals=signals,
            release_checklist=checklist,
            relevant_incidents=incidents,
            mixed_snapshot_analysis=mixed,
            summary=summary,
            deterministic_summary=deterministic_summary,
        )

        from .ai import explain_change_set  # local import: keep service AI-free

        explanation = explain_change_set(intelligence, provider=explainer)
        intelligence.ai_explanation = explanation.model_dump(mode="json")
        return intelligence

    # -- input normalization (M3) ------------------------------------
    @staticmethod
    def _normalize_inputs(change_set: ChangeSet) -> ChangeSet:
        """Normalize the change set before semantic analysis.

        - Exact duplicates (same normalized path, old path, and status)
          are deduplicated to one file event.
        - The same normalized path with conflicting statuses is rejected
          with a clear validation error (it cannot be both, e.g.,
          modified and deleted).
        """
        seen: dict[tuple[str, str, str], ChangedFile] = {}
        for changed in change_set.files:
            path = normalize_path(changed.path)
            old = normalize_path(changed.old_path) if changed.old_path else ""
            key = (path, old, changed.status)
            if key in seen:
                continue
            for (p, o, s) in seen:
                if p == path and o == old and s != changed.status:
                    raise ValueError(
                        f"conflicting statuses for {path!r}: "
                        f"{s!r} vs {changed.status!r}"
                    )
            seen[key] = ChangedFile(path=path, status=changed.status,
                                    old_path=changed.old_path)
        return ChangeSet(
            files=list(seen.values()),
            source=change_set.source,
            base_ref=change_set.base_ref,
            head_ref=change_set.head_ref,
        )

    # -- mapping -----------------------------------------------------
    def _map_files(
        self,
        change_set: ChangeSet,
        resolutions: dict[str, list[str]],
        provider: ChangeSetProvider | None,
    ) -> list[MappedChange]:
        head_mapper = self._views["head"].mapper
        out: list[MappedChange] = []
        for changed in change_set.files:
            selected = resolutions.get(changed.path)
            if changed.status == "renamed":
                out.append(self._map_rename(changed, selected, provider))
                continue
            if changed.status == "deleted" and provider is not None:
                read_base = getattr(provider, "read_base_source_file", None)
                content = read_base(changed.path) if read_base else None
                if content is not None:
                    out.append(
                        head_mapper.map_deleted_base_file(changed, content)
                    )
                    continue
            out.append(head_mapper.map_file(changed, selected))
        return out

    def _map_rename(
        self,
        changed: ChangedFile,
        selected: list[str] | None,
        provider: ChangeSetProvider | None,
    ) -> MappedChange:
        """Map a rename as ONE file event with previous + current components.

        The old path is mapped against the base snapshot (its former
        dependents must not disappear from analysis) and the new path
        against the head snapshot. Frozen Phase 1 identity semantics are
        untouched; Phase 3 just consults both snapshots.
        """
        head_mapper = self._views["head"].mapper
        previous_ids: list[str] = []
        old_norm = normalize_path(changed.old_path) if changed.old_path else ""
        read_base = getattr(provider, "read_base_source_file", None)
        if old_norm and read_base is not None:
            content = read_base(old_norm)
            if content is not None:
                prev = head_mapper.map_deleted_base_file(
                    ChangedFile(path=old_norm, status="deleted"), content
                )
                if prev.mapping_status == "mapped":
                    previous_ids = prev.component_ids
        current = head_mapper.map_file(changed, selected)
        current_ids = (
            current.component_ids if current.mapping_status == "mapped" else []
        )
        union = sorted(set(previous_ids) | set(current_ids))
        if not union:
            # Neither side resolved: keep the head mapping outcome (which
            # carries the precise unmapped/ambiguous/requires_base_snapshot
            # status) but preserve the rename shape.
            note = current.note or "Rename could not be resolved."
            return MappedChange(
                file=current.file,
                mapping_status=current.mapping_status,
                candidate_components=current.candidate_components,
                selected_component_ids=current.selected_component_ids,
                previous_component_ids=previous_ids,
                current_component_ids=current_ids,
                snapshot="head",
                note=f"{note} Rename status preserved.",
            )
        return MappedChange(
            file=current.file,
            mapping_status="mapped",
            component_ids=union,
            candidate_components=current.candidate_components,
            selected_component_ids=current.selected_component_ids,
            previous_component_ids=previous_ids,
            current_component_ids=current_ids,
            # The file exists at head; per-component snapshots are tracked
            # in the root plan (previous ids -> base).
            snapshot="head",
            note=(
                "Rename mapped against both snapshots: "
                f"previous={previous_ids or []} (base), "
                f"current={current_ids or []} (head)."
            ),
        )

    def _build_root_plan(self, mapped: list[MappedChange]) -> list[_RootPlan]:
        """One analysis plan entry per unique changed component.

        Multiple input files resolving to the same component analyse it
        exactly once; every originating file path is preserved on the
        plan entry. Rename previous identities analyse on base, current
        identities on head; an identity present on both sides is
        analysed once (head).
        """
        by_id: dict[str, _RootPlan] = {}
        for m in mapped:
            if m.mapping_status != "mapped":
                continue
            prev = set(m.previous_component_ids)
            curr = set(m.current_component_ids)
            is_rename = bool(prev or curr)
            for comp_id in m.component_ids:
                if is_rename:
                    snapshot: Snapshot = (
                        "base"
                        if comp_id in prev and comp_id not in curr
                        else "head"
                    )
                else:
                    # Deleted files carry snapshot="base" from their own
                    # mapping; everything else analyses on head.
                    snapshot = m.snapshot
                entry = by_id.setdefault(
                    comp_id,
                    _RootPlan(
                        component_id=comp_id,
                        snapshot=snapshot,
                        previous_component_ids=sorted(prev - {comp_id}),
                    ),
                )
                # A head occurrence wins over a base-only occurrence.
                if snapshot == "head":
                    entry.snapshot = "head"
                entry.originating_files.append(m.file.path)
        plans = sorted(by_id.values(), key=lambda p: p.component_id)
        for p in plans:
            p.originating_files = sorted(set(p.originating_files))
        return plans

    # -- per-root analysis (frozen engines, unchanged semantics) ------
    def _analyze_root(
        self, plan: _RootPlan
    ) -> tuple[PerChangeAnalysis, IncidentIntelligence]:
        """Analyse one confirmed changed component on its snapshot's view."""
        view = self._views.get(plan.snapshot, self._views["head"])
        ctx: ImpactContext = build_impact_context_on(
            view.graph, view.analyzer, plan.component_id
        )
        tests = recommend_tests(ctx, self._catalog)
        signals = detect_risk_signals(ctx)
        checklist = build_checklist(ctx, signals)
        incident_intel = build_incident_intelligence(ctx, self._incidents)
        source_file = view.graph.component(plan.component_id).get(
            "source_file", ""
        )
        per_change = PerChangeAnalysis(
            component_id=plan.component_id,
            source_file=source_file,
            snapshot=plan.snapshot,
            impact=ctx,
            recommended_tests=tests,
            risk_signals=signals,
            release_checklist=checklist,
            incident_intelligence=incident_intel.model_dump(mode="json"),
        )
        return per_change, incident_intel

    def _build_changed_components(
        self,
        plan: list[_RootPlan],
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
    ) -> list[ChangedComponent]:
        """Changed components with cross-impact (M2) preserved."""
        impacts = {
            p.component_id: set(p.impact.direct_impacts)
            | set(p.impact.transitive_impacts)
            for p, _ in per_root
        }
        snapshots = {p.component_id: p.snapshot for p, _ in per_root}
        changed: list[ChangedComponent] = []
        for item in plan:
            cross = _root_refs(
                {
                    other: snapshots[other]
                    for other in sorted(impacts)
                    if other != item.component_id
                    and item.component_id in impacts[other]
                }
            )
            changed.append(
                ChangedComponent(
                    component_id=item.component_id,
                    originating_files=item.originating_files,
                    snapshot=item.snapshot,
                    previous_component_ids=item.previous_component_ids,
                    also_impacted_by=cross,
                )
            )
        return changed

    # -- aggregation -------------------------------------------------
    @staticmethod
    def _aggregate_impact(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
        changed_ids: set[str],
    ) -> list[ImpactedComponentEntry]:
        """Downstream impacted components EXCLUDING changed roots (M2)."""
        by_component: dict[str, dict] = {}
        for per_change, _ in per_root:
            root = per_change.component_id
            snapshot = per_change.snapshot
            ctx = per_change.impact
            impacted = (
                set(ctx.direct_impacts) | set(ctx.transitive_impacts)
            ) - changed_ids
            paths_by_impacted: dict[str, list] = {}
            for path in ctx.dependency_paths:
                paths_by_impacted.setdefault(path.impacted, []).append(path)
            for comp in impacted:
                entry = by_component.setdefault(
                    comp, {"roots": {}, "per_root": []}
                )
                entry["roots"][root] = snapshot
                paths = paths_by_impacted.get(comp, [])
                depth = min((len(p.path) for p in paths), default=0)
                entry["per_root"].append(
                    ImpactProvenance(
                        change_root=root,
                        snapshot=snapshot,
                        depth=depth,
                        dependency_paths=paths,
                    )
                )
        entries: list[ImpactedComponentEntry] = []
        for comp in sorted(by_component):
            roots: dict[str, Snapshot] = by_component[comp]["roots"]
            per_r = sorted(
                by_component[comp]["per_root"], key=lambda d: d.change_root
            )
            entries.append(
                ImpactedComponentEntry(
                    component_id=comp,
                    impacted_by=sorted(roots),
                    impacted_by_count=len(roots),
                    per_root=per_r,
                )
            )
        return entries

    @staticmethod
    def _aggregate_tests(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
    ) -> list[AggregatedTest]:
        by_id: dict[str, dict] = {}
        for per_change, _ in per_root:
            root = per_change.component_id
            for test in per_change.recommended_tests:
                bucket = by_id.setdefault(
                    test.test_id, {"sample": test, "roots": {}}
                )
                bucket["roots"][root] = (per_change.snapshot, test)
        aggregated: list[AggregatedTest] = []
        for test_id in sorted(by_id):
            sample = by_id[test_id]["sample"]
            roots: dict[str, tuple[Snapshot, object]] = by_id[test_id]["roots"]
            ordered = sorted(roots)
            # Strongest deterministic priority wins (MUST_RUN > SHOULD_RUN);
            # ties resolve to the smallest root id — fully deterministic.
            best_root = min(
                ordered,
                key=lambda r: (-_PRIORITY_ORDER[roots[r][1].impact_level], r),
            )
            best_test = roots[best_root][1]
            per_root_tests = [
                PerRootTest(
                    change_root=r,
                    snapshot=roots[r][0],
                    impact_level=roots[r][1].impact_level,
                    rationale=roots[r][1].rationale,
                    matched_components=sorted(roots[r][1].matched_components),
                )
                for r in ordered
            ]
            aggregated.append(
                AggregatedTest(
                    test_id=test_id,
                    test_name=sample.test_name,
                    test_type=sample.test_type,
                    impact_level=best_test.impact_level,
                    rationale=best_test.rationale,
                    evidence=_dedup_evidence(
                        [e for r in ordered for e in roots[r][1].evidence]
                    ),
                    recommended_because_of=_root_refs(
                        {r: roots[r][0] for r in ordered}
                    ),
                    per_root=per_root_tests,
                )
            )
        return aggregated

    @staticmethod
    def _aggregate_resources(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
    ) -> list[AggregatedResource]:
        by_key: dict[tuple[str, str], dict] = {}
        for per_change, _ in per_root:
            root = per_change.component_id
            for res in per_change.impact.involved_resources:
                bucket = by_key.setdefault(
                    (res.table, res.access),
                    {"roots": {}, "used_by": set(), "evidence": []},
                )
                bucket["roots"][root] = per_change.snapshot
                bucket["used_by"].update(res.used_by)
                bucket["evidence"].extend(res.evidence)
        return [
            AggregatedResource(
                table=table,
                access=access,
                used_by=sorted(bucket["used_by"]),
                associated_change_roots=_root_refs(bucket["roots"]),
                evidence=_dedup_evidence(bucket["evidence"]),
            )
            for (table, access), bucket in sorted(by_key.items())
        ]

    @staticmethod
    def _aggregate_signals(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
        total_impacted: int,
    ) -> list[AggregatedSignal]:
        by_id: dict[str, dict] = {}
        for per_change, _ in per_root:
            root = per_change.component_id
            for signal in per_change.risk_signals:
                bucket = by_id.setdefault(
                    signal.id,
                    {
                        "signal": signal,
                        "roots": {},
                        "triggered_by": set(),
                        "supporting": set(),
                        "evidence": [],
                        "severity_rank": -1,
                        "severity": signal.severity,
                    },
                )
                bucket["roots"][root] = per_change.snapshot
                bucket["triggered_by"].update(signal.triggered_by)
                bucket["supporting"].update(signal.supporting_components)
                bucket["evidence"].extend(signal.evidence)
                # Documented Phase 3 rule: keep the strongest deterministic
                # severity the rule produced across roots. Severity is never
                # escalated merely because several changes triggered it —
                # this only preserves the rule's own strongest verdict.
                rank = _SEVERITY_ORDER.get(signal.severity, -1)
                if rank > bucket["severity_rank"]:
                    bucket["severity_rank"] = rank
                    bucket["severity"] = signal.severity
        aggregated: list[AggregatedSignal] = []
        for sid in sorted(by_id):
            b = by_id[sid]
            s = b["signal"]
            roots: dict[str, Snapshot] = b["roots"]
            supporting = sorted(b["supporting"])
            triggered = sorted(b["triggered_by"])
            # M1: release prose is regenerated from the MERGED structured
            # fields — never inherited from the first processed root.
            aggregated.append(
                AggregatedSignal(
                    id=sid,
                    severity=b["severity"],
                    title=release_signal_title(sid, s.title),
                    explanation=release_signal_explanation(
                        sid, supporting, triggered, sorted(roots),
                        total_impacted, s.explanation,
                    ),
                    triggered_by=triggered,
                    supporting_components=supporting,
                    change_roots=_root_refs(roots),
                    evidence=_dedup_evidence(b["evidence"]),
                )
            )
        return aggregated

    @staticmethod
    def _aggregate_checklist(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
        total_impacted: int,
    ) -> list[AggregatedChecklistItem]:
        by_id: dict[str, dict] = {}
        for per_change, _ in per_root:
            root = per_change.component_id
            for item in per_change.release_checklist:
                bucket = by_id.setdefault(
                    item.id,
                    {
                        "item": item,
                        "roots": {},
                        "related": set(),
                    },
                )
                bucket["roots"][root] = per_change.snapshot
                bucket["related"].update(item.related_components)
        aggregated: list[AggregatedChecklistItem] = []
        for iid in sorted(by_id):
            b = by_id[iid]
            item = b["item"]
            related = sorted(b["related"])
            roots: dict[str, Snapshot] = b["roots"]
            # M1: release detail regenerated from merged fields.
            aggregated.append(
                AggregatedChecklistItem(
                    id=iid,
                    title=release_checklist_title(iid, item.title),
                    detail=release_checklist_detail(
                        iid, related, total_impacted, item.detail
                    ),
                    rule=item.rule,
                    related_components=related,
                    applicable_change_roots=_root_refs(roots),
                )
            )
        return aggregated

    @staticmethod
    def _aggregate_incidents(
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
    ) -> list[AggregatedIncident]:
        by_id: dict[str, dict] = {}
        for per_change, intel in per_root:
            for relevant in intel.relevant_incidents:
                bucket = by_id.setdefault(
                    relevant.incident.id,
                    {"relevant": relevant, "per_change": []},
                )
                bucket["per_change"].append(
                    PerChangeIncidentReason(
                        change_root=intel.changed_component,
                        snapshot=per_change.snapshot,
                        primary_reason=relevant.primary_reason,
                        relevance_reasons=list(relevant.relevance_reasons),
                        matched_components=list(relevant.matched_components),
                    )
                )
        aggregated: list[AggregatedIncident] = []
        for iid in sorted(by_id):
            b = by_id[iid]
            per_change = sorted(b["per_change"], key=lambda p: p.change_root)
            # Strongest deterministic reason across all change roots, using
            # the existing REASON_PRECEDENCE (enum order).
            strongest = min(
                (
                    reason.reason
                    for pc in per_change
                    for reason in pc.relevance_reasons
                ),
                key=lambda reason: REASON_PRECEDENCE.index(reason),
            )
            aggregated.append(
                AggregatedIncident(
                    incident=b["relevant"].incident,
                    relevant_to_changes=_root_refs(
                        {p.change_root: p.snapshot for p in per_change}
                    ),
                    per_change=per_change,
                    primary_reason=strongest,
                )
            )
        return aggregated

    # -- summary -----------------------------------------------------
    @staticmethod
    def _build_summary(
        change_set: ChangeSet,
        mapped: list[MappedChange],
        changed: list[ChangedComponent],
        impacted: list[ImpactedComponentEntry],
        tests: list[AggregatedTest],
        resources: list[AggregatedResource],
        signals: list[AggregatedSignal],
        checklist: list[AggregatedChecklistItem],
        incidents: list[AggregatedIncident],
        direct_union: list[str],
        transitive_union: list[str],
    ) -> ChangeSetSummary:
        return ChangeSetSummary(
            changed_files=len(change_set.files),
            changed_components=len(changed),
            cross_impacted_changed_components=sum(
                1 for c in changed if c.also_impacted_by
            ),
            ambiguous_files=sum(1 for m in mapped if m.mapping_status == "ambiguous"),
            unmapped_files=sum(1 for m in mapped if m.mapping_status == "unmapped"),
            unresolved_files=sum(
                1 for m in mapped if m.mapping_status == "requires_base_snapshot"
            ),
            direct_impact_union=len(direct_union),
            transitive_impact_union=len(transitive_union),
            unique_impacted_components=len(impacted),
            overlap_impacted_components=sum(
                1 for e in impacted if e.impacted_by_count > 1
            ),
            unique_recommended_tests=len(tests),
            must_run_tests=sum(1 for t in tests if t.impact_level == "MUST_RUN"),
            should_run_tests=sum(1 for t in tests if t.impact_level == "SHOULD_RUN"),
            involved_db2_reads=sum(1 for r in resources if r.access == "read"),
            involved_db2_writes=sum(1 for r in resources if r.access == "write"),
            risk_signals=len(signals),
            checklist_items=len(checklist),
            relevant_incidents=len(incidents),
        )

    @staticmethod
    def _deterministic_summary(
        mapped: list[MappedChange],
        changed: list[ChangedComponent],
        per_root: list[tuple[PerChangeAnalysis, IncidentIntelligence]],
        impacted: list[ImpactedComponentEntry],
        tests: list[AggregatedTest],
        resources: list[AggregatedResource],
        signals: list[AggregatedSignal],
        checklist: list[AggregatedChecklistItem],
        incidents: list[AggregatedIncident],
        summary: ChangeSetSummary,
        mixed: bool,
    ) -> str:
        roots = sorted(c.component_id for c in changed)
        lines = [
            f"Change set: {summary.changed_files} file(s) -> "
            f"{summary.changed_components} changed component(s)"
            + (f" ({', '.join(roots)})" if roots else "")
            + ".",
            f"Mapping: {summary.changed_components} mapped, "
            f"{summary.ambiguous_files} ambiguous, "
            f"{summary.unmapped_files} unmapped, "
            f"{summary.unresolved_files} unresolved (needs base snapshot).",
            f"Downstream impact (excluding the changed components "
            f"themselves): {summary.unique_impacted_components} unique "
            f"component(s) ({summary.direct_impact_union} direct union, "
            f"{summary.transitive_impact_union} transitive union); "
            f"{summary.overlap_impacted_components} impacted by multiple changes.",
        ]
        cross = sorted(
            c.component_id for c in changed if c.also_impacted_by
        )
        if cross:
            detail = "; ".join(
                f"{c.component_id} also impacted by "
                + ", ".join(r.change_root for r in c.also_impacted_by)
                for c in changed
                if c.also_impacted_by
            )
            lines.append(
                f"Cross-impact between changed components: {detail}."
            )
        if mixed:
            lines.append(
                "Mixed snapshot analysis: results combine evidence from "
                "the base snapshot (deleted / renamed-away components) and "
                "the head snapshot; per-root provenance records which."
            )
        lines.extend(
            [
                f"Tests: {summary.unique_recommended_tests} recommended "
                f"({summary.must_run_tests} MUST_RUN, {summary.should_run_tests} "
                f"SHOULD_RUN).",
                f"DB2 resources involved: {summary.involved_db2_reads} read, "
                f"{summary.involved_db2_writes} write (involved \u2260 impacted).",
                f"Risk signals: {summary.risk_signals}; "
                f"checklist items: {summary.checklist_items}; "
                f"relevant historical incidents: {summary.relevant_incidents}.",
            ]
        )
        overlap = sorted(
            e.component_id for e in impacted if e.impacted_by_count > 1
        )
        if overlap:
            lines.append(
                "Overlap (impacted by several changes): "
                + ", ".join(overlap)
                + "."
            )
        return " ".join(lines)
