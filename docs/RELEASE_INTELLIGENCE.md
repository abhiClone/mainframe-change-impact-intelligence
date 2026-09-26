# Release Intelligence

`GET /api/intelligence/{component_id}` returns the full release-intelligence bundle:
impact context, involved DB2 resources, test recommendations, risk signals, release
checklist, incident intelligence, and the explanation. Every section except the
explanation is produced by deterministic rules. See `docs/TEST_RECOMMENDATION.md`,
`docs/INCIDENT_INTELLIGENCE.md`, and `docs/AI_GROUNDING.md` for the deep dives.

## ImpactContext

`build_impact_context()` (`backend/intelligence/impact_context.py`) translates the
Phase 1 `analyze()` result into a typed, serializable Pydantic model: the changed
component, direct/transitive impacts classified by type (programs, jobs, procs,
tables, copybooks), dependency paths with evidence, and **involved resources**.

### Involved vs impacted — the critical distinction

`ImpactContext.involved_resources` lists DB2 tables **used by** the impacted programs,
derived deterministically from the programs' outgoing Phase 1 edges (`READS_TABLE` →
`access: read`, `WRITES_TABLE` → `access: write`), with the original file/line/text
evidence preserved. A table listed here does **not** depend on the change — it is
**involved, not impacted**. The UI states this explicitly ("involved in the change,
not impacted by it") and renders read/write access as distinct badges.

This is why `DB2_WRITE_INVOLVED` and `CHK-DB2-WRITE` can fire for a copybook change
whose reverse impact set contains no tables at all: the risk attaches to what the
impacted programs *do*, not to what the change *touches*.

## Risk signals

`detect_risk_signals(ctx)` (`backend/intelligence/risk_signals.py`) is a pure function
over the `ImpactContext`. Each `RiskSignal` carries `id`, `severity`, `title`,
`explanation`, `triggered_by`, `supporting_components`, and `evidence`.

**No failure probabilities are claimed anywhere.** Signals describe structural facts
about the impact set; severity reflects the *consequence class*, not a predicted
likelihood.

| Severity | Meaning |
|---|---|
| `high` | A defect here can corrupt persistent data or break production state. Review is mandatory before release. |
| `medium` | The blast radius requires extra verification (recompilation, regression suites, scheduling review, rollback planning). |
| `low` | Informational: indirect chains or multi-path reachability to trace before sign-off. |

### The 8 signals

| Signal | Severity | Trigger |
|---|---|---|
| `SHARED_COPYBOOK_CHANGE` | medium | Changed component is a copybook used by ≥ 2 programs |
| `MULTIPLE_PROGRAMS_IMPACTED` | medium | ≥ 2 affected programs |
| `MULTIPLE_BATCH_JOBS_IMPACTED` | medium | ≥ 2 affected batch jobs |
| `DB2_WRITE_INVOLVED` | **high** | Any involved DB2 resource has `access: write` — the only signal whose consequence class is persistent data corruption |
| `MULTIPLE_DB2_TABLES_IMPACTED` | medium | ≥ 2 affected tables |
| `TRANSITIVE_IMPACT` | low | Any transitive impact at all |
| `HIGH_FAN_OUT` | medium | ≥ 5 total impacted components |
| `MULTIPLE_EXECUTION_PATHS` | low | An impacted component reachable via ≥ 2 distinct dependency paths |

For `copybook:WARRCOPY`, 7 signals fire (all except `MULTIPLE_DB2_TABLES_IMPACTED`).

## Release checklist

`build_checklist(ctx, signals)` (`backend/intelligence/release_checklist.py`) emits
`ChecklistItem`s; each item's `rule` field cites the rule that produced it, so every
checklist line is traceable to evidence. For `copybook:WARRCOPY`:

| Item id | Rule citation | Fires when |
|---|---|---|
| `CHK-JOBS-IMPACTED` | `jobs_impacted` | affected jobs non-empty |
| `CHK-DB2-WRITE` | `db2_write_involved` | any involved resource with `access: write` |
| `CHK-DB2-READ` | `db2_read_involved` | any involved resource with `access: read` |
| `CHK-SHARED-COPYBOOK` | `shared_copybook_change` | `SHARED_COPYBOOK_CHANGE` fired |
| `CHK-PROCS-AFFECTED` | `procs_affected` | affected procs non-empty |
| `CHK-TRANSITIVE-IMPACT` | `transitive_impact` | transitive impacts non-empty |
| `CHK-HIGH-FAN-OUT` | `high_fan_out` | `HIGH_FAN_OUT` fired |

The checklist is advisory: it structures the release manager's review. Nothing in the
deterministic stack approves or blocks a release — that decision stays with the human.

## Incident intelligence (summary)

The bundle's `incident_intelligence` section lists the deterministically relevant
historical incidents (11 of 17 for WARRCOPY) with reasons, primary-tier vs all-reason
counts, and evidence. Full model: `docs/INCIDENT_INTELLIGENCE.md`.

## Explanation (summary)

The bundle's `explanation` section carries the four-section plain-language summary and
the authoritative `explanation_source` (`deterministic` or `ai`) that drives the UI
badge. Full contract: `docs/AI_GROUNDING.md`.
