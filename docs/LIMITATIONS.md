# Limitations

Known limitations of the current baseline. None of these are hidden; each is
either pinned by a test, documented in code, or both.

## Parsing and dependency model

- **Regex-based COBOL/JCL parsing.** Works for the structured sample sources;
  a grammar/AST parser would be more robust. Parser internals are swappable
  behind stable signatures.
- **Dynamic COBOL CALLs are not resolved.** `CALL WS-VAR` (variable target)
  is ignored — no guessing.
- **Only Phase 1 dependency types are supported**: `USES_COPYBOOK`, `CALLS`,
  `READS_TABLE`, `WRITES_TABLE`, `EXECUTES_PROGRAM`, `USES_PROC`. No CICS,
  IMS, MQ, or dataset relationships.
- **Keywords inside COBOL string literals** can yield false dependencies
  (documented from the Phase 1 audit).
- **Shortest impact paths only.** Longer alternate chains are not enumerated.

## Graph and scale

- **In-memory NetworkX graph**, built once per process at API startup. No
  persistence, no incremental updates, single-repository scope.
- **COSE node positions may vary between page loads** (layout is
  non-deterministic); the graph auto-fits on load and Fit/Reset recover the view.
- **Dense at 900px width** with 18 nodes — all nodes remain visible and clickable.

## Incidents and intelligence

- **17 synthetic incidents**, not a real ServiceNow/Jira source. The
  `IncidentRepository` ABC is the integration seam for real sources later.
- **No semantic incident similarity** — relevance is exact deterministic
  correlation only.
- **Involved resources focus on DB2 READ/WRITE relationships.**

## AI layer

- **HTTP LLM provider has not been live-tested with a paid API.**
- **AI natural-language prose is non-authoritative and not fully fact-checked.**
  The guard validates identifiers, not prose; deterministic evidence remains the
  source of truth.

## Change-set analysis

- **Ambiguous mappings need a human decision.** A file like `sql/schema.sql`
  declares many tables; the platform surfaces candidates and never
  auto-selects.
- **Deletions need a base snapshot.** A deleted file that no longer exists
  in the scanned tree can only be resolved when base bytes are available
  (git mode); otherwise uncertainty is reported.
- **Git mode is CLI-only.** The HTTP API accepts explicit file lists only —
  it never takes repository or filesystem paths.
- **Rename identity follows frozen Phase 1 rules.** COBOL program and
  copybook identity is filename-derived, so renaming such a file always
  changes the component identity; SQL table identity comes from DDL
  content, so a pure DDL rename keeps the identity.
- **Path containment is enforced, not guessed.** Absolute paths,
  Windows drive/UNC paths, `..` segments, and symlink escapes are
  rejected; the platform never reads outside the analyzed tree.
- **No opaque release-risk score.** The platform aggregates evidence;
  release judgement stays with humans.

## Frontend build

- **Vite/Cytoscape produces a non-blocking chunk-size warning** on build.

## What is deliberately not built

Automated release verdicts, failure-probability prediction, automated
root-cause analysis, and any design where an LLM discovers dependencies or
modifies deterministic results. See `ROADMAP.md`.
