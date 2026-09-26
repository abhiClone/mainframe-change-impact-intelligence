# Phase 2A Risk Signal Model

`detect_risk_signals(ctx)` in `backend/intelligence/risk_signals.py` is a
pure function over an `ImpactContext`. Each signal (`RiskSignal` in
`backend/intelligence/models.py`) carries: `id`, `severity`, `title`,
`explanation`, `triggered_by` (the component ids that tripped the rule),
`supporting_components` (the components the explanation refers to), and
`evidence` (real `EvidenceRef` entries from the Phase 1 scan).

**No failure probabilities are claimed anywhere.** Signals describe
structural facts about the impact set (fan-out, shared copybooks, DB2 write
paths) and their severity reflects the *consequence class*, not a predicted
likelihood. Nothing in this model says "this change has an X% chance of
failing."

## Severity scale

| Severity | Meaning |
|---|---|
| `high` | A defect here can corrupt persistent data or break production state. Review is mandatory before release. |
| `medium` | The change's blast radius requires extra verification (recompilation, regression suites, scheduling review, rollback planning). |
| `low` | Informational: indirect chains or multi-path reachability that must be traced before sign-off, but that do not widen the blast radius by themselves. |

## Every implemented signal

### SHARED_COPYBOOK_CHANGE — medium
- **Trigger:** the changed component's type is `COPYBOOK` **and** ≥ 2
  programs are in the direct impact set (i.e. ≥ 2 programs `USES_COPYBOOK`
  the changed copybook).
- **Example (change to `copybook:WARRCOPY`):** fires with
  `supporting_components = [program:WARR001, program:WARR002]` and the two
  `USES_COPYBOOK` evidence refs.
- **Explanation:** "Copybook copybook:WARRCOPY is used by 2 programs, so a
  layout change can break record mappings in all of them at once."

### MULTIPLE_PROGRAMS_IMPACTED — medium
- **Trigger:** `len(affected_programs) >= 2`.
- **Example:** fires for `copybook:WARRCOPY` (2 affected programs);
  evidence = all impact-path edge evidence.
- **Explanation:** "2 programs are impacted by this change; each needs
  recompilation and regression coverage."

### MULTIPLE_BATCH_JOBS_IMPACTED — medium
- **Trigger:** `len(affected_jobs) >= 2`.
- **Example:** fires for `copybook:WARRCOPY` with supporting components
  `job:DAILY01`, `job:WARRBTCH` ("batch jobs ... run the impacted programs;
  batch scheduling and job recovery need review").

### DB2_WRITE_INVOLVED — high
- **Trigger:** any involved DB2 resource (see below) has `access: write` —
  i.e. an impacted program (or the changed program itself) holds an
  existing Phase 1 `WRITES_TABLE` edge to a table.
- **Example:** fires for `copybook:WARRCOPY` (impacted programs `WARR001`
  and `WARR002` write `table:WARRANTY`; `WARR002` also writes
  `table:CLAIM_HISTORY`), with writers and tables listed as supporting
  components and only the `WRITES_TABLE` evidence attached. It does *not*
  fire for `copybook:UNUSED` (no impacted programs, hence no involved
  resources).
- **Explanation:** "Programs in the impact set (...) write to DB2 tables
  (...). A defect here can corrupt persistent data, so write paths need
  rollback validation." — the only `high` severity, because it is the only
  signal whose consequence class is persistent data corruption.

### Involved vs impacted DB2 resources

`ImpactContext.involved_resources` lists DB2 tables **used by** the impacted
programs, derived deterministically from the programs' outgoing Phase 1
edges (`READS_TABLE` → `access: read`, `WRITES_TABLE` → `access: write`)
with the original file/line/text evidence preserved. A table listed here
does **not** depend on the change — it is involved, not impacted. This is
why `DB2_WRITE_INVOLVED` and the `CHK-DB2-WRITE` checklist item can fire
for a copybook change whose reverse impact set contains no tables at all:
the risk attaches to what the impacted programs *do*, not to what the
change *touches*.

### MULTIPLE_DB2_TABLES_IMPACTED — medium
- **Trigger:** `len(affected_tables) >= 2`.
- **Explanation:** "... DB2 tables are in the impact set; cross-table
  consistency checks are required."

### TRANSITIVE_IMPACT — low
- **Trigger:** any transitive impact at all (`transitive_impacts` non-empty).
- **Example:** fires for `copybook:WARRCOPY` (3 transitively impacted
  components: `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`).
- **Explanation:** "... component(s) are impacted only indirectly (via other
  components). Chains must be traced before sign-off."

### HIGH_FAN_OUT — medium
- **Trigger:** `total_impacted_components >= 5` (threshold, not a heuristic
  score).
- **Example:** fires for `copybook:WARRCOPY` (exactly 5 impacted
  components): "The change impacts 5 components; the release window and
  rollback plan must account for this blast radius."

### MULTIPLE_EXECUTION_PATHS — low
- **Trigger:** any impacted component is reachable via ≥ 2 distinct
  dependency paths (computed by counting `dependency_paths` per impacted
  component).
- **Example:** fires for `copybook:WARRCOPY` — `proc:WARRANTY` is reachable
  via more than one path ("test coverage must exercise each path").

## Release checklist rules (rule citations)

`build_checklist(ctx, signals)` in `backend/intelligence/release_checklist.py`
emits `ChecklistItem`s; each item's `rule` field cites the rule that produced
it, so every checklist line is traceable to evidence. For
`copybook:WARRCOPY` the actual output is:

| Item id | Rule citation | Fires when |
|---|---|---|
| `CHK-JOBS-IMPACTED` | `jobs_impacted` | `affected_jobs` non-empty |
| `CHK-DB2-WRITE` | `db2_write_involved` | any involved DB2 resource with `access: write` |
| `CHK-DB2-READ` | `db2_read_involved` | any involved DB2 resource with `access: read` |
| `CHK-SHARED-COPYBOOK` | `shared_copybook_change` | `SHARED_COPYBOOK_CHANGE` signal fired |
| `CHK-PROCS-AFFECTED` | `procs_affected` | `affected_procs` non-empty |
| `CHK-TRANSITIVE-IMPACT` | `transitive_impact` | `transitive_impacts` non-empty |
| `CHK-HIGH-FAN-OUT` | `high_fan_out` | `HIGH_FAN_OUT` signal fired |

The checklist is advisory: it structures the release manager's review, it
does not render a go/no-go verdict. Nothing in the deterministic stack
approves or blocks a release — that decision stays with the human.
