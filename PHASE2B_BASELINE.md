# Phase 2B Baseline — Historical Incident Intelligence

Phase 2B completion date: 2026-09-26

## Phase 1 baseline (frozen, unchanged)

- Commit: dd154309275682c6c796baa558b4bab4b454ec7f
- Tag: phase1-complete
- Deterministic COBOL/JCL/DB2 dependency & change-impact engine.
  No Phase 1 file was modified by Phase 2A or Phase 2B work
  (`git diff phase1-complete -- backend/parsers backend/graph
  backend/models analyze.py impact.py` is empty).

## Phase 2A baseline (frozen, unchanged)

- Commit: c705291
- Tag: phase2a-complete
- Change Impact Intelligence & Test Recommendation.
  Phase 2B did not change Phase 2A decision logic (test selection,
  MUST_RUN/SHOULD_RUN, risk-signal rules, checklist rules,
  involved-resource semantics, explanation-source semantics).

## Phase 2B scope

Historical Incident Intelligence.

### Tests

- 150 passed
- 0 failed

### Mainframe repository

- 18 components
- 30 dependencies

### Incident dataset

- 17 synthetic historical incidents
  (`sample_mainframe/incidents/incidents.yaml`)

## Phase 2B capabilities

- validated historical incident repository
- authoritative structured incident-to-component links
- deterministic incident relevance selection
- CHANGED_COMPONENT_MATCH
- DIRECT_IMPACT_MATCH
- TRANSITIVE_IMPACT_MATCH
- INVOLVED_WRITE_RESOURCE_MATCH
- INVOLVED_READ_RESOURCE_MATCH
- multiple relevance reasons preserved
- deterministic primary relevance precedence
- primary_tier_counts separated from reason_counts
- deterministic dependency/resource evidence for relevance
- incident severity separated from change relevance
- grounded incident summarization
- incident-ID hallucination protection
- Historical Incident Intelligence API
- Historical Incident Intelligence UI

## Relevance precedence

CHANGED_COMPONENT_MATCH
> DIRECT_IMPACT_MATCH
> TRANSITIVE_IMPACT_MATCH
> INVOLVED_WRITE_RESOURCE_MATCH
> INVOLVED_READ_RESOURCE_MATCH

## Important semantics

Precedence selects the primary relevance reason only.
It does not remove valid secondary reasons.

READ and WRITE resource matches are independent.
A historical incident may therefore contain both
INVOLVED_WRITE_RESOURCE_MATCH and
INVOLVED_READ_RESOURCE_MATCH.

## Summary semantics

primary_tier_counts count each relevant incident exactly once
according to its strongest reason.

reason_counts count every valid relevance reason and may
therefore exceed total_relevant_incidents.

## Architecture rule

Historical incident relevance is deterministic.
LLMs do not select incidents, create incident relationships,
change relevance ordering, or modify deterministic results.

## AI trust boundary

Identifiers are automatically grounded and validated.
AI natural-language prose remains non-authoritative.
Deterministic evidence remains the source of truth.

## Negative control

copybook:UNUSED returns:

- 0 impacted components
- 0 involved resources
- 0 relevant historical incidents

## WARRCOPY baseline

- 11 relevant historical incidents
- primary tier counts:
  - changed: 1
  - direct: 5
  - transitive: 4
  - involved-write: 1
  - involved-read: 0
- all reason counts:
  - changed: 1
  - direct: 6
  - transitive: 4
  - involved-write: 6
  - involved-read: 4

## Known limitations

- 17 synthetic incidents only
- no real ServiceNow/Jira integration
- no semantic similarity or embeddings
- involved resources limited to DB2 READS_TABLE/WRITES_TABLE
- HTTP LLM provider not live-tested with a paid API
- AI prose is not fully fact-checked
- Phase 1 regex parser limitations remain
- shortest dependency paths only
- in-memory graph

## Freeze status

Phase 2B work is committed and tagged (tag: phase2b-complete). No
semantic similarity, embeddings, vector databases, ServiceNow, Jira,
logs, prediction, automated RCA, Phase 3, or any other feature work was
started.
