# Test Recommendation

Deterministic regression-test recommendation over a validated test catalog.
`recommend_tests(ctx, catalog)` (`backend/intelligence/test_selector.py`) implements
one rule — no heuristics, no scoring, no probability.

## Catalog schema

The test catalog is `sample_mainframe/tests/test_catalog.yaml` — **12 synthetic tests**.
Each entry (`TestCase` in `backend/intelligence/models.py`):

```yaml
- id: TC-WARR-002
  name: Warranty copybook regression
  type: regression                      # batch | regression | database |
                                        # functional | interface | integration
  covers:                               # component ids from the dependency graph
    - copybook:WARRCOPY
    - program:WARR001
    - program:WARR002
  execution: {job: WARRBTCH}            # always a real JCL job
  description: Recompiles and regression-tests every program using the
    WARRCOPY layout after a record-layout change.
```

Constraints enforced by convention and covered by tests: every `covers[]` entry is a
real component id from the dependency graph; every `execution.job` is a real JCL job.
The scanner ignores the `tests/` directory, so the catalog cannot perturb the graph
(verified: the graph still has exactly 18 components and 30 dependencies with the
catalog present).

## The deterministic selection rule

> A test is recommended **iff** the set of components it covers intersects the impact
> set (the changed component + direct impacts + transitive impacts).
>
> `recommended  ⇔  set(test.covers) ∩ impact_set ≠ ∅`

Repeat runs over the same repository and component id produce byte-identical
recommendations (pinned by test).

## MUST_RUN vs SHOULD_RUN — exact logic

```python
if set(matched) & ({changed} | direct):
    level = "MUST_RUN"
else:
    level = "SHOULD_RUN"
```

- **MUST_RUN** — at least one matched component is the changed component itself or a
  *direct* impact. The rationale says the representative component is "directly
  impacted".
- **SHOULD_RUN** — every matched component is *transitively* impacted only.

The representative component in the rationale is chosen by documented priority: direct
impact first, then transitive, then the changed component; ties broken alphabetically.
Results are sorted by `(impact_level, test_id)` — all `MUST_RUN` before `SHOULD_RUN`,
alphabetical within each level.

An `OPTIONAL` tier was deliberately omitted: two tiers keep the release semantics crisp
("must run before release" vs "should run before release"). Tests outside the impact set
are simply not recommended — silent exclusion is itself a signal.

## Rationale format

```
{test_id} '{test_name}' covers {representative}, {directly|transitively}
impacted by the change to {changed} via {chain} ({file}:{line}).[ Also
matches: {other matched components}.]
```

`{chain}` renders the first dependency path in dependency direction
(`program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY`) and `{file}:{line}` is real
scan evidence. Each `RecommendedTest` also carries the deduplicated `EvidenceRef`
entries from its dependency paths.

## Real example: `copybook:WARRCOPY`

7 of 12 catalog tests are recommended:

| Level | Test | Why |
|---|---|---|
| MUST_RUN | TC-CUST-002 Customer copybook regression | covers `program:WARR001` (direct) |
| MUST_RUN | TC-DB2-001 Warranty table write regression | covers `program:WARR001`, `program:WARR002` (direct) |
| MUST_RUN | TC-PROC-001 WARRANTY proc execution chain | covers `program:WARR002` (direct) + transitive |
| MUST_RUN | TC-WARR-001 Warranty claim batch end-to-end | covers `program:WARR001`, `program:WARR002` (direct) |
| MUST_RUN | TC-WARR-002 Warranty copybook regression | covers `copybook:WARRCOPY` (changed) + both programs (direct) |
| MUST_RUN | TC-WARR-003 Claim history DB2 write validation | covers `program:WARR002` (direct) |
| SHOULD_RUN | TC-CUST-001 Customer daily batch functional | covers only `job:DAILY01` (transitive) |

Example generated rationale (produced by running the code, not hand-written):

```
TC-CUST-002 'Customer copybook regression' covers program:WARR001, directly
impacted by the change to copybook:WARRCOPY via program:WARR001
--USES_COPYBOOK--> copybook:WARRCOPY (cobol/WARR001.cbl:15).
```

Phase working notes: `docs/archive/test-recommendation-model.md`.
