# Phase 1 Results

All results below were produced by executing the code in this workspace
(`analyze.py`, `impact.py`, pytest, curl against the FastAPI backend).
No values are hand-written.

## Repository scan (`python analyze.py`)

```
Repository Analysis

COBOL programs: 5
Copybooks: 4          (CUSTCOPY, WARRCOPY, VEHCOPY + UNUSED.cpy negative test)
JCL jobs: 3
PROCs: 2
DB2 tables: 4

Dependencies discovered: 30
```

Components: 18. Dependency mix: 7 USES_COPYBOOK, 3 CALLS, 5 READS_TABLE,
5 WRITES_TABLE, 7 EXECUTES_PROGRAM, 3 USES_PROC. Every dependency carries
file + line + statement evidence (`test_every_dependency_has_evidence`).

## Automated tests (`pytest backend/tests/ -v`)

**33 passed, 0 failed.** Covers acceptance tests 1–8 from the build spec
(COPY, CALL, SELECT-read, UPDATE-write, JCL PGM, JCL PROC, impact path
correctness, unrelated-component exclusion), the UNUSED.cpy negative test,
evidence completeness, impact-direction semantics, repository counts,
unknown-component handling, plus 20 parser-robustness tests from the
Phase 1 audit (multiline SQL, static/dynamic CALL handling, comment
keyword guards, case-insensitivity, JCL variants, intentionally
unsupported syntax negative tests, and a MultiDiGraph parallel-edge
regression test).

## API verification (curl, uvicorn :8000)

| Endpoint | Result |
|---|---|
| `GET /api/summary` | correct counts, 30 dependencies |
| `GET /api/components` | 18 components, 5 types |
| `GET /api/dependencies` | 30, all with evidence |
| `GET /api/graph` | nodes + edges for the UI |
| `GET /api/component/program:WARR001` | correct upstream/downstream |
| `GET /api/impact/copybook:WARRCOPY` | correct direct/transitive/paths/evidence |
| `GET /api/impact/copybook:UNUSED` | empty impact |
| `GET /api/impact/program:NOPE` | HTTP 404 |

## Frontend verification

- `npm run build` (tsc + vite): **PASS**, zero TypeScript errors.
- `npx vite preview --port 4173`: serves production build; index.html + JS
  bundle verified via curl; bundle references the local API.
- Views: Repository Overview, Dependency Explorer, Change Impact, interactive
  Cytoscape Graph (node color+shape per type, legend, "A → B means A depends
  on B" note). **Evidence Panel (mandatory)**: clicking any edge shows
  relationship, source file, line, evidence text — in Graph, Explorer, and
  Impact views.
- API cross-check from the frontend builder: `/api/impact/copybook:WARRCOPY`
  returns `program:WARR001` in direct impact; unknown id → 404 surfaced as a
  message, not a crash.

## Impact scenario 1 — Change: `copybook:WARRCOPY`

(`python impact.py copybook:WARRCOPY`)

- **Direct impact:** `program:WARR001`, `program:WARR002`
- **Transitive impact:** `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`
- **Dependency paths:**
  - `copybook:WARRCOPY <- program:WARR001`
  - `copybook:WARRCOPY <- program:WARR002`
  - `copybook:WARRCOPY <- program:WARR001 <- job:DAILY01`
  - `copybook:WARRCOPY <- program:WARR002 <- job:WARRBTCH`
  - `copybook:WARRCOPY <- program:WARR001 <- proc:WARRANTY`
  - `copybook:WARRCOPY <- program:WARR002 <- proc:WARRANTY`
- **Source evidence:**
  - `WARR001 -> WARRCOPY [USES_COPYBOOK]` — `cobol/WARR001.cbl:15` — `COPY WARRCOPY.`
  - `WARR002 -> WARRCOPY [USES_COPYBOOK]` — `cobol/WARR002.cbl:15` — `COPY WARRCOPY.`
  - `DAILY01 -> WARR001 [EXECUTES_PROGRAM]` — `jcl/DAILY01.jcl:6` — `//STEP030  EXEC PGM=WARR001`
  - `WARRBTCH -> WARR002 [EXECUTES_PROGRAM]` — `jcl/WARRBTCH.jcl:4` — `//STEP020  EXEC PGM=WARR002`
  - `WARRANTY -> WARR001 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:4` — `//STEP02   EXEC PGM=WARR001`
  - `WARRANTY -> WARR002 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:3` — `//STEP01   EXEC PGM=WARR002`

## Impact scenario 2 — Change: `program:WARR001`

(`python impact.py program:WARR001`)

- **Direct impact:** `job:DAILY01`, `proc:WARRANTY`
- **Transitive impact:** `job:WARRBTCH`
- **Dependency paths:**
  - `program:WARR001 <- job:DAILY01`
  - `program:WARR001 <- proc:WARRANTY`
  - `program:WARR001 <- proc:WARRANTY <- job:WARRBTCH`
- **Source evidence:**
  - `DAILY01 -> WARR001 [EXECUTES_PROGRAM]` — `jcl/DAILY01.jcl:6` — `//STEP030  EXEC PGM=WARR001`
  - `WARRANTY -> WARR001 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:4` — `//STEP02   EXEC PGM=WARR001`
  - `WARRBTCH -> WARRANTY [USES_PROC]` — `jcl/WARRBTCH.jcl:3` — `//STEP010  EXEC PROC=WARRANTY`

## Impact scenario 3 — Change: `table:WARRANTY`

(`python impact.py table:WARRANTY`)

- **Direct impact:** `program:WARR001`, `program:WARR002`
- **Transitive impact:** `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`
- **Dependency paths** (parallel read/write edges each get their own variant):
  - `table:WARRANTY <- program:WARR001` (READS_TABLE)
  - `table:WARRANTY <- program:WARR001` (WRITES_TABLE)
  - `table:WARRANTY <- program:WARR002` (WRITES_TABLE)
  - `table:WARRANTY <- program:WARR001 <- job:DAILY01` (×2, read/write variants)
  - `table:WARRANTY <- program:WARR002 <- job:WARRBTCH`
  - `table:WARRANTY <- program:WARR001 <- proc:WARRANTY` (×2)
  - `table:WARRANTY <- program:WARR002 <- proc:WARRANTY`
- **Source evidence:**
  - `WARR001 -> WARRANTY [READS_TABLE]` — `cobol/WARR001.cbl:27` — `FROM WARRANTY`
  - `WARR001 -> WARRANTY [WRITES_TABLE]` — `cobol/WARR001.cbl:31` — `INSERT INTO WARRANTY`
  - `WARR002 -> WARRANTY [WRITES_TABLE]` — `cobol/WARR002.cbl:23` — `UPDATE WARRANTY`
  - `DAILY01 -> WARR001 [EXECUTES_PROGRAM]` — `jcl/DAILY01.jcl:6` — `//STEP030  EXEC PGM=WARR001`
  - `WARRBTCH -> WARR002 [EXECUTES_PROGRAM]` — `jcl/WARRBTCH.jcl:4` — `//STEP020  EXEC PGM=WARR002`
  - `WARRANTY -> WARR001 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:4` — `//STEP02   EXEC PGM=WARR001`
  - `WARRANTY -> WARR002 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:3` — `//STEP01   EXEC PGM=WARR002`
  - `WARRBTCH -> WARRANTY [USES_PROC]` — `jcl/WARRBTCH.jcl:3` — `//STEP010  EXEC PROC=WARRANTY`

## Impact scenario 4 — Change: `copybook:UNUSED` (negative test)

(`python impact.py copybook:UNUSED`)

- **Direct impact:** 0
- **Transitive impact:** 0
- **Dependency paths:** none
- **Evidence:** none

The engine reports an empty result instead of pretending everything is
related.

## Acceptance criteria status (20/20)

1. Synthetic repository exists ✓ 2. Scanner works ✓ 3. COPY extraction ✓
4. CALL extraction ✓ 5. SELECT extraction ✓ 6. INSERT/UPDATE/DELETE ✓
7. JCL PGM ✓ 8. JCL PROC ✓ 9. Graph generated ✓ 10. Evidence on every
dependency ✓ 11. Direct impact ✓ 12. Transitive impact ✓ 13. Dependency
paths ✓ 14. No false positives ✓ 15. Tests pass (13/13) ✓ 16. CLI works ✓
17. API works ✓ 18. Minimal UI works ✓ 19. Interactive graph ✓ 20. Evidence
visible from UI ✓
