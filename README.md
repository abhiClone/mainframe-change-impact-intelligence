# Mainframe Change Impact & Release Intelligence Platform

**Phase 1: Deterministic Mainframe Dependency & Change Impact Engine**

## Business problem

Large IBM mainframe estates contain thousands of interconnected COBOL programs,
copybooks, JCL jobs, procedures, and DB2 tables. When a developer changes one
component, answering *"what else is affected?"* is slow and error-prone:
tribal knowledge, manual cross-referencing, and missed batch jobs cause
production incidents.

This platform answers that question deterministically: it scans mainframe
sources, extracts dependency relationships **from source evidence**, builds a
dependency graph, and computes direct + transitive change impact — with every
relationship citing the file, line, and statement it was found in.

## Why no AI in dependency discovery (Phase 1)

An LLM can hallucinate a plausible-sounding but wrong dependency. In change
impact analysis, a wrong edge means a missed regression test or a false alarm
that erodes trust. So Phase 1 uses **parsers, not predictions**: regular-expression-based
COBOL/JCL/SQL parsers (with modular interfaces ready for a real grammar later)
extract only what the source actually says. Every dependency carries evidence.
Anything that cannot be proven from source is marked unknown, never guessed.
AI explanation layers come only in later phases — on top of, never instead of,
deterministic discovery.

## Architecture

```
sample_mainframe/ ──scan──▶ parsers ──▶ components + dependencies (with evidence)
                                        ──▶ NetworkX MultiDiGraph ──▶ ImpactAnalyzer
                                                                      ├─▶ CLI (analyze.py, impact.py)
                                                                      ├─▶ FastAPI (/api/...)
                                                                      └─▶ React + Vite + Cytoscape UI
```

See `docs/architecture.md` and `docs/dependency-model.md` for details.

### Supported dependency types (Phase 1)

| Relationship | Example |
|---|---|
| `USES_COPYBOOK` | `program:WARR001` → `copybook:WARRCOPY` (`COPY WARRCOPY.`) |
| `CALLS` | `program:WARR001` → `program:CUST002` (`CALL 'CUST002'`) |
| `READS_TABLE` | `program:WARR001` → `table:WARRANTY` (`SELECT ... FROM WARRANTY`) |
| `WRITES_TABLE` | `program:WARR002` → `table:WARRANTY` (`UPDATE WARRANTY`) |
| `EXECUTES_PROGRAM` | `job:DAILY01` → `program:WARR001` (`//STEP030 EXEC PGM=WARR001`) |
| `USES_PROC` | `job:DAILY01` → `proc:WARRANTY` (`//STEP020 EXEC PROC=WARRANTY`) |

Edge direction means "depends on". Impact traverses the reverse direction
(dependents of a change).

## Project layout

```
mainframe-impact/
├── sample_mainframe/      synthetic repo: cobol/, copybook/, jcl/, proc/, sql/
├── backend/
│   ├── models/            Component, Dependency (+ mandatory Evidence)
│   ├── parsers/           cobol_parser, jcl_parser, sql_parser, repository_scanner
│   ├── graph/             dependency_graph (NetworkX), impact_analyzer
│   ├── api/               FastAPI app
│   └── tests/             pytest acceptance tests
├── frontend/              React + TypeScript + Vite + Cytoscape UI
├── analyze.py             CLI: repository summary
├── impact.py              CLI: change impact for a component
├── docs/                  architecture, dependency-model, phase1-results
├── BUILD_LOG.md           implementation log
└── requirements.txt
```

## Install

```bash
cd mainframe-impact
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Frontend (separate, needs Node 18+):

```bash
cd frontend
npm install
```

## Run the analysis (CLI)

```bash
# Repository summary
.venv/bin/python analyze.py

# Change impact for a component
.venv/bin/python impact.py copybook:WARRCOPY
.venv/bin/python impact.py table:WARRANTY
.venv/bin/python impact.py copybook:UNUSED   # negative test: zero impact
```

## Run the tests

```bash
.venv/bin/python -m pytest backend/tests/ -v
# or
./run_tests.sh
```

13 tests cover the 8 acceptance criteria from the build spec (COPY, CALL,
SELECT-read, UPDATE-write, JCL PGM, JCL PROC, impact path correctness,
unrelated-component exclusion), the UNUSED.cpy negative test, evidence
completeness, impact direction semantics, and repository counts.

## Start the backend

```bash
./run_api.sh
# API at http://localhost:8000
#   GET /api/components  /api/dependencies  /api/graph
#   GET /api/component/{id}  /api/impact/{id}  /api/summary
```

## Start the frontend

```bash
cd frontend
npm run dev      # dev server (expects API at http://localhost:8000)
npm run build    # production build
npx vite preview # serve the production build
```

The UI has four views: Repository Overview, Dependency Explorer, Change
Impact, and an interactive dependency Graph. **Clicking any edge opens the
Evidence Panel** showing relationship, source file, line number, and the
exact source statement.

## Synthetic data

Everything under `sample_mainframe/` is hand-written synthetic data for an
imaginary automotive after-sales application. No proprietary code, no external
services, no network calls at runtime (the backend is fully offline).

## Known limitations (Phase 1)

- Parsers are regex-based: unusual COBOL formatting, nested `EXEC SQL` with
  complex joins/aliases, and dynamic `CALL`s are not resolved (dynamic calls
  are ignored rather than guessed).
- No CICS, IMS, MQ, GDG, or dataset dependencies yet; no test/incident
  correlation (Phase 2 scope).
- Impact paths report shortest chains only.
- SQLite metadata store from the target architecture is not yet used; the
  graph is built in memory per process (interface is isolated in
  `dependency_graph.py` for a future swap).
