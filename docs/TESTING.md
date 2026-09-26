# Testing

## Suites

| Suite | Command | Result |
|---|---|---|
| Backend | `.venv/bin/python -m pytest backend/tests/ -q` (or `./run_tests.sh`) | **166 passed, 0 failed** |
| Frontend | `cd frontend && npm test` (Vitest) | **17 passed, 0 failed** |
| Production build | `cd frontend && npm run build` | ✅ `tsc -b` + `vite build` succeed |

## What the backend tests pin (166)

- **Parsers & robustness** (`test_phase1.py`, `test_parser_robustness.py`):
  COPY/CALL/SELECT/INSERT/UPDATE/DELETE extraction, JCL `PGM=`/`PROC=`, comment
  guards, case-insensitivity, multiline SQL, dynamic-CALL negative tests,
  intentionally unsupported syntax negative tests.
- **Graph semantics**: MultiDiGraph parallel-edge preservation
  (`READS_TABLE` + `WRITES_TABLE` stay independent), node/edge counts.
- **Impact direction**: impact flows to dependents, not dependencies; shortest
  paths; per-edge evidence.
- **Evidence completeness**: every dependency carries file, line, and statement.
- **Repository counts**: 18 components, 30 dependencies, frozen.
- **Deterministic intelligence** (`test_phase2_intelligence.py`): test-selection
  rule and byte-identical repeat runs, MUST/SHOULD level logic, rationale format,
  all 8 risk-signal rules, checklist rule citations, involved-resource derivation.
- **Incident validation & relevance** (`test_phase2b_incidents.py`, `test_catalog_validation.py`):
  dataset load-time validation (unknown ids rejected, no silent acceptance),
  all 5 reason types, precedence and ordering, primary-tier vs all-reason counts,
  severity ≠ relevance (unrelated high-severity incident excluded), UNUSED
  negative control.
- **AI layer** (`test_phase2_ai.py`): provider selection and fallback, strict
  input contract, hallucination guard (subject check, vocabulary check, offending
  identifier listing), `explanation_source` authority, incident-id validation.
- **API contracts** (`test_phase2_api.py`): endpoint shapes, 404 on unknown
  components, 500 on corrupted datasets.
- **Validation & edge cases** (audit remediation): malformed YAML → controlled
  domain errors, empty-input validation, catalog↔graph consistency.

## What the frontend tests pin (17, Vitest)

- `frontend/src/__tests__/App.test.tsx`: product subtitle, absence of stale
  Phase 1 wording, tab structure.
- `frontend/src/views/__tests__/GraphView.test.tsx`: Fit/Reset controls and
  actions, independent parallel-edge data, distinct curve offsets, edge evidence
  retention, collapsible graph hint.
- `frontend/src/views/__tests__/IntelligenceView.test.tsx`: provider-neutral
  intro copy, trust-boundary badges (`VERIFIED IMPACT`, `DETERMINISTIC SUMMARY`
  vs `AI EXPLANATION`), severity/relevance separation, involved-vs-impacted
  wording, evidence-drawer no-inference message.

## Browser verification (manual, real Chromium)

Chrome for Testing at 1440×900, 1280×800, 900×800: graph render, zoom/pan,
Fit to view, Reset view, evidence panel, parallel-edge visual + interactive
verification (both `WARR001 → WARRANTY` curves clicked independently), Release
Intelligence view, UNUSED empty state, invalid-input and loading behaviour, no
horizontal overflow at 900px.

## Running everything

```bash
.venv/bin/python -m pytest backend/tests/ -q
cd frontend && npm test && npm run build
```

## Phase 3A (in development, unreleased)

On the `phase3-changeset-analysis` branch (not merged, not tagged):

- **Backend: 219 passed, 0 failed** — 166 frozen-phase tests unchanged +
  53 Phase 3A tests: `test_phase3_mapping_providers.py` (24: file→component
  mapping statuses, explicit/git providers on temporary repos only, base
  snapshots, unsafe-ref rejection, PROC mapping via the deterministic parser
  fallback, foreign-tree test-catalog selection and controlled catalog errors)
  and `test_phase3_aggregation.py` (29: multi-root dedup + provenance,
  strongest-priority-wins, READ/WRITE independence, UNUSED negative control,
  mixed mapped/unmapped sets, AI guard rejection of hallucinated ids, API
  validation).
- **Frontend: 30 passed, 0 failed** — 17 frozen-phase tests unchanged +
  13 Phase 3A tests for the new `ChangeSetView` (sixth view; demo preset
  populates input only, results from the backend; `VERIFIED CHANGE SET` /
  `VERIFIED IMPACT` / `DETERMINISTIC SUMMARY` / `AI EXPLANATION` badges).
- Frozen baseline counts (166 / 17) above describe the tagged
  `v1.0.0`/`interview-ready-baseline` state; the branch adds to them without
  changing frozen behaviour.
