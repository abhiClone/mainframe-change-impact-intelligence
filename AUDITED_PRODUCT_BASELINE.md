# Audited Product Baseline

Audit remediation completion date: 2026-09-26

## Frozen phase baselines (unchanged)

Phase 1
- commit: dd154309275682c6c796baa558b4bab4b454ec7f
- tag: phase1-complete

Phase 2A
- commit: c7052915a7f0404fbbcf4920bc0c94bd201a776c
- tag: phase2a-complete

Phase 2B
- commit: f697ae9a19626f0fcb76f2cc48315e66ff620fa9
- tag: phase2b-complete

## Audited product baseline

Backend tests:
- 166 passed
- 0 failed

Frontend tests:
- 9 passed
- 0 failed

Mainframe repository:
- 18 components
- 30 dependencies

Test catalog:
- 12 test cases

Historical incidents:
- 17

WARRCOPY:
- 7 recommended tests
- 7 risk signals
- 7 checklist items
- 11 relevant incidents

UNUSED:
- 0 impact-driven tests
- 0 risk signals
- 0 checklist items
- 0 relevant incidents

## Product audit remediation completed

- httpx declared explicitly
- Python dependencies constrained
- fresh-clone verification successful
- malformed YAML converted to controlled domain errors
- test catalog validates graph component/job references
- root README updated for Phase 2B product
- frontend README updated
- frontend trust-boundary tests added
- empty-input validation added
- INC-1055 synthetic incident corrected

## Architecture guarantees

- dependency discovery is deterministic
- reverse change impact is deterministic
- test recommendation is deterministic
- risk signals are deterministic
- release checklist is deterministic
- historical incident selection/relevance is deterministic
- AI cannot modify verified deterministic artifacts
- AI prose remains non-authoritative

## Known limitations

- synthetic incident repository only
- no ServiceNow/Jira integration
- no semantic similarity/embeddings
- involved resources currently limited to DB2 READS_TABLE/WRITES_TABLE
- HTTP LLM provider not live-tested against a paid API
- AI prose not fully fact-checked
- regex-based Phase 1 parser limitations
- shortest impact paths only
- in-memory graph
- actual visual/browser rendering still requires a dedicated manual visual audit
- Starlette emits a cosmetic httpx/httpx2 deprecation warning

## Freeze status

The audited product baseline is committed and tagged (tag: audited-product-baseline).
Phase 3 was not started and no functionality was added beyond audit remediation.
