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

## Frontend build

- **Vite/Cytoscape produces a non-blocking chunk-size warning** on build.

## What is deliberately not built

Automated release verdicts, failure-probability prediction, automated
root-cause analysis, and any design where an LLM discovers dependencies or
modifies deterministic results. See `ROADMAP.md`.
