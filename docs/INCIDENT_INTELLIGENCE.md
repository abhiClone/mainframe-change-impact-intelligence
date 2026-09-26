# Incident Intelligence

Historical incident intelligence: past incidents **deterministically matched** to the
current change. The engine reports *what happened before in deterministically related
places* — never a probability of recurrence, never a production-failure prediction,
never automated root-cause analysis.

> **All 17 incidents are synthetic demonstration data**, authored for this project.
> They are not mined from production logs, not imported from ServiceNow/Jira, and not
> derived from prose by any LLM. See "Synthetic data" in `README.md`.

## Incident model

`HistoricalIncident` (`backend/intelligence/incidents/models.py`), stored at
`sample_mainframe/incidents/incidents.yaml`:

| Field | Meaning |
|---|---|
| `id` | Unique id, e.g. `INC-1042` |
| `title` | Short human title |
| `occurred_at` | ISO `YYYY-MM-DD` date |
| `severity` | `low` / `medium` / `high` / `critical` — historical severity of the *past* incident |
| `status` | `open` / `investigating` / `resolved` |
| `summary` / `symptoms` | Description and observable symptoms (SQLCODEs, abends, …) |
| `linked_components` | **Authoritative structured data**: real component ids from the dependency graph |
| `failure_mode` | Machine-readable failure category |
| `root_cause_category` / `root_cause_summary` | Cause classification and summary |
| `resolution_summary` | How it was resolved |

### Link validation

`linked_components` are validated **at load time** against the actual dependency graph:

- every linked id must exist in the graph — an unknown id raises `IncidentDatasetError`
  and the whole dataset is rejected, never silently accepted or ignored;
- duplicate linked components are deduplicated; incident ids must be unique; dates,
  severities, statuses, and titles are validated; every incident needs at least one
  linked component.

Invalid historical data cannot quietly contaminate intelligence results: the API
surfaces a clear HTTP 500 naming the problem.

### Dataset design (17 incidents)

Deliberately small and interview-readable: a copybook incident (`INC-1015`), program-logic
incidents, batch failures (`INC-1088` DAILY01 DB2 timeout, `INC-1045` WARRBTCH S322), a
PROC incident (`INC-1023`), DB2 duplicate-key and data-integrity incidents, a read-related
DB incident (`INC-1050`), multi-component incidents, six unrelated incidents, and one
**unrelated high-severity** incident (`INC-1075`, severity `high`, linked only to
`table:CUSTOMER`) — proving severity alone never implies relevance. No incident is
linked to `copybook:UNUSED`, keeping it a clean negative control.

## Deterministic relevance

`build_incident_intelligence()` (`backend/intelligence/incidents/relevance.py`) is a
pure function of the changed component, the `ImpactContext`, the involved DB2 resources,
and the validated dataset. **No LLM, no embeddings, no scoring model.** An incident is
relevant iff at least one of its `linked_components` intersects one of the deterministic
sets. Incidents with no intersection are excluded — regardless of severity.

### Relevance reason types

| Reason | Meaning |
|---|---|
| `CHANGED_COMPONENT_MATCH` | incident linked to the changed component itself |
| `DIRECT_IMPACT_MATCH` | incident linked to a directly impacted component |
| `TRANSITIVE_IMPACT_MATCH` | incident linked to a transitively impacted component |
| `INVOLVED_WRITE_RESOURCE_MATCH` | incident linked to a table an impacted program **writes** (involved, not reverse-impacted) |
| `INVOLVED_READ_RESOURCE_MATCH` | incident linked to a table an impacted program **reads** (involved, not reverse-impacted) |

Every reason carries the matched component, a deterministic template explanation, the
supporting dependency paths (for impacted-component matches), and real file/line/text
evidence. A changed component subsumes any involved-resource reading of the same id
(no duplicated reasons). Read and write resource matches are **independent**: a table
both read and written yields **both** reasons, each with its own evidence. Precedence
(write outranks read) decides the primary reason and ordering only — never deletes a
valid secondary reason.

### Precedence and ordering

`REASON_PRECEDENCE` order: changed → direct → transitive → involved-write →
involved-read. An incident's strongest reason becomes its `primary_reason`; **all**
valid reasons are preserved and inspectable. Result ordering: primary-reason tier first,
then `occurred_at` most-recent-first as a deterministic tie-breaker, then incident id.
The same inputs always return the same incidents, reasons, ordering, and evidence.

### Count semantics: primary tiers vs all reasons

`IncidentIntelligence` carries two deliberately distinct count maps:

- `primary_tier_counts` — incidents by **primary** reason tier; sums to
  `total_relevant_incidents`, no double-counting.
- `reason_counts` — **every valid** relevance reason; may exceed the total because one
  incident can carry several reasons.

Example (`copybook:WARRCOPY`, 11 relevant): primary tiers are changed 1 / direct 5 /
transitive 4 / involved-write 1 / involved-read 0 (sums to 11), while `reason_counts`
shows involved-write 6 and involved-read 4 — the preserved secondary reasons. The API
and UI label these unambiguously as "primary tier" vs "all reasons".

## Severity ≠ relevance

Historical `severity` describes how bad the past incident was. Change relevance
describes whether the incident has a deterministic relationship to the current change.
`severity = critical, relevance = none` means the incident is **not selected**.
Regression test `test_unrelated_high_severity_incident_excluded` pins this: `INC-1075`
(severity `high`) is excluded for a `copybook:WARRCOPY` change. The UI keeps
HISTORICAL INCIDENT SEVERITY visually separate from CHANGE RELEVANCE.

## Additive integration

The incident layer is additive: impact, involved resources, test recommendations, risk
signals, and checklist are computed by the same deterministic functions and are
byte-identical with or without the incident layer. Historical incidents cannot alter
impacted components, dependency paths, test priority, risk signals, or checklist rules.
`IncidentRepository` is an ABC — future ServiceNow/Jira integrations plug in without
touching the relevance engine.

Phase working notes: `docs/archive/phase2b-architecture.md`,
`docs/archive/incident-model.md`, `docs/archive/incident-relevance.md`.
