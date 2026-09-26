# Change Impact

`ImpactAnalyzer.analyze(component_id)` (`backend/graph/impact_analyzer.py`) answers
"what does changing this component affect?" as a pure deterministic function over the
frozen dependency graph.

## Semantics

- **Direction:** impact traverses edges **backwards** (the graph stores "depends on";
  dependents are impacted).
- **Direct impact:** dependents at distance 1.
- **Transitive impact:** dependents at distance ≥ 2.
- **Dependency paths:** shortest impact chain(s) per impacted component, each edge
  carrying its evidence. Parallel edges (read vs write) each get their own path variant
  so every relationship is explained with its own evidence.
- **A dependency is not a dependent:** changing a component never "impacts" the
  components it depends on.

## Scenario: `copybook:WARRCOPY`

(`.venv/bin/python impact.py copybook:WARRCOPY` — also `GET /api/impact/copybook:WARRCOPY`)

- **Direct impact (2):** `program:WARR001`, `program:WARR002`
- **Transitive impact (3):** `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`
- **Dependency paths (6):**
  - `copybook:WARRCOPY <- program:WARR001`
  - `copybook:WARRCOPY <- program:WARR002`
  - `copybook:WARRCOPY <- program:WARR001 <- job:DAILY01`
  - `copybook:WARRCOPY <- program:WARR002 <- job:WARRBTCH`
  - `copybook:WARRCOPY <- program:WARR001 <- proc:WARRANTY`
  - `copybook:WARRCOPY <- program:WARR002 <- proc:WARRANTY`
- **Source evidence** (examples):
  - `WARR001 -> WARRCOPY [USES_COPYBOOK]` — `cobol/WARR001.cbl:15` — `COPY WARRCOPY.`
  - `DAILY01 -> WARR001 [EXECUTES_PROGRAM]` — `jcl/DAILY01.jcl:6` — `//STEP030  EXEC PGM=WARR001`
  - `WARRANTY -> WARR002 [EXECUTES_PROGRAM]` — `proc/WARRANTY.proc:3` — `//STEP01   EXEC PGM=WARR002`

## Scenario: `table:WARRANTY`

Changing a DB2 table shows the parallel-edge semantics: `program:WARR001` both reads
and writes `table:WARRANTY`, so it appears via two path variants (one per relationship),
each with its own evidence (`FROM WARRANTY` vs `INSERT INTO WARRANTY`).

## Negative control: `copybook:UNUSED`

(`.venv/bin/python impact.py copybook:UNUSED` — also `GET /api/impact/copybook:UNUSED`)

- Direct impact: 0 · Transitive impact: 0 · Dependency paths: none · Evidence: none

The engine reports the empty result instead of pretending everything is related. The
UI renders a clean empty state; the Release Intelligence view shows zero tests, zero
signals, zero checklist items, zero incidents. This negative control is pinned by tests
and is a first-class demo asset.

## Unknown components

`impact.py program:NOPE` prints a clear error; `GET /api/impact/program:NOPE` returns
HTTP 404. Unknown ids never produce partial or guessed results.

## UI surfaces

- **Change Impact** view: impact sets, dependency paths, evidence refs.
- **Graph** view: the impact neighbourhood rendered on the full graph; click any edge
  for its evidence.
- **Release Intelligence** view: the impact context feeds test recommendation, risk
  signals, checklist, and incident intelligence (see `docs/RELEASE_INTELLIGENCE.md`).
