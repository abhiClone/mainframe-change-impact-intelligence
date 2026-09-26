# Dependency Model — Phase 1

## Component model

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

A component referenced but not found in the repo (does not occur in the
Phase 1 synthetic data) is materialized with `source_file: "unknown"` so the
graph stays connected without inventing provenance.

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

**Evidence is mandatory.** A dependency is only emitted when the parser can
cite the source file, the 1-based line number, and the source statement text.
`test_every_dependency_has_evidence` enforces this on every scan.

## Supported relationships (Phase 1)

| Relationship | Meaning (source → target) | Discovered from |
|---|---|---|
| `USES_COPYBOOK` | program includes copybook | `COPY <name>.` in COBOL |
| `CALLS` | program statically calls program | `CALL '<name>'` in COBOL |
| `READS_TABLE` | program reads DB2 table | `SELECT ... FROM <table>` in `EXEC SQL` |
| `WRITES_TABLE` | program writes DB2 table | `INSERT INTO` / `UPDATE` / `DELETE FROM <table>` in `EXEC SQL` |
| `EXECUTES_PROGRAM` | job or proc runs a program | `//step EXEC PGM=<pgm>` in JCL / PROC |
| `USES_PROC` | job invokes a procedure | `//step EXEC PROC=<proc>` in JCL |

## Direction semantics

All edges point **from the dependent to the thing it depends on**:

```
program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY   (WARR001 depends on WARRCOPY)
job:DAILY01 --EXECUTES_PROGRAM--> program:WARR001      (DAILY01 depends on WARR001)
program:WARR001 --CALLS--> program:CUST002              (WARR001 depends on CUST002)
```

Change impact is therefore the **reverse** traversal: changing WARRCOPY
impacts its dependents (WARR001), and transitively the dependents of those
dependents (DAILY01 via WARR001). Changing WARR001 does **not** impact
CUST002 (a dependency is not a dependent) — covered by
`test_impact_flows_to_dependents_not_dependencies`.

## How extraction works (no AI involved)

- **COBOL**: line-oriented regexes over program source. `COPY` statements
  (comment lines skipped), static `CALL '<literal>'` (dynamic calls ignored),
  and `EXEC SQL ... END-EXEC` blocks scanned for `SELECT`/`FROM`,
  `INSERT INTO`, `UPDATE`, `DELETE FROM`. Table names are upper-cased DB2
  identifiers. A `FROM` inside a `DELETE` block is not misread as a read.
- **JCL/PROC**: per-line `EXEC PGM=` / `EXEC PROC=` matching; `//*` comments
  skipped. PROC name taken from the `//<name> PROC` definition line.
- **DDL**: `CREATE TABLE <name>` statements.

The parsers are intentionally regex-based for Phase 1 but expose stable
function signatures (`parse_program`, `parse_job`, `parse_proc`,
`parse_schema`, `scan_repository`) so a grammar/AST implementation can be
dropped in without touching the graph, analyzer, API, or UI.
