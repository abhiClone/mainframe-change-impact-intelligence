# Phase 2A Test Recommendation Model

## Catalog schema

The test catalog is `sample_mainframe/tests/test_catalog.yaml` — 12
synthetic tests. Each entry (`TestCase` in `backend/intelligence/models.py`):

```yaml
- id: TC-WARR-002
  name: Warranty copybook regression
  type: regression                      # batch | regression | database |
                                        # functional | interface | integration
  covers:                               # component ids from the Phase 1 graph
    - copybook:WARRCOPY
    - program:WARR001
    - program:WARR002
  execution: {job: WARRBTCH}            # always a real JCL job
  description: Recompiles and regression-tests every program using the
    WARRCOPY layout after a record-layout change.
```

Constraints enforced by convention (and covered by tests): every `covers[]`
entry is a real component id from the frozen Phase 1 graph; every
`execution.job` is a real JCL job. The Phase 1 scanner ignores the `tests/`
directory, so the catalog cannot perturb the dependency graph (verified: the
graph still has exactly 18 components and 30 dependencies with the catalog
present).

## The deterministic selection rule

`recommend_tests(ctx, catalog)` in
`backend/intelligence/test_selector.py` implements one rule, no heuristics:

> A test is recommended **iff** the set of components it covers intersects
> the impact set (the changed component + direct impacts + transitive
> impacts).

```
matched = set(test.covers) ∩ impact_set
recommended  ⇔  matched ≠ ∅
```

There is no scoring, no ranking model, no probability. Repeat runs over the
same repository and component id produce byte-identical recommendations
(verified by test: deterministic selection).

## MUST_RUN vs SHOULD_RUN — exact logic

```python
if set(matched) & ({changed} | direct):
    level = "MUST_RUN"
else:
    level = "SHOULD_RUN"
```

- **MUST_RUN** — at least one matched component is the changed component
  itself or a *direct* impact. Rationale wording: the representative
  component is "directly impacted" by the change.
- **SHOULD_RUN** — every matched component is *transitively* impacted only.
  Rationale wording: the representative component is "transitively
  impacted".

The representative component shown in the rationale is chosen by a
documented priority: direct impact (0) first, then transitive (1), then the
changed component itself (2); ties broken alphabetically. If the
representative *is* the changed component (a test covering exactly the
changed component), no impact chain exists and the rationale says so
explicitly.

Results are sorted by `(impact_level, test_id)` — all MUST_RUN before all
SHOULD_RUN, alphabetical within each level.

## Rationale generation format

```
{test_id} '{test_name}' covers {representative}, {directly|transitively}
impacted by the change to {changed} via {chain} ({file}:{line}).[ Also
matches: {other matched components}.]
```

where `{chain}` renders the first dependency path in dependency direction:

```
program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY
```

The `{file}:{line}` suffix is real evidence from the Phase 1 scan (e.g.
`cobol/WARR001.cbl:15` is the line containing the `COPY WARRCOPY.` statement).
Each `RecommendedTest` also carries the deduplicated list of `EvidenceRef`
entries from its dependency paths.

## Real example: change to copybook:WARRCOPY

Impact set for `copybook:WARRCOPY` (from the deterministic context):
direct = `program:WARR001`, `program:WARR002`; transitive = `job:DAILY01`,
`job:WARRBTCH`, `proc:WARRANTY`. 7 of 12 catalog tests are recommended:

| Level | Test | Why |
|---|---|---|
| MUST_RUN | TC-CUST-002 Customer copybook regression | covers `program:WARR001` (direct) |
| MUST_RUN | TC-DB2-001 Warranty table write regression | covers `program:WARR001`, `program:WARR002` (direct) |
| MUST_RUN | TC-PROC-001 WARRANTY proc execution chain | covers `program:WARR002` (direct), `job:WARRBTCH`, `job:DAILY01`, `proc:WARRANTY` (transitive) |
| MUST_RUN | TC-WARR-001 Warranty claim batch end-to-end | covers `program:WARR001`, `program:WARR002` (direct) |
| MUST_RUN | TC-WARR-002 Warranty copybook regression | covers `copybook:WARRCOPY` (changed) + `program:WARR001`, `program:WARR002` (direct) |
| MUST_RUN | TC-WARR-003 Claim history DB2 write validation | covers `program:WARR002` (direct) |
| SHOULD_RUN | TC-CUST-001 Customer daily batch functional | covers only `job:DAILY01` (transitive) |

Actual generated rationales (produced by running the code, not hand-written):

```
TC-CUST-002 'Customer copybook regression' covers program:WARR001, directly
impacted by the change to copybook:WARRCOPY via program:WARR001
--USES_COPYBOOK--> copybook:WARRCOPY (cobol/WARR001.cbl:15).
```

```
TC-DB2-001 'Warranty table write regression' covers program:WARR001, directly
impacted by the change to copybook:WARRCOPY via program:WARR001
--USES_COPYBOOK--> copybook:WARRCOPY (cobol/WARR001.cbl:15). Also matches:
program:WARR002.
```

## Why OPTIONAL was omitted

The catalog and selector define exactly two impact levels. An `OPTIONAL`
tier was deliberately omitted: a two-tier model keeps the release semantics
crisp ("must run before release" vs "should run before release") and leaves
no ambiguity about where a test belongs. Tests outside the impact set are
simply not recommended — silent exclusion is itself a signal ("no regression
coverage needed for this change"). A third tier would invite subjective
thresholds, which the deterministic model is designed to avoid.
