# Changelog

All notable changes to this project are recorded here. Phase and audit
baselines keep their own frozen records at the repository root:

- `PHASE1_BASELINE.md` — Phase 1: deterministic COBOL/JCL/DB2 dependency & change-impact engine
- `PHASE2A_BASELINE.md` — Phase 2A: deterministic release intelligence and grounded AI explanation
- `PHASE2B_BASELINE.md` — Phase 2B: deterministic historical incident intelligence
- `AUDITED_PRODUCT_BASELINE.md` — post-Phase-2B product audit remediation
- `INTERVIEW_READY_BASELINE.md` — interview-ready product baseline (final graph + Release Intelligence UX)

## [interview-ready] — 2026-09-26

### Added
- Fit to view and Reset view controls on the dependency graph.
- `frontend/src/__tests__/App.test.tsx` — product-level subtitle and header tests.
- `frontend/src/views/__tests__/GraphView.test.tsx` — parallel-edge independence, curve offsets, evidence retention, collapsible hint tests.
- `INTERVIEW_READY_BASELINE.md` — frozen interview-ready baseline record.

### Changed
- Header subtitle: "Phase 1 — deterministic COBOL / JCL / DB2 dependency & change-impact engine" →
  "Deterministic Mainframe Change Impact & Release Intelligence" (product-level wording).
- Release Intelligence intro copy is provider-neutral ("a grounded explanation of the verified impact
  and release data") instead of promising an AI-generated explanation.
- Graph layout automatically fits all visible nodes on load; edge styling (3px base / 5px selected,
  9px semibold labels), stronger selected-node feedback, collapsible "Reading the graph" hint.
- Parallel `WARR001 → WARRANTY` edges (`READS_TABLE` / `WRITES_TABLE`) render as visibly separated
  symmetric curves and remain independently selectable Cytoscape elements.
- Evidence references wrap (`overflow-wrap: anywhere`); no horizontal page overflow at 900px.

### Preserved (explicitly unchanged)
- All deterministic counts, rules, and semantics: Phase 1 dependency logic, Phase 2A decision logic,
  Phase 2B incident relevance logic, AI trust-boundary semantics, graph direction semantics.

## [audited-product] — 2026-09-26

Product audit remediation: reproducible setup, validation, and UI trust tests.
See `AUDITED_PRODUCT_BASELINE.md`.

### Added
- `httpx` declared in `requirements.txt`; Python dependency constraints documented.
- Fresh-clone setup verification; malformed YAML → controlled domain errors (not tracebacks).
- Test-catalog ↔ graph/job validation; frontend trust-boundary tests; empty-input validation.

### Fixed
- `INC-1055` corrected. No baseline count movement (18 components / 30 dependencies / 12 tests / 17 incidents).

## [phase2b] — 2026-09-26

Phase 2B: deterministic historical incident intelligence (17-incident synthetic dataset,
deterministic relevance engine, additive integration). See `PHASE2B_BASELINE.md`.

## [phase2a] — 2026-09-26

Phase 2A: deterministic release intelligence (test recommendation, risk signals, release
checklist) and the grounded AI explanation layer with hallucination guard.
See `PHASE2A_BASELINE.md`.

## [phase1] — 2026-09-26

Phase 1: deterministic COBOL/JCL/DB2 dependency discovery, NetworkX MultiDiGraph,
change-impact analysis with evidence, CLI + FastAPI + React frontend.
See `PHASE1_BASELINE.md`.
