# Phase 2B Incident Relevance

## How relevance is determined

`build_incident_intelligence()` (`backend/intelligence/incidents/relevance.py`)
is a **pure deterministic function** of:

1. the changed component,
2. the Phase 2A `ImpactContext` (direct/transitive impact sets, dependency paths, evidence),
3. the involved DB2 resources (`read_tables` / `write_tables`),
4. the validated incident dataset.

No LLM, no embeddings, no scoring model. An incident is relevant **iff**
at least one of its `linked_components` intersects one of these
deterministic sets. Incidents with no intersection are excluded —
regardless of severity.

## Relevance reason types

| Reason | Meaning |
|---|---|
| `CHANGED_COMPONENT_MATCH` | incident linked to the changed component itself |
| `DIRECT_IMPACT_MATCH` | incident linked to a directly impacted component |
| `TRANSITIVE_IMPACT_MATCH` | incident linked to a transitively impacted component |
| `INVOLVED_WRITE_RESOURCE_MATCH` | incident linked to a table an impacted program **writes** (involved, not reverse-impacted) |
| `INVOLVED_READ_RESOURCE_MATCH` | incident linked to a table an impacted program **reads** (involved, not reverse-impacted) |

Every reason carries: the matched component, a deterministic template
explanation, the supporting Phase 1 dependency paths (when the match is an
impacted component), and real file/line/text evidence.

A linked component that equals the changed component yields only
`CHANGED_COMPONENT_MATCH` — it subsumes any involved-resource reading of
the same id (e.g. a changed table that is also listed as involved), so no
reason is duplicated. Read and write resource matches are **independent**:
a table that impacted programs both read and write yields **both**
`INVOLVED_WRITE_RESOURCE_MATCH` and `INVOLVED_READ_RESOURCE_MATCH`, each
with its own deterministic evidence (e.g. the `INSERT INTO` statement vs
the `SELECT ... FROM` statement). Precedence decides the primary reason
(write outranks read) and ordering only — it never deletes a valid
secondary reason.

## Relevance reason precedence (exact ordering)

The enum order in `REASON_PRECEDENCE` **is** the precedence order:

1. `CHANGED_COMPONENT_MATCH`
2. `DIRECT_IMPACT_MATCH`
3. `TRANSITIVE_IMPACT_MATCH`
4. `INVOLVED_WRITE_RESOURCE_MATCH`
5. `INVOLVED_READ_RESOURCE_MATCH`

An incident's strongest reason becomes its `primary_reason` (drives
ordering and display); **all** valid reasons are preserved and inspectable
— multiple matches are never collapsed.

Result ordering: primary-reason tier first, then `occurred_at` **most
recent first** as a deterministic tie-breaker, then incident id. The same
(repository, dataset, changed component) always returns the same incidents,
reasons, ordering, and evidence, whether or not an LLM is configured.

## Count semantics: primary tiers vs all reasons

`IncidentIntelligence` carries two deliberately distinct count maps:

- `primary_tier_counts` — incidents counted by **primary** reason tier.
  Sums to `total_relevant_incidents`; no incident is double-counted.
- `reason_counts` — **every valid** relevance reason counted. May exceed
  the total because one incident can carry several reasons.

Example (`copybook:WARRCOPY`, 11 relevant incidents): primary tiers are
changed 1 / direct 5 / transitive 4 / involved-write 1 / involved-read 0
(sums to 11), while `reason_counts` shows involved-write 6 and
involved-read 4 — the extra counts are the preserved secondary reasons
(e.g. `INC-1042` carries DIRECT + INVOLVED_WRITE + INVOLVED_READ). The API
and UI label these unambiguously as "primary tier" vs "all reasons".

## Severity ≠ relevance

Historical `severity` describes how bad the past incident was. Change
relevance describes whether the incident has a deterministic relationship
to the current change. `severity = critical, relevance = none` means the
incident is **not selected**. Regression test
`test_unrelated_high_severity_incident_excluded` pins this: `INC-1075`
(severity `high`, linked to `table:CUSTOMER`) is excluded for a
`copybook:WARRCOPY` change.

## History, not prediction

The engine reports *what happened before in deterministically related
places*. It never claims a probability of recurrence, never predicts a
production failure, and never performs automated root-cause analysis.
The UI keeps HISTORICAL INCIDENT SEVERITY visually separate from CHANGE
RELEVANCE so a critical past incident is never read as "this change is
high risk".
