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

## 2026-09-26 — Phase 2A AI explanation layer (`backend/intelligence/ai/`)

Built the optional, grounded AI explanation layer. Phase 1 files untouched
(`git diff HEAD -- backend/models backend/parsers backend/graph backend/api`
empty); only tracked-file change is `.gitignore` (+ `.env`).

Files created:
- `backend/intelligence/ai/__init__.py` — package docstring.
- `backend/intelligence/ai/ai_models.py` — Pydantic v2: `IntelligenceContext`
  (strict input contract: changed_component, impacted_components,
  dependency_paths, evidence, recommended_tests, risk_signals,
  release_checklist) and `IntelligenceExplanation` (executive_summary,
  technical_summary, testing_summary, release_considerations).
- `backend/intelligence/ai/providers.py` — `IntelligenceProvider` ABC
  (`name` property, `explain(context)`); `DeterministicProvider`
  (template-built, context-only); `FakeProvider` (canned text interpolating
  only context IDs); `HttpLlmProvider` (stdlib urllib chat-completions
  client, env-only config: INTELLIGENCE_PROVIDER=http,
  INTELLIGENCE_LLM_ENDPOINT / INTELLIGENCE_LLM_API_KEY /
  INTELLIGENCE_LLM_MODEL; system instruction forbids introducing
  identifiers not in the context); `get_provider()` (default deterministic;
  unknown INTELLIGENCE_PROVIDER value -> deterministic, no crash).
- `backend/intelligence/ai/guard.py` — `validate_explanation()` builds the
  allowed vocabulary (changed_component + impacted_components + test_ids +
  signal ids) and regex-extracts candidate IDs from all four text fields
  (`\b(?:program|job|proc|copybook|table):[A-Za-z0-9_#.-]+\b`,
  `\bTC-[A-Za-z0-9-]+\b`); unknown candidates raise
  `HallucinationError(offending: list[str])`.
- `backend/intelligence/ai/service.py` — `explain_change(impact_ctx,
  recommendations, signals, checklist, provider=None)` builds the
  IntelligenceContext from the sibling models (imported from
  `backend.intelligence.models`: ImpactContext, RecommendedTest, RiskSignal,
  ChecklistItem — landed by the parallel track; field names matched the
  spec exactly), runs provider + guard; on HallucinationError or any
  provider exception (including HttpLlmProvider misconfiguration) returns
  the DeterministicProvider explanation with executive_summary prefixed by
  "AI explanation unavailable. Deterministic analysis remains available. ".
- `.env.example` (repo root) — INTELLIGENCE_PROVIDER=deterministic plus
  commented-out LLM vars with "never commit real keys" note. `.env`
  appended to `.gitignore`. No real API keys anywhere.
- `backend/tests/test_phase2_ai.py` — 12 tests: provider selection
  (default/unknown/fake), service with default provider, fake provider
  validity, hallucinated component ID rejection (program:FAKE999),
  hallucinated test ID rejection (TC-FAKE-999), real context IDs passing,
  deterministic output containing only known IDs, service fallback for a
  hallucinating provider / an exploding provider / misconfigured http.

Commands run / outcomes:
- `.venv/bin/python -m pytest backend/tests/test_phase2_ai.py -q` -> 12 passed.
- `.venv/bin/python -m pytest backend/tests/ -q` -> 70 passed, 4 failed.
  The 4 failures are all in `backend/tests/test_phase2_intelligence.py`
  (the parallel track's test selector/checklist assertions); that module
  does not import anything from `backend/intelligence/ai/`.
- Phase 1 regression: `pytest backend/tests/test_phase1.py
  backend/tests/test_parser_robustness.py -q` -> 41 passed, 0 failed.

Scope respected: no API endpoints, no UI, no incident correlation,
CICS/IMS/MQ, Neo4j, integrations, or Phase 3 work.

## 2026-09-26 — Phase 2A deterministic intelligence core (this track)

Files created:
- `backend/intelligence/__init__.py` — package exports.
- `backend/intelligence/models.py` — Pydantic v2 models: EvidenceRef,
  PathEdge, DependencyPath, ImpactContext, TestCase, RecommendedTest,
  RiskSignal, ChecklistItem (exact names/fields per spec).
- `backend/intelligence/impact_context.py` — `build_impact_context(
  component_id) -> ImpactContext`, built ONLY from Phase 1
  `ImpactAnalyzer.analyze()` output + graph component types; raises
  KeyError for unknown ids (Phase 1 behavior). Lazy singleton graph build.
- `backend/intelligence/test_catalog.py` — `load_catalog() ->
  list[TestCase]`; YAML path resolved from the module location.
- `backend/intelligence/test_selector.py` — `recommend_tests(ctx,
  catalog) -> list[RecommendedTest]`; deterministic rule with MUST_RUN /
  SHOULD_RUN levels, machine-generated rationale with concrete chain +
  file:line evidence, deduped evidence, sorted by (impact_level, test_id).
- `backend/intelligence/risk_signals.py` — `detect_risk_signals(ctx) ->
  list[RiskSignal]`; 8 rules: SHARED_COPYBOOK_CHANGE (medium),
  MULTIPLE_PROGRAMS_IMPACTED (medium), MULTIPLE_BATCH_JOBS_IMPACTED
  (medium), DB2_WRITE_INVOLVED (high), MULTIPLE_DB2_TABLES_IMPACTED
  (medium), TRANSITIVE_IMPACT (low), HIGH_FAN_OUT (medium),
  MULTIPLE_EXECUTION_PATHS (low). All ids/evidence grounded in real data.
- `backend/intelligence/release_checklist.py` — `build_checklist(ctx,
  signals) -> list[ChecklistItem]` with rules jobs_impacted,
  db2_write_involved, db2_read_involved, shared_copybook_change,
  procs_affected, transitive_impact, high_fan_out; each item cites its rule.
- `sample_mainframe/tests/test_catalog.yaml` — 12 synthetic tests
  (TC-WARR-001..003, TC-CUST-001..004, TC-VEH-001..002, TC-IFACE-001,
  TC-PROC-001, TC-DB2-001); all covers[] use real component ids, all
  execution.job values are real jobs. Scanner ignores `tests/`, so the
  Phase 1 graph is unchanged (verified: 18 components, 30 deps).
- `backend/tests/test_phase2_intelligence.py` — 36 business-behavior tests.

Files modified:
- `requirements.txt` — added `pyyaml` (allowed; not a Phase 1 file).
  Installed pyyaml-6.0.3 into `.venv`.

Commands run / outcomes:
- `.venv/bin/python -m pytest backend/tests/ -q` -> 77 passed, 0 failed
  (41 Phase 1 + 36 Phase 2A). Note: an earlier sibling-track log entry
  recorded 4 failures in `test_phase2_intelligence.py`; those were this
  track's own incorrect test assumptions (read/write-table expectations
  for a copybook change) and are fixed — the full suite is green.

Verified behaviors (all via tests):
- copybook:WARRCOPY -> 2 direct / 3 transitive impacts, depth >= 2,
  7 recommended tests, SHARED_COPYBOOK_CHANGE fires with WARR001/WARR002
  evidence, deterministic selection (repeat runs identical).
- copybook:UNUSED -> zero recommendations AND zero risk signals.
- table:WARRANTY -> DB2_WRITE_INVOLVED severity high; read_tables and
  write_tables kept distinguishable (table:CLAIM_HISTORY: read=[] / write
  present).
- Unknown component id raises KeyError.

Semantic note: read_tables/write_tables are derived from READS_TABLE /
WRITES_TABLE edges in the Phase 1 analyze() evidence set (impact-path
evidence), per spec. For a copybook change these are legitimately empty
(tables sit upstream of impacted programs, never on impact paths); they
are populated for table changes (e.g. table:WARRANTY, table:CLAIM_HISTORY).

Scope respected: no Phase 1 file modified (graph still 18 components /
30 deps, all 41 Phase 1 tests pass); no incident correlation, CICS/IMS/MQ,
Neo4j, integrations, API, UI, AI layer, or Phase 3.

---

## Phase 2A API track (2026-09-26)

Files created:
- backend/api/intelligence.py: FastAPI APIRouter with GET /api/intelligence/{component_id}
  (full bundle: changed_component, impact, recommended_tests, risk_signals,
  release_checklist, ai_explanation), GET /api/test-recommendations/{component_id},
  GET /api/risk-signals/{component_id}, GET /api/test-catalog. Composes the
  intelligence services (build_impact_context -> load_catalog ->
  recommend_tests -> detect_risk_signals -> build_checklist -> explain_change);
  no Phase 1 dependency logic duplicated. 404 on unknown component.
- backend/tests/test_phase2_api.py: 10 tests using fastapi.testclient.TestClient.

Files modified:
- backend/api/app.py: two lines only — import intelligence router and
  app.include_router(intelligence_router). No existing endpoint touched.

Environment note:
- Installed httpx2 into .venv (required by starlette's TestClient).

Commands run and outcomes:
- `.venv/bin/pip install httpx2` — ok
- `.venv/bin/python -m pytest backend/tests/test_phase2_api.py -q` — 10 passed
  (after fixing two test assertions: IntelligenceExplanation fields are
  executive_summary/technical_summary/testing_summary/release_considerations;
  RecommendedTest uses impact_level, not priority)
- `.venv/bin/python -m pytest backend/tests/ -q` — 87 passed (41 Phase 1 +
  46 Phase 2, all green)

Verified behaviors (via tests):
- copybook:WARRCOPY intelligence bundle returns all six top-level keys with
  non-empty recommended_tests, risk_signals, release_checklist and a valid
  ai_explanation (non-empty executive_summary).
- copybook:UNUSED -> empty recommended_tests and empty risk_signals.
- table:WARRANTY -> DB2_WRITE_INVOLVED signal present with severity high.
- /api/test-catalog returns exactly 12 tests.
- Unknown component id -> 404 on all three component-scoped intelligence endpoints.
- Phase 1 spot-check: /api/impact/copybook:WARRCOPY still 200.

## 2026-09-26 — Phase 2A documentation (docs-only; no code changed)

Wrote four interview-quality design docs, grounded by reading the actual
implemented code in `backend/intelligence/` + `backend/intelligence/ai/`
(never describing planned functionality as completed). Phase 1 untouched.
API/UI tracks not yet present in the repo — documented against the backend
intelligence + AI code only, noted as "see implementation."

- `docs/phase2-architecture.md` — the layered pipeline (source → frozen
  Phase 1 parsers → graph → deterministic impact → ImpactContext → test
  selection + risk signals + checklist → optional AI explanation → UI),
  per-layer ownership/forbidden-acts table, text component diagram, and the
  data flow for `GET /api/intelligence/{component_id}`.
- `docs/test-recommendation-model.md` — catalog schema, the deterministic
  selection rule (`coverage ∩ impact set`), MUST_RUN/SHOULD_RUN exact logic,
  rationale format, a real executed example (change to `copybook:WARRCOPY` →
  6 MUST_RUN + 1 SHOULD_RUN with verbatim rationales such as
  `program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY (cobol/WARR001.cbl:15)`),
  and why OPTIONAL was omitted.
- `docs/risk-signal-model.md` — all 8 implemented signals (id, trigger
  rule, severity logic, real example with evidence), the severity scale
  (high = persistent-data corruption consequence class), the explicit
  no-failure-probabilities statement, and the 7 checklist rules with their
  rule citations.
- `docs/ai-grounding.md` — what the AI may do (summarize/explain the four
  sections) vs the 7 prohibitions, the `IntelligenceProvider` abstraction
  (deterministic / fake / http), the strict `IntelligenceContext` input
  contract, the hallucination guard mechanism (allowed vocabulary + regex
  extraction + `HallucinationError` + fallback), fallback prefix behavior,
  and the `.env.example` / no-keys-in-repo policy.

Verification of documented examples: ran `build_impact_context`,
`recommend_tests`, `detect_risk_signals`, `build_checklist` for
`copybook:WARRCOPY` (direct 2 / transitive 3, depth 2, 7 recommendations,
6 signals, 5 checklist items) — all doc examples are real outputs.

## 2026-09-26 — Phase 2A frontend: Release Intelligence view (frontend track)

Files created:
- `frontend/src/views/IntelligenceView.tsx` — new "Release Intelligence"
  view. Component-id input (default `copybook:WARRCOPY`, editable) +
  Analyze button. Sections: Change Summary, Impacted Components (grouped
  by type: programs/copybooks/jobs/procs/tables), Dependency paths,
  Recommended Tests, Release-Risk Signals, Release Checklist, AI
  Explanation, Evidence. Deterministic sections carry a "VERIFIED IMPACT"
  badge; only the AI section carries an "AI EXPLANATION" badge (green vs
  purple styling, `App.css`). AI fallback (executive_summary starting
  with "AI explanation unavailable.") renders a warning banner and shows
  the deterministic fallback text. Zero-impact / zero-test / zero-signal
  cases (e.g. `copybook:UNUSED`) render clean empty states with no fake
  content. Path hops and evidence refs reuse the existing EvidencePanel.

Files modified (additive only, Phase 1 views untouched):
- `frontend/src/api.ts` — added Phase 2A types (`IntelligenceResult`,
  `IntelligenceImpact`, `RecommendedTest`, `RiskSignal`,
  `ReleaseChecklistItem`, `AiExplanation`, `TestCatalogEntry`) and
  `api.intelligence(id)` / `api.testCatalog()` client functions. No
  existing Phase 1 type or endpoint changed.
- `frontend/src/App.tsx` — added the "Release Intelligence" tab + route.
- `frontend/src/App.css` — added provenance/priority/severity badge styles
  and intel list/item styles. No Phase 1 rule changed.

Verification (all commands actually run):
- Started backend: `.venv/bin/python -m uvicorn backend.api.app:app --port 8000`
  (parallel API track's endpoints present).
- `curl /api/intelligence/copybook:WARRCOPY` -> 200: 2 direct / 3
  transitive impacts, depth 2, 5 total, 7 recommended tests (MUST_RUN /
  SHOULD_RUN), 6 risk signals (SHARED_COPYBOOK_CHANGE etc.), 5 checklist
  items, ai_explanation with 4 grounded summaries. Payload shape matches
  the TS types field-for-field.
- `curl /api/intelligence/copybook:UNUSED` -> 200: 0 impacted, 0 tests,
  0 signals, 0 checklist, non-fallback AI summary present.
- `curl /api/test-catalog` -> 200: 12 entries, 6 test types.
- Grep of `frontend/src` for hard-coded component/test/signal ids beyond
  the input default `copybook:WARRCOPY` (also present in Phase 1
  ImpactView) found nothing; no deterministic result data invented
  client-side.
- `npm run build` -> tsc -b + vite build, zero errors (only the
  pre-existing cytoscape chunk-size warning). `npm run lint` -> 0 errors,
  1 pre-existing warning in Phase 1 `EdgeList.tsx`.
- Scope respected: no backend changes made by this track; no Phase 1
  frontend file modified beyond the additive tab/route/css/api additions.

## Phase 2A targeted correction (2026-09-26, uncommitted)

Correction per review: separate reverse-impacted components from involved
DB2 resources, generate DB2 rules from involved resources, and fix
deterministic-vs-AI explanation labeling.

Changes:
- `backend/intelligence/models.py`: added `InvolvedResource`
  (table/access/used_by/evidence); `ImpactContext` gains
  `involved_resources`, keeps `read_tables`/`write_tables` as
  involved-resource projections.
- `backend/intelligence/impact_context.py`: `build_impact_context()`
  collects involved resources from the impacted programs' outgoing Phase 1
  `READS_TABLE`/`WRITES_TABLE` edges (via `graph.upstream`, Phase 1
  traversal untouched). Impact paths no longer double as the DB2 source.
- `backend/intelligence/risk_signals.py`: `DB2_WRITE_INVOLVED` now fires
  from involved write resources (writers + tables as supporting
  components, write evidence attached).
- `backend/intelligence/release_checklist.py`: `CHK-DB2-WRITE` /
  `CHK-DB2-READ` now fire from involved resources.
- `backend/intelligence/ai/ai_models.py`: `IntelligenceExplanation` gains
  `subject_component` and `explanation_source` (`deterministic` | `ai`).
- `backend/intelligence/ai/providers.py`: providers emit correct source
  metadata; HTTP provider fills both fields when the model omits them.
- `backend/intelligence/ai/service.py`: `explain_change()` stamps
  `explanation_source` authoritatively (provider cannot self-label);
  deterministic provider and any failure path -> `deterministic`.
- `backend/intelligence/ai/guard.py`: validates `subject_component`
  matches the context; trust boundary documented explicitly
  ("Identifier grounding is validated automatically. Natural-language
  interpretation may still contain unsupported wording, therefore AI prose
  is non-authoritative and deterministic evidence remains the source of
  truth.").
- `backend/api/intelligence.py`: unchanged (serializes the new fields via
  Pydantic).
- Frontend: `api.ts` gains `InvolvedResource`, `ExplanationSource`,
  `involved_resources`; `IntelligenceView.tsx` adds an "Involved DB2
  Resources" section (table, read/write badge, used-by programs,
  evidence), and the explanation badge/title now come from
  `explanation_source` (DETERMINISTIC SUMMARY / AI EXPLANATION / fallback
  note); `App.css` adds `prov-det`, `rel-badge.read/.write` styles.
- Docs: `docs/ai-grounding.md` (source labeling, subject grounding, trust
  boundary), `docs/risk-signal-model.md` (DB2_WRITE_INVOLVED from involved
  resources), `docs/phase2-architecture.md` (context model wording).

Verification (commands actually run):
- `.venv/bin/python -m pytest backend/tests/ -q` -> 101 passed, 0 failed
  (87 prior + 14 new: involved-resource, DB2 signal/checklist, explanation
  source, guard subject, AI write-path, API bundle tests).
- `.venv/bin/python analyze.py sample_mainframe`, `impact.py
  copybook:WARRCOPY`, `impact.py copybook:UNUSED` -> Phase 1 behavior
  unchanged.
- Live API `/api/intelligence/copybook:WARRCOPY` -> 200: WARRCOPY not in
  affected_tables; involved read/write WARRANTY + CLAIM_HISTORY write;
  DB2_WRITE_INVOLVED fired; db2_write_involved checklist item present;
  explanation_source == "deterministic".
- Live API `/api/intelligence/copybook:UNUSED` -> 200: 0 impacts, 0
  involved resources, no DB2 signal, no checklist items.
- Live API `/api/intelligence/table:WARRANTY` -> 200: read WARRANTY,
  write WARRANTY + CLAIM_HISTORY, READS_TABLE/WRITES_TABLE distinguished.
- `npm run build` -> vite build, zero errors (pre-existing chunk-size
  warning only).
- `git diff phase1-complete -- backend/parsers backend/graph backend/models
  analyze.py impact.py` -> empty (Phase 1 frozen).

Not committed, not tagged. No Phase 2B/3 work.

## 2026-09-26 — Phase 2A correction: changed-program involved-resource regression tests

Suspected bug: involved resources missing for the changed component itself
when the changed component is a COBOL program (program resource scope not
including the changed component's own outgoing edges).
Verification result: NO BUG — `build_impact_context` already derives involved
READS_TABLE/WRITES_TABLE resources from `affected_programs` + the changed
component when `changed_component_type == COBOL_PROGRAM`, and the changed
program is not added to its own impacted-components set. Confirmed live for
program:WARR001 before any change.
Change made (Phase 2 only, no Phase 1 touch): 5 new regression tests in
backend/tests/test_phase2_intelligence.py proving for change program:WARR001:
not in its own impacted set; WARRANTY read resource (cobol/WARR001.cbl:27,
"FROM WARRANTY") and write resource (:31, "INSERT INTO WARRANTY") with
real Phase 1 file/line/text evidence; DB2_WRITE_INVOLVED fires (high,
triggered_by program:WARR001); db2_read_involved + db2_write_involved
checklist items fire.
- pytest: 106 passed, 0 failed (101 prior + 5 new).
- analyze.py sample_mainframe: 30 dependencies; impact.py WARRCOPY/UNUSED
  outputs unchanged.
- Live API program:WARR001 -> 200: direct DAILY01/WARRANTY-proc, transitive
  WARRBTCH, affected_programs [], involved WARRANTY read+write, DB2_WRITE_INVOLVED
  high, checklist db2_read_involved/db2_write_involved/jobs_impacted/
  procs_affected/transitive_impact, explanation_source deterministic.
- WARRCOPY/UNUSED/WARRANTY live scenarios unchanged.
- npm run build -> vite build, zero errors (pre-existing chunk-size warning).
- git diff phase1-complete -- backend/parsers backend/graph backend/models
  analyze.py impact.py -> empty (Phase 1 frozen).

Not committed, not tagged. No Phase 2B/3 work.

## 2026-09-26 — Phase 2B: Historical Incident Intelligence

Objective: answer "which historical production incidents are relevant to
this change, and why?" with a fully deterministic relevance engine. LLMs
never select incidents or invent incident-to-component associations.

Files created:
- sample_mainframe/incidents/incidents.yaml (17 synthetic incidents)
- backend/intelligence/incidents/__init__.py
- backend/intelligence/incidents/models.py (HistoricalIncident,
  RelevanceReason(Type), RelevantIncident, IncidentIntelligence,
  REASON_PRECEDENCE)
- backend/intelligence/incidents/repository.py (IncidentRepository ABC,
  YamlFileIncidentRepository with load-time validation,
  IncidentDatasetError)
- backend/intelligence/incidents/relevance.py (deterministic relevance
  engine; reason templates; precedence-ordered reasons; deterministic
  ordering: primary tier, occurred_at most-recent-first, id)
- backend/intelligence/incidents/service.py (lazy validated loading,
  incident_intelligence_for)
- backend/tests/test_phase2b_incidents.py (40 tests)
- docs/incident-model.md, docs/incident-relevance.md,
  docs/phase2b-architecture.md

Files modified:
- backend/intelligence/ai/ai_models.py (IntelligenceContext.relevant_incidents;
  IntelligenceExplanation gains incident_summary, historical_patterns,
  release_history_considerations)
- backend/intelligence/ai/providers.py (deterministic incident sections
  from supplied incidents only; FakeProvider canned incident clause;
  HttpLlmProvider instruction + response keys extended)
- backend/intelligence/ai/guard.py (INC- id regex; incident ids validated;
  all 7 text fields scanned)
- backend/intelligence/ai/service.py (explain_change gains optional
  incident_intelligence param; serializes only selected incidents)
- backend/api/intelligence.py (additive "incident_intelligence" key in the
  /api/intelligence bundle; new GET /api/incidents,
  /api/incidents/{incident_id}, /api/incident-intelligence/{component_id};
  unknown component -> 404, unknown incident -> 404, invalid dataset -> 500)
- backend/tests/test_phase2_ai.py (test helpers updated for the 3 new
  required explanation fields; no behavior change)
- frontend/src/api.ts (HistoricalIncident / RelevantIncident /
  IncidentIntelligence types; incidents/incident/incidentIntelligence
  client calls)
- frontend/src/views/IntelligenceView.tsx (HISTORICAL INCIDENT
  INTELLIGENCE section: id/title/date, historical-severity badge vs
  change-relevance badge, primary + all reasons, matched components,
  why-relevant, deterministic paths, evidence, symptoms, root cause,
  resolution; AI section extended with 3 incident blocks; relevant-incidents
  stat card)
- frontend/src/App.css (reason/relevance badges, incident detail styles)

Tests added: 40 Phase 2B tests (dataset load/validation, all 5 reason
types, precedence, multiple reasons, determinism, WARRCOPY/UNUSED/WARR001/
WARRANTY scenarios, evidence attachment, unrelated high-severity
exclusion, Phase 2A recommendation/signal invariance, AI incident-id
guard accept/reject, meddling-provider immutability, provider-failure
fallback, API incl. 404/500 paths).

Commands executed:
- .venv/bin/python -m pytest backend/tests/ -q -> 146 passed, 0 failed
  (106 Phase 1+2A intact)
- .venv/bin/python analyze.py sample_mainframe -> 18 components,
  30 dependencies
- .venv/bin/python impact.py copybook:WARRCOPY / copybook:UNUSED ->
  unchanged Phase 1 output
- live API checks: /api/incidents (17), /api/incidents/INC-1042,
  /api/incident-intelligence/{WARRCOPY:11, UNUSED:0, WARR001:9,
  WARRANTY:11}, /api/intelligence/copybook:WARRCOPY (incident_intelligence
  present, Phase 2A sections unchanged), unknown component -> 404,
  unknown incident -> 404
- cd frontend && npm run build -> success, zero errors
- grep frontend/src for hard-coded incident datasets -> none (API-driven)
- git diff phase2a-complete -- backend/parsers backend/graph backend/models
  analyze.py impact.py -> empty (Phase 1 frozen)

Defects found: none in Phase 1 or Phase 2A logic. (4 pre-existing AI test
helpers needed the 3 new required explanation fields after the additive
schema extension; fixed in test helpers only.)

Verification results: all acceptance criteria proven by executed commands
above. Phase 2A deterministic outputs unchanged (test recommendations,
risk signals, checklist, involved resources byte-identical).

Not committed, not tagged. No work beyond Phase 2B.

## 2026-09-26 — Phase 2B targeted semantic correction: READ/WRITE reason independence + summary semantics

Defect found: in `backend/intelligence/incidents/relevance.py::_reasons_for`,
the read-resource check was an `elif` after the write-resource check, so a
table both read and written (e.g. table:WARRANTY for copybook:WARRCOPY)
yielded only INVOLVED_WRITE_RESOURCE_MATCH — the valid READ reason was
silently discarded, contradicting "all valid reasons remain inspectable".
Also, `relevance_summary` counted primary tiers only under an ambiguous name.
Fix (Phase 2B only):
- `_reasons_for`: read and write resource matches are independent `if`
  checks; both reasons preserved with their own deterministic evidence;
  CHANGED-component subsumption and impact-beats-involved precedence kept.
- `IncidentIntelligence`: `relevance_summary` replaced by
  `primary_tier_counts` (sums to total) + `reason_counts` (all valid
  reasons, may exceed total); API/UI labels disambiguated.
- Frontend: api.ts type updated; IntelligenceView shows "primary tier: X"
  stat cards plus an explicit all-reasons line.
- Docs: docs/incident-relevance.md updated (read/write independence,
  count-semantics section with WARRCOPY example).
Tests: rewrote test_involved_read_resource_match_precedence (now asserts
BOTH reasons, WRITE primary); updated INC-1042 multi-reason expectations;
updated summary assertions; added 4 new tests (write-only CLAIM_HISTORY,
read-only VEHICLE in CUST002 context, read/write evidence distinctness,
primary-vs-all count semantics).
- pytest: 150 passed, 0 failed (146 prior + 4 net new).
- Live WARRCOPY: 11 incidents; INC-1060 (linked table:WARRANTY) now carries
  INVOLVED_WRITE + INVOLVED_READ (primary WRITE); primary_tier_counts
  changed 1/direct 5/transitive 4/involved-write 1/involved-read 0 (sums 11);
  reason_counts involved-write 6/involved-read 4.
- UNUSED: 0 relevant incidents.
- Phase 1 and Phase 2A frozen behavior unchanged (diffs vs phase2a-complete
  empty for Phase 1 paths and Phase 2A decision logic).

Not committed, not tagged. Nothing beyond Phase 2B.
