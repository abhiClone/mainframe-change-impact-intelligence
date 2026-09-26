# Interview-Ready Product Baseline

Interview-ready baseline date: 2026-09-26

## Previous audited baseline

- commit: 00ee9abbdc6a2576c0c2bce76b312d8d6618094f
- tag: audited-product-baseline

## Frozen historical baselines (unchanged)

Phase 1
- commit: dd154309275682c6c796baa558b4bab4b454ec7f
- tag: phase1-complete

Phase 2A
- commit: c7052915a7f0404fbbcf4920bc0c94bd201a776c
- tag: phase2a-complete

Phase 2B
- commit: f697ae9a19626f0fcb76f2cc48315e66ff620fa9
- tag: phase2b-complete

## Final verified product

Backend tests:
- 166 passed
- 0 failed

Frontend tests:
- 17 passed
- 0 failed

Mainframe repository:
- 18 components
- 30 deterministic dependencies

Test catalog:
- 12 tests

Historical incidents:
- 17

## Primary WARRCOPY scenario

- 2 direct impacts
- 3 transitive impacts
- 6 dependency paths
- 7 recommended tests
- 7 risk signals
- 7 release-checklist items
- 11 relevant historical incidents

## UNUSED negative control

- 0 direct impact
- 0 transitive impact
- 0 involved resources
- 0 recommended tests
- 0 risk signals
- 0 checklist items
- 0 relevant incidents

## Final visual remediation

- product-level subtitle replaces stale Phase 1 wording
- Release Intelligence intro is provider-neutral
- deterministic/AI provenance distinction preserved
- Cytoscape graph automatically fits visible nodes
- Fit to view control added
- Reset view control added
- parallel READS_TABLE / WRITES_TABLE edges visibly separated
- parallel edges independently selectable
- edge interaction improved
- selected-node feedback improved
- graph help made collapsible
- evidence-reference wrapping fixed
- no horizontal page overflow at 900px
- Chromium verification completed at 1440x900, 1280x800 and 900x800

## Core architecture guarantees

- dependencies come from deterministic source parsing
- LLMs do not discover dependencies
- reverse impact is deterministic
- involved DB2 resources derive from deterministic graph edges
- test recommendation is deterministic
- test priority is deterministic
- risk signals are deterministic
- release checklist is deterministic
- historical incident relevance is deterministic
- AI cannot modify deterministic intelligence
- deterministic evidence remains the source of truth

## Trust-boundary UI

- VERIFIED IMPACT identifies deterministic results
- DETERMINISTIC SUMMARY is shown when no LLM produced the explanation
- AI EXPLANATION is shown only for validated LLM output
- historical severity is separate from change relevance
- involved resources are explicitly distinguished from impacted components

## Browser verification

- real Chromium used
- Graph render verified
- zoom/pan verified
- Fit to view verified
- Reset view verified
- Evidence Panel verified
- parallel WARR001 → WARRANTY READ/WRITE relationships verified visually and interactively
- Release Intelligence verified
- UNUSED empty state verified
- invalid-input behavior verified
- loading behavior verified

## Known limitations

- regex-based COBOL/JCL parsing
- dynamic COBOL CALLs are not resolved
- only current Phase 1 dependency types are supported
- involved resources currently focus on DB2 READ/WRITE relationships
- shortest impact paths only
- in-memory NetworkX graph
- 17 synthetic incidents rather than a real ServiceNow/Jira source
- no semantic incident similarity
- HTTP LLM provider has not been live-tested with a paid API
- AI natural-language prose is non-authoritative and not fully fact-checked
- COSE node positions may vary between page loads
- graph can be dense at 900px width
- Vite/Cytoscape produces a non-blocking chunk-size warning
