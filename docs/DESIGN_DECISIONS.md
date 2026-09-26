# Design Decisions

The key decisions behind the platform and why each was made.

## 1. Determinism as architecture, not policy

The LLM is kept out of fact-producing roles by construction: it receives only a
serialized context of already-computed results, and a mechanical guard validates
its output. This answers the decisive interview question — "how do you stop the
LLM from inventing facts?" — architecturally rather than aspirationally.

## 2. Edge direction: "depends on"

`A → B` means "A depends on B". Impact is the reverse traversal. This matches how
engineers reason ("what depends on the thing I'm changing?") and makes the graph
readable: arrows point from consumers to providers.

## 3. MultiDiGraph instead of DiGraph

A plain directed graph collapses parallel relationships. During development, the
`READS_TABLE` + `WRITES_TABLE` pair on one table became a single edge — caught by
counting. MultiDiGraph keeps every dependency as its own edge with its own evidence,
and the UI renders parallel edges as independently selectable curves.

## 4. Evidence is mandatory

A dependency is only emitted when the parser can cite file, line, and statement.
This single rule eliminates an entire class of "where did this come from?" problems
and makes the Evidence Panel possible everywhere.

## 5. Involved ≠ impacted

Tables used by impacted programs are "involved", not "impacted". Collapsing the two
would let a copybook change appear to "impact" a database table it never touches —
exactly the kind of over-claim that destroys trust in impact tooling.

## 6. No failure probabilities

Risk signals describe structural facts and consequence classes, never likelihoods.
Claiming "X% chance of failure" from static structure would be dishonest; the
severity scale says what *could* break and how bad that would be, not how likely.

## 7. Two test tiers, no OPTIONAL

`MUST_RUN` / `SHOULD_RUN` keeps release semantics crisp. A third tier would invite
subjective thresholds that the deterministic model is designed to avoid.

## 8. Severity ≠ relevance

Historical severity describes the past incident; change relevance describes the
deterministic relationship to the current change. Rendering them separately prevents
a critical old incident from being misread as "this change is high risk".

## 9. Primary-tier vs all-reason counts

One incident can carry several valid relevance reasons. Collapsing to a single reason
would lose information; double-counting in totals would mislead. Two count maps —
primary tiers (sums to total) and all reasons (may exceed it) — keep both honest,
labelled unambiguously in API and UI.

## 10. Additive incident layer

Phase 2B changed no Phase 2A/Phase 1 result: the incident engine is a separate
evidence layer displayed alongside deterministic intelligence. This keeps each
frozen baseline meaningful and each layer independently testable.

## 11. Fail loud on bad data

Malformed YAML, unknown incident links, unknown component ids → controlled domain
errors (HTTP 500/404 naming the problem), never silent acceptance, never a raw
traceback. Invalid historical data cannot quietly contaminate results.

## 12. Graceful AI degradation

Any AI failure — network, key, guard rejection, unknown provider value — falls back
to the deterministic provider. The deterministic analysis is never gated on the AI,
and a fresh checkout works with zero configuration.

## 13. Synthetic sample data

The bundled repository, test catalog, and incidents are authored demo data containing
no employer/client production code or data. This makes the project safe to publish,
demo, and discuss — and the determinism guarantees are verifiable by anyone who
clones it.
