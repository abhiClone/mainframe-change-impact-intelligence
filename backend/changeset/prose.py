"""Release-level prose generation for Phase 3A (M1 remediation).

The frozen Phase 2A engines produce per-root human-readable text. At
release level Phase 3A must NOT copy the first processed root's prose:
``[WARRCOPY, WARR002]`` and ``[WARR002, WARRCOPY]`` have to yield
semantically identical aggregate output. This module regenerates
release-level ``detail`` / ``explanation`` deterministically from the
MERGED structured fields (already sorted by the caller), so root input
order cannot leak into human-readable text.

Unknown rule/signal ids fall back to the sample text (the frozen rule
texts are constant per id, so the fallback only guards future rules).
"""
from __future__ import annotations


def _programs(ids: list[str]) -> list[str]:
    return [i for i in ids if i.startswith("program:")]


def _tables(ids: list[str]) -> list[str]:
    return [i for i in ids if i.startswith("table:")]


def _copybooks(ids: list[str]) -> list[str]:
    return [i for i in ids if i.startswith("copybook:")]


def _jobs(ids: list[str]) -> list[str]:
    return [i for i in ids if i.startswith("job:")]


def _procs(ids: list[str]) -> list[str]:
    return [i for i in ids if i.startswith("proc:")]


# -- checklist ---------------------------------------------------------

def release_checklist_title(item_id: str, fallback: str) -> str:
    return _CHECKLIST_TITLES.get(item_id, fallback)


def release_checklist_detail(
    item_id: str,
    related: list[str],
    total_impacted: int,
    fallback: str,
) -> str:
    """Build release-level checklist detail from merged related components."""
    if item_id == "CHK-JOBS-IMPACTED":
        jobs = _jobs(related)
        return (
            f"Batch jobs {', '.join(jobs)} execute impacted programs. "
            f"Re-run them in the test region and verify scheduling, "
            f"dependencies, and restart/recovery procedures."
        )
    if item_id == "CHK-DB2-WRITE":
        writers = _programs(related)
        tables = _tables(related)
        return (
            f"Programs in the impact set ({', '.join(writers)}) write to "
            f"{', '.join(tables)}. Verify write logic, commit scope, and "
            f"rollback scenarios before release."
        )
    if item_id == "CHK-DB2-READ":
        tables = _tables(related)
        return (
            f"Impacted programs read from {', '.join(tables)}. Confirm "
            f"result sets and access paths are unchanged."
        )
    if item_id == "CHK-SHARED-COPYBOOK":
        cbs = _copybooks(related)
        users = _programs(related)
        return (
            f"Copybook {', '.join(cbs)} is shared by {', '.join(users)}. "
            f"Recompile every dependent program against the new layout and "
            f"run their regression suites."
        )
    if item_id == "CHK-PROCS-AFFECTED":
        procs = _procs(related)
        return (
            f"JCL PROCs {', '.join(procs)} invoke impacted programs. Walk "
            f"each PROC step and confirm step-level parameters and dataset "
            f"references still hold."
        )
    if item_id == "CHK-TRANSITIVE-IMPACT":
        return (
            f"{len(related)} component(s) are only indirectly impacted. "
            f"Review every transitive chain in the impact report before "
            f"release sign-off."
        )
    if item_id == "CHK-HIGH-FAN-OUT":
        return (
            f"The release impacts {total_impacted} components. Sequence the "
            f"deployment and keep a rollback plan for the full blast radius."
        )
    return fallback


_CHECKLIST_TITLES = {
    "CHK-JOBS-IMPACTED": "Validate impacted batch jobs",
    "CHK-DB2-WRITE": "Validate DB2 write behavior and rollback scenarios",
    "CHK-DB2-READ": "Validate DB2 read behavior against impacted tables",
    "CHK-SHARED-COPYBOOK": "Compile and regression-test all dependent programs",
    "CHK-PROCS-AFFECTED": "Validate PROC execution chain",
    "CHK-TRANSITIVE-IMPACT": "Trace transitive impact chains before sign-off",
    "CHK-HIGH-FAN-OUT": "Plan release window for high fan-out change",
}


# -- risk signals ------------------------------------------------------

def release_signal_title(signal_id: str, fallback: str) -> str:
    return _SIGNAL_TITLES.get(signal_id, fallback)


def release_signal_explanation(
    signal_id: str,
    supporting: list[str],
    triggered_by: list[str],  # noqa: ARG001 - kept for signature stability
    change_roots: list[str],
    total_impacted: int,
    fallback: str,
) -> str:
    """Build release-level signal explanation from merged fields."""
    if signal_id == "SHARED_COPYBOOK_CHANGE":
        cbs = _copybooks(change_roots)
        users = _programs(supporting)
        return (
            f"Copybook {', '.join(cbs)} is used by {len(users)} programs "
            f"({', '.join(users)}), so a layout change can break record "
            f"mappings in all of them at once."
        )
    if signal_id == "MULTIPLE_PROGRAMS_IMPACTED":
        progs = _programs(supporting) or supporting
        return (
            f"{len(progs)} programs are impacted by this release "
            f"({', '.join(progs)}); each needs recompilation and regression "
            f"coverage."
        )
    if signal_id == "MULTIPLE_BATCH_JOBS_IMPACTED":
        jobs = _jobs(supporting) or supporting
        return (
            f"{len(jobs)} batch jobs ({', '.join(jobs)}) run the impacted "
            f"programs; batch scheduling and job recovery need review."
        )
    if signal_id == "DB2_WRITE_INVOLVED":
        writers = _programs(supporting)
        tables = _tables(supporting)
        return (
            f"Programs in the impact set ({', '.join(writers)}) write to "
            f"DB2 tables ({', '.join(tables)}). A defect here can corrupt "
            f"persistent data, so write paths need rollback validation."
        )
    if signal_id == "MULTIPLE_DB2_TABLES_IMPACTED":
        return (
            f"{len(supporting)} DB2 tables are in the impact set; "
            f"cross-table consistency checks are required."
        )
    if signal_id == "TRANSITIVE_IMPACT":
        return (
            f"{len(supporting)} component(s) are impacted only indirectly "
            f"(via other components). Chains must be traced before sign-off."
        )
    if signal_id == "HIGH_FAN_OUT":
        return (
            f"The release impacts {total_impacted} components; the release "
            f"window and rollback plan must account for this blast radius."
        )
    if signal_id == "MULTIPLE_EXECUTION_PATHS":
        return (
            f"{len(supporting)} impacted component(s) are reachable via "
            f"more than one dependency path ({', '.join(supporting)}); "
            f"test coverage must exercise each path."
        )
    return fallback


_SIGNAL_TITLES = {
    "SHARED_COPYBOOK_CHANGE": "Shared copybook change",
    "MULTIPLE_PROGRAMS_IMPACTED": "Multiple programs impacted",
    "MULTIPLE_BATCH_JOBS_IMPACTED": "Multiple batch jobs impacted",
    "DB2_WRITE_INVOLVED": "DB2 write involved",
    "MULTIPLE_DB2_TABLES_IMPACTED": "Multiple DB2 tables impacted",
    "TRANSITIVE_IMPACT": "Transitive impact present",
    "HIGH_FAN_OUT": "High impact fan-out",
    "MULTIPLE_EXECUTION_PATHS": "Multiple execution paths",
}
