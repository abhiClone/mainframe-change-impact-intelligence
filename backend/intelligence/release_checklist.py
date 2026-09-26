"""Deterministic release checklist built from impact context + signals.

Each item cites the rule that produced it in ``rule`` so a release
manager can trace every checklist line back to the evidence.
"""
from __future__ import annotations

from .models import ChecklistItem, ImpactContext, RiskSignal


def build_checklist(
    ctx: ImpactContext, signals: list[RiskSignal]
) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    signal_ids = {s.id for s in signals}

    def add(item_id: str, title: str, detail: str, rule: str,
            related: list[str]) -> None:
        items.append(ChecklistItem(
            id=item_id,
            title=title,
            detail=detail,
            rule=rule,
            related_components=sorted(set(related)),
        ))

    if ctx.affected_jobs:
        add("CHK-JOBS-IMPACTED",
            "Validate impacted batch jobs",
            f"Batch jobs {', '.join(ctx.affected_jobs)} execute impacted "
            f"programs. Re-run them in the test region and verify "
            f"scheduling, dependencies, and restart/recovery procedures.",
            "jobs_impacted",
            ctx.affected_jobs)

    # DB2 write rule: fires when an involved DB2 resource is written by a
    # program in the impact set (deterministic WRITES_TABLE edge).
    write_resources = [r for r in ctx.involved_resources if r.access == "write"]
    if write_resources:
        writers = sorted({p for r in write_resources for p in r.used_by})
        add("CHK-DB2-WRITE",
            "Validate DB2 write behavior and rollback scenarios",
            f"Programs in the impact set ({', '.join(writers)}) write to "
            f"{', '.join(ctx.write_tables)}. Verify write logic, commit "
            f"scope, and rollback scenarios before release.",
            "db2_write_involved",
            writers + ctx.write_tables)

    if ctx.read_tables:
        add("CHK-DB2-READ",
            "Validate DB2 read behavior against impacted tables",
            f"Impacted programs read from {', '.join(ctx.read_tables)}. "
            f"Confirm result sets and access paths are unchanged.",
            "db2_read_involved",
            ctx.read_tables)

    if "SHARED_COPYBOOK_CHANGE" in signal_ids:
        users = sorted(
            p for p in ctx.direct_impacts if p.startswith("program:"))
        add("CHK-SHARED-COPYBOOK",
            "Compile and regression-test all dependent programs",
            f"Copybook {ctx.changed_component} is shared by "
            f"{', '.join(users)}. Recompile every dependent program "
            f"against the new layout and run their regression suites.",
            "shared_copybook_change",
            [ctx.changed_component] + users)

    if ctx.affected_procs:
        add("CHK-PROCS-AFFECTED",
            "Validate PROC execution chain",
            f"JCL PROCs {', '.join(ctx.affected_procs)} invoke impacted "
            f"programs. Walk each PROC step and confirm step-level "
            f"parameters and dataset references still hold.",
            "procs_affected",
            ctx.affected_procs)

    if ctx.transitive_impacts:
        add("CHK-TRANSITIVE-IMPACT",
            "Trace transitive impact chains before sign-off",
            f"{len(ctx.transitive_impacts)} component(s) are only "
            f"indirectly impacted. Review every transitive chain in the "
            f"impact report before release sign-off.",
            "transitive_impact",
            ctx.transitive_impacts)

    if "HIGH_FAN_OUT" in signal_ids:
        add("CHK-HIGH-FAN-OUT",
            "Plan release window for high fan-out change",
            f"The change impacts {ctx.total_impacted_components} "
            f"components. Sequence the deployment and keep a rollback "
            f"plan for the full blast radius.",
            "high_fan_out",
            [ctx.changed_component])

    return items
