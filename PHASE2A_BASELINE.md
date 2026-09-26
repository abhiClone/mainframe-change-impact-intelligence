# Phase 2A Baseline — Change Impact Intelligence & Test Recommendation

Phase 2A completion date: 2026-09-26

## Phase 1 baseline (frozen, unchanged)

- commit: dd154309275682c6c796baa558b4bab4b454ec7f
- tag: phase1-complete
- Deterministic COBOL/JCL/DB2 dependency & change-impact engine. Frozen:
  no Phase 1 file was modified by Phase 2A work
  (`git diff phase1-complete -- backend/parsers backend/graph backend/models
  analyze.py impact.py` is empty).

## Phase 2A scope

Change Impact Intelligence & Test Recommendation.

### Tests

- 106 passed
- 0 failed

### Phase 1 graph

- networkx.MultiDiGraph (unchanged by Phase 2A)

### Repository

- 18 components
- 30 dependencies

Dependency types:

- USES_COPYBOOK: 7
- EXECUTES_PROGRAM: 7
- READS_TABLE: 5
- WRITES_TABLE: 5
- CALLS: 3
- USES_PROC: 3

### Test catalog

- 12 test cases

## Phase 2A capabilities

- Structured ImpactContext
- deterministic test recommendation
- MUST_RUN / SHOULD_RUN prioritization
- involved DB2 resource analysis
- deterministic release-risk signals
- deterministic release checklist
- provider-independent explanation layer
- deterministic fallback provider
- optional HTTP LLM provider
- identifier/subject hallucination guard
- explanation_source distinction
- Release Intelligence UI

## Architecture rule

Phase 1 dependency discovery remains deterministic.
LLMs do not discover dependencies, select tests,
generate deterministic risk signals, or modify verified results.

## Known trust boundary

Identifier grounding is validated automatically.
Natural-language interpretation may still contain unsupported wording,
therefore AI prose is non-authoritative and deterministic evidence
remains the source of truth.

## Known limitations

- regex-based Phase 1 parsing
- shortest dependency paths only
- in-memory graph
- involved resources currently limited to deterministic DB2
  READS_TABLE/WRITES_TABLE relationships
- natural-language AI prose is not fully fact-checked
- HTTP LLM provider has not been live-tested with a paid API

## Freeze status

Phase 2A work is committed and tagged (tag: phase2a-complete). No Phase 2B,
Phase 3, incident correlation, new dependency parsing, Neo4j, Git
integration, ServiceNow/Jira integration, or other feature work was started.
