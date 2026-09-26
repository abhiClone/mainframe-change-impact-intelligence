# BUILD_LOG — Phase 1: Deterministic Change Impact Engine

All entries record work actually executed and verified in this workspace.
Nothing is claimed without a run behind it.

## 2026-09-26 — Project setup

- Created `~/workspace/mainframe-impact/` with `sample_mainframe/`, `backend/`
  (`models/`, `parsers/`, `graph/`, `api/`, `tests/`), `frontend/`, `docs/`.
- Environment: Python 3.12.3 (venv at `.venv`), Node v24.20.0, npm 10.9.4.
- `pip install networkx fastapi pydantic pytest uvicorn` into the venv (PEP 668
  required a venv; system pip refused). Verified imports OK.
- Decision: component id scheme `"<kind>:<NAME>"` (`program:WARR001`,
  `copybook:WARRCOPY`, `job:DAILY01`, `proc:WARRANTY`, `table:WARRANTY`).

## 2026-09-26 — Synthetic repository (`sample_mainframe/`)

Created (all hand-written, synthetic automotive after-sales data):
- `cobol/CUST001.cbl` — COPY CUSTCOPY, COPY VEHCOPY, CALL 'CUST002',
  SELECT CUSTOMER (read), INSERT CUSTOMER (write)
- `cobol/CUST002.cbl` — COPY CUSTCOPY, SELECT CUSTOMER, SELECT VEHICLE
- `cobol/WARR001.cbl` — COPY WARRCOPY, COPY CUSTCOPY, CALL 'CUST002',
  SELECT WARRANTY (read), INSERT WARRANTY (write)
- `cobol/WARR002.cbl` — COPY WARRCOPY, CALL 'VEH001', UPDATE WARRANTY (write),
  INSERT CLAIM_HISTORY (write)
- `cobol/VEH001.cbl` — COPY VEHCOPY, SELECT VEHICLE (read), DELETE VEHICLE (write)
- `copybook/CUSTCOPY.cpy`, `WARRCOPY.cpy`, `VEHCOPY.cpy`, `UNUSED.cpy`
  (UNUSED referenced nowhere — negative test)
- `jcl/DAILY01.jcl` (PGM=CUST001, PROC=WARRANTY, PGM=WARR001),
  `jcl/NIGHT01.jcl` (PGM=CUST002, PROC=CUSTOMER),
  `jcl/WARRBTCH.jcl` (PROC=WARRANTY, PGM=WARR002)
- `proc/WARRANTY.proc` (PGM=WARR002, PGM=WARR001), `proc/CUSTOMER.proc` (PGM=CUST001)
- `sql/schema.sql` — CREATE TABLE CUSTOMER, WARRANTY, VEHICLE, CLAIM_HISTORY

## 2026-09-26 — Parsers + graph (backend)

Files created:
- `backend/models/component.py`, `backend/models/dependency.py`
  (Evidence{file, line, text} mandatory on every dependency)
- `backend/parsers/cobol_parser.py` — COPY / static CALL / EXEC SQL block scan
  (SELECT→READS_TABLE, INSERT/UPDATE/DELETE→WRITES_TABLE); skips `*` comment
  lines; guards `DELETE FROM` against misread as SELECT; dynamic CALLs ignored
- `backend/parsers/jcl_parser.py` — EXEC PGM=/PROC= per JCL step, PROC steps;
  `//*` comments skipped; PROC name from `//<name> PROC` line
- `backend/parsers/sql_parser.py` — CREATE TABLE extraction
- `backend/parsers/repository_scanner.py` — walks repo, dispatches per
  directory; referenced-but-missing targets materialized with
  `source_file="unknown"` (none occur in synthetic data)
- `backend/graph/dependency_graph.py` — NetworkX wrapper
- `backend/graph/impact_analyzer.py` — BFS on reversed graph; direct =
  distance 1, transitive = distance ≥ 2; shortest paths with per-edge evidence

Failure + fix (caught by counting, before tests):
- First graph used `nx.DiGraph`; `analyze.py` reported 27 dependencies while
  the scanner emitted 30 — parallel edges (READS_TABLE + WRITES_TABLE between
  the same program/table pair) were collapsed. Switched to `nx.MultiDiGraph`;
  count now 30 and every dependency keeps its own evidence.

## 2026-09-26 — CLI proof (executed)

- `.venv/bin/python analyze.py` →
  `COBOL programs: 5, Copybooks: 4, JCL jobs: 3, PROCs: 2, DB2 tables: 4,
  Dependencies discovered: 30`
- `.venv/bin/python impact.py copybook:WARRCOPY` →
  direct: WARR001, WARR002; transitive: DAILY01, WARRBTCH, WARRANTY;
  6 dependency paths each with file/line/statement evidence. Matches the
  master-prompt example shape.
- `.venv/bin/python impact.py table:WARRANTY` → direct WARR001/WARR002
  (incl. separate READS_TABLE/WRITES_TABLE path variants), transitive
  DAILY01/WARRBTCH/WARRANTY.
- `.venv/bin/python impact.py copybook:UNUSED` → 0 direct, 0 transitive
  (negative test passes via CLI).
- Cosmetic fix: `impact.py` dependency paths now print full component ids
  (`proc:WARRANTY` vs `table:WARRANTY` were ambiguous as bare names).

## 2026-09-26 — Automated tests (executed)

- Created `backend/tests/test_phase1.py` (+ `conftest.py`): 13 tests mapping to
  the 8 acceptance tests (COPY/CALL/SELECT/UPDATE/JCL PGM/JCL PROC/impact
  paths/unrelated exclusion), the UNUSED.cpy negative test, evidence
  completeness, impact-direction semantics, repository counts, unknown-id
  KeyError.
- `.venv/bin/python -m pytest backend/tests/ -v` → **13 passed, 0 failed**.

## 2026-09-26 — FastAPI backend (executed)

- Created `backend/api/app.py`: graph built once at startup; endpoints
  `/api/components`, `/api/dependencies`, `/api/graph`, `/api/component/{id}`,
  `/api/impact/{id}`, `/api/summary` (summary is a small extra, documented).
- Started with uvicorn on :8000 and verified with curl:
  - `/api/summary` → correct counts, 30 dependencies
  - `/api/components` → 18 components, 5 types
  - `/api/dependencies` → 30, all with evidence
  - `/api/impact/copybook:WARRCOPY` → direct [WARR001, WARR002], transitive
    [DAILY01, WARRBTCH, WARRANTY], 6 paths, 6 evidence items
  - `/api/component/program:WARR001` → correct upstream/downstream
  - `/api/impact/copybook:UNUSED` → empty impact
  - unknown id → HTTP 404
- `run_api.sh`, `run_tests.sh`, `requirements.txt` created.

## 2026-09-26 — Frontend (delegated to subagent) — VERIFIED COMPLETE

Subagent built React + TypeScript + Vite + Cytoscape UI in `frontend/`:
- `src/api.ts` — typed API client (`API_BASE` default `http://localhost:8000`,
  overridable via `VITE_API_URL`); graceful backend-down handling
- `src/App.tsx` — tabs: Repository Overview · Dependency Explorer ·
  Change Impact · Graph
- `src/views/Overview.tsx` — count cards from `/api/summary`
- `src/views/Explorer.tsx` — component search; upstream/downstream edges with
  per-edge evidence
- `src/views/ImpactView.tsx` — component input (default `copybook:WARRCOPY`);
  direct/transitive lists; hop chains like
  `copybook:WARRCOPY <-[USES_COPYBOOK] program:WARR001 <-[EXECUTES_PROGRAM] job:DAILY01`
  with clickable relationship labels opening evidence
- `src/views/GraphView.tsx` — Cytoscape graph; node color+shape per type +
  legend; edge labels with dependent→depended-on arrows; "A → B means A depends
  on B" note; edge click opens Evidence Panel
- `src/components/EvidencePanel.tsx` — slide-in drawer: Relationship,
  Dependent, Depends-on, Source file, Line, Evidence text (works in all views)

Verification (executed by the subagent, artifacts confirmed by coordinator):
- `npm run build` (tsc + vite): **PASS**, zero TypeScript errors
  (one `cytoscape.Stylesheet` → `StylesheetStyle` type error fixed during dev;
  only a benign chunk-size warning remains)
- `npx vite preview --port 4173` served the production build; curl returned
  index.html + JS bundle referencing the local API; `frontend/dist/` present
- API cross-checks: `/api/impact/copybook:WARRCOPY` correct; unknown id → 404
  surfaced as a message
- Known limitation: no screenshot verification possible in this environment
  (Cytoscape styling not eyeball-checked); edge labels can overlap at some
  zoom levels.

## 2026-09-26 — Docs finalized

- `docs/phase1-results.md` — scan counts, test/API/frontend verification, all
  four impact scenarios with evidence, 20/20 acceptance criteria checklist.
- Coordinator re-ran: pytest 13/13 pass; `frontend/dist/index.html` exists;
  `impact.py` re-executed for all four scenarios (outputs captured).

## 2026-09-26 — Docs

- `README.md` (problem, architecture, dependency types, extraction, why-no-AI,
  install/run/test/API/UI instructions, limitations)
- `docs/architecture.md`, `docs/dependency-model.md`
- `docs/phase1-results.md` …to be finalized after frontend verification.

## Known limitations (Phase 1)

- Regex-based parsers: exotic COBOL formatting, complex nested SQL
  joins/aliases, and dynamic CALLs not resolved (ignored, not guessed).
- No CICS/IMS/MQ/dataset dependencies; no test/incident correlation.
- Impact paths report shortest chains only.
- No SQLite metadata store yet (target architecture); graph is in-memory per
  process, isolated behind `DependencyGraph` for a future swap.
- `/api/summary` is an extra endpoint beyond the spec (used by the UI).

## 2026-09-26 — Phase 1 final implementation audit (no new features)

- Verified `DependencyGraph` uses `networkx.MultiDiGraph`
  (backend/graph/dependency_graph.py). Multi-edge semantics proven by
  regression test `test_parallel_edges_reads_and_writes_coexist`:
  program:WARR001 --READS_TABLE--> table:WARRANTY and
  program:WARR001 --WRITES_TABLE--> table:WARRANTY coexist as two edges,
  each with its own relationship, file, line, and evidence statement.
- Six WARRCOPY impact paths explained: 5 impacted components, 6 paths —
  proc:WARRANTY is reachable via two distinct shortest chains
  (through program:WARR001 and through program:WARR002); both are valid
  because proc:WARRANTY executes both programs.
- BUG FIX: EXEC SQL blocks inside COBOL '*' comments produced a false
  READS_TABLE dependency (`_sql_deps` scanned raw text). Fixed by
  blanking comment lines (line numbers preserved) before SQL scanning in
  `parse_program`. Repo counts unchanged (18 components / 30 deps).
  Negative test: `test_commented_sql_block_produces_no_false_table`.
- Added backend/tests/test_parser_robustness.py: 20 tests covering static
  CALL (single/double quoted), dynamic CALL ignored, unquoted CALL
  ignored (limitation), multiline SELECT/INSERT/UPDATE/DELETE, COPY
  case/whitespace variants, quoted COPY ignored (limitation), comment
  keyword false-positive guards, lowercase/mixed-case source, JCL
  EXEC PGM=/PROC=, lowercase JCL, '//*' comment guard, positional PROC
  syntax ignored (limitation), lowercase PROC parse, and the multi-edge
  regression test.
- Frontend/backend integration proven: all views fetch via
  frontend/src/api.ts (`api.summary/components/component/impact/graph`);
  grep found no hard-coded dependency data in frontend/src (only a
  default input value and a help-text example). Full trace demonstrated:
  cobol/WARR001.cbl:15 `COPY WARRCOPY.` -> parser -> Dependency record
  -> MultiDiGraph edge -> GET /api/impact/copybook:WARRCOPY JSON ->
  cytoscape edge data -> EvidencePanel.
- Full verification rerun: pytest 33 passed, 0 failed; analyze.py,
  impact.py (WARRCOPY + UNUSED), and `npm run build` (tsc + vite, zero
  TS errors) all pass. No Phase 2 work started.

## 2026-09-26 - String-literal correctness fix (Phase 1 defect)
- Defect: DISPLAY 'COPY ME'. produced a false USES_COPYBOOK -> ME dependency.
- Fix (narrow, backend/parsers/cobol_parser.py only): added
  _string_literal_spans() character scanner ('...'/ "..." with ''/""
  doubled-quote escapes; unterminated quotes treated as ordinary chars)
  over the comment-blanked text. A keyword match is accepted only when
  the keyword starts outside a literal span. Static CALL 'PGM' still
  works because the CALL keyword is real code. Source text is never
  rewritten, so evidence keeps original line numbers and verbatim text.
  SELECT-presence and DELETE-before-FROM heuristics are literal-aware.
- Tests: 8 new regression tests in backend/tests/test_parser_robustness.py
  (DISPLAY 'COPY ME'., DISPLAY "CALL 'FAKEPGM'".,
  DISPLAY 'SELECT * FROM WARRANTY'.,
  DISPLAY 'UPDATE WARRANTY SET X = 1'., doubled-quote escape,
  real CALL next to literal CALL, valid COPY/CALL/multiline SELECT/UPDATE
  with evidence line+text assertions, INSERT with 'SELECT FROM WARRANTY'
  literal -> only WRITES_TABLE CLAIM_HISTORY).
- Verification: pytest 41 passed, 0 failed; analyze.py still 18
  components / 30 dependencies (7/7/5/5/3/3, unchanged -- repo had no
  literal-keyword false positives); impact.py WARRCOPY and UNUSED outputs
  identical to audit baseline. No Phase 2 work started.
