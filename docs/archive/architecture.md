# Architecture — Phase 1: Deterministic Change Impact Engine

## Overview

The Phase 1 system scans a synthetic mainframe repository (COBOL, copybooks,
JCL, PROCs, DB2 DDL), extracts dependency relationships **deterministically
from source evidence**, builds a directed graph, and answers change-impact
queries. There is no LLM anywhere in Phase 1: every dependency shown by the
CLI, API, or UI was found by a parser in a real source file.

```
sample_mainframe/
      │  scan
      ▼
┌─────────────────────┐
│ repository_scanner  │  walks the repo, dispatches per file type
└────────┬────────────┘
         │
   ┌─────┼──────────────────────────────┐
   ▼     ▼              ▼               ▼
cobol_  jcl_parser   sql_parser    (copybook inventory)
parser
   │     │              │
   └─────┴──────────────┴──▶  components[] + dependencies[]
                                (every dependency has evidence)
                                     │
                                     ▼
                          ┌───────────────────┐
                          │ DependencyGraph   │  NetworkX MultiDiGraph
                          │  (backend/graph)  │  edge: A→B = "A depends on B"
                          └────────┬──────────┘
                                   ▼
                          ┌───────────────────┐
                          │ ImpactAnalyzer    │  BFS on the REVERSED graph
                          │  (backend/graph)  │  (dependents of a change)
                          └────────┬──────────┘
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              analyze.py /    FastAPI API    React + Vite + Cytoscape
              impact.py (CLI) (/api/...)      frontend (Phase 1 UI)
```

## Backend modules

| Module | Responsibility |
|---|---|
| `backend/models/component.py` | Normalized `Component` dataclass: `id` (`"<kind>:<NAME>"`), `name`, `type`, `source_file` |
| `backend/models/dependency.py` | Normalized `Dependency` dataclass: `source`, `target`, `relationship`, mandatory `Evidence{file, line, text}` |
| `backend/parsers/cobol_parser.py` | COPY / static CALL / EXEC SQL (SELECT→read, INSERT/UPDATE/DELETE→write) extraction. Regex-based; interfaces are modular so a grammar/AST parser can replace internals later |
| `backend/parsers/jcl_parser.py` | JCL `EXEC PGM=` / `EXEC PROC=` steps; PROC `EXEC PGM=` steps; `//*` comments skipped |
| `backend/parsers/sql_parser.py` | `CREATE TABLE` → DB2_TABLE components |
| `backend/parsers/repository_scanner.py` | Walks `sample_mainframe/`, dispatches per directory/extension, materializes referenced-but-unseen targets as `source_file="unknown"` (explicit, never guessed) |
| `backend/graph/dependency_graph.py` | NetworkX `MultiDiGraph` wrapper; queries for upstream/downstream/edges/counts. MultiDiGraph preserves parallel edges (e.g. a program that both READS and WRITES a table) |
| `backend/graph/impact_analyzer.py` | BFS in impact direction (reversed edges); direct = distance 1, transitive = distance ≥ 2; shortest dependency paths with per-edge evidence |
| `backend/api/app.py` | FastAPI app; graph built once at startup |

## Key design decisions

1. **Edge direction = "depends on".** `program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY`
   means WARR001 depends on WARRCOPY. Impact traversal therefore walks the
   **reversed** graph: dependents of the changed component are impacted.
   This is implemented explicitly (`reversed_view()`) and tested
   (`test_impact_flows_to_dependents_not_dependencies`).

2. **MultiDiGraph, not DiGraph.** A plain DiGraph collapses parallel
   relationships between the same pair (READS_TABLE + WRITES_TABLE on one
   table became a single edge during development — caught by counting).
   MultiDiGraph keeps every dependency as its own edge with its own evidence.

3. **Shortest paths only.** `dependency_paths` reports each impacted component
   via its shortest impact chain(s). Parallel edges (read vs write) each get
   their own path variant so every relationship is explained with its own
   evidence.

4. **No guessing.** Dynamic CALLs (`CALL WS-VAR`) are ignored. Unknown
   references are materialized as `source_file="unknown"` components rather
   than silently dropped or invented.

5. **Swappable graph backend.** All graph access goes through
   `DependencyGraph`; replacing NetworkX with Neo4j later means changing one
   module, not the parsers, analyzer, API, or UI.

## Data flow for an impact query

`GET /api/impact/copybook:WARRCOPY`
→ `ImpactAnalyzer.analyze` → BFS on reversed graph from `copybook:WARRCOPY`
→ direct (distance 1): `program:WARR001`, `program:WARR002`
→ transitive (distance ≥ 2): `proc:WARRANTY`, `job:DAILY01`, `job:WARRBTCH`
→ paths + evidence serialized from the dependency edges traversed.
