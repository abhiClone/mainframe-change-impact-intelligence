# Dependency Model

## Component model

Every node in the dependency graph is a `Component` with a stable id of the form
`"<kind>:<NAME>"`:

```json
{
  "id": "program:WARR001",
  "name": "WARR001",
  "type": "COBOL_PROGRAM",
  "source_file": "cobol/WARR001.cbl"
}
```

| id prefix | type | source |
|---|---|---|
| `program:<NAME>` | `COBOL_PROGRAM` | `cobol/<NAME>.cbl` |
| `copybook:<NAME>` | `COPYBOOK` | `copybook/<NAME>.cpy` |
| `job:<NAME>` | `JCL_JOB` | `jcl/<NAME>.jcl` |
| `proc:<NAME>` | `JCL_PROC` | `proc/<NAME>.proc` |
| `table:<NAME>` | `DB2_TABLE` | `sql/schema.sql` |

A component referenced but not found in the repo is materialized with
`source_file: "unknown"` so the graph stays connected without inventing provenance
(does not occur in the synthetic sample data).

## Dependency model

```json
{
  "source": "program:WARR001",
  "target": "copybook:WARRCOPY",
  "relationship": "USES_COPYBOOK",
  "evidence": {
    "file": "cobol/WARR001.cbl",
    "line": 15,
    "text": "COPY WARRCOPY."
  }
}
```

**Evidence is mandatory.** A dependency is only emitted when the parser can cite the
source file, the 1-based line number, and the source statement text. The test
`test_every_dependency_has_evidence` enforces this on every scan.

## Supported relationships

| Relationship | Meaning (source → target) | Discovered from |
|---|---|---|
| `USES_COPYBOOK` | program includes copybook | `COPY <name>.` in COBOL |
| `CALLS` | program statically calls program | `CALL '<name>'` in COBOL |
| `READS_TABLE` | program reads DB2 table | `SELECT ... FROM <table>` in `EXEC SQL` |
| `WRITES_TABLE` | program writes DB2 table | `INSERT INTO` / `UPDATE` / `DELETE FROM <table>` in `EXEC SQL` |
| `EXECUTES_PROGRAM` | job or proc runs a program | `//step EXEC PGM=<pgm>` in JCL / PROC |
| `USES_PROC` | job invokes a procedure | `//step EXEC PROC=<proc>` in JCL |

Dependency mix in the sample repository: 7 `USES_COPYBOOK`, 3 `CALLS`,
5 `READS_TABLE`, 5 `WRITES_TABLE`, 7 `EXECUTES_PROGRAM`, 3 `USES_PROC` = 30 total.

## Direction semantics

All edges point **from the dependent to the thing it depends on**:

```
program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY   (WARR001 depends on WARRCOPY)
job:DAILY01 --EXECUTES_PROGRAM--> program:WARR001      (DAILY01 depends on WARR001)
program:WARR001 --CALLS--> program:CUST002              (WARR001 depends on CUST002)
```

Change impact is therefore the **reverse** traversal: changing WARRCOPY impacts its
dependents (WARR001), and transitively the dependents of those dependents (DAILY01 via
WARR001). Changing WARR001 does **not** impact CUST002 — a dependency is not a
dependent. This is pinned by `test_impact_flows_to_dependents_not_dependencies`.

## Parallel edges

The graph is a NetworkX `MultiDiGraph`: every dependency is its own edge with its own
relationship and evidence. A program that both reads and writes a table keeps two
independent edges — e.g. `program:WARR001 → table:WARRANTY` exists as both
`READS_TABLE` (evidence: `FROM WARRANTY`, line 27) and `WRITES_TABLE` (evidence:
`INSERT INTO WARRANTY`, line 31). The frontend renders them as separate, independently
selectable curves.

## How extraction works (no AI involved)

- **COBOL**: line-oriented regexes. `COPY` statements (comment lines skipped), static
  `CALL '<literal>'` (dynamic calls ignored), `EXEC SQL ... END-EXEC` blocks scanned for
  `SELECT`/`FROM`, `INSERT INTO`, `UPDATE`, `DELETE FROM`. A `FROM` inside a `DELETE`
  block is not misread as a read. Table names are upper-cased DB2 identifiers.
- **JCL/PROC**: per-line `EXEC PGM=` / `EXEC PROC=` matching; `//*` comments skipped;
  PROC name from the `//<name> PROC` definition line.
- **DDL**: `CREATE TABLE <name>` statements.

Parsers expose stable signatures (`parse_program`, `parse_job`, `parse_proc`,
`parse_schema`, `scan_repository`) so a grammar/AST implementation can replace the
regex internals without touching the graph, analyzer, API, or UI.

Phase working notes: `docs/archive/dependency-model.md`.
