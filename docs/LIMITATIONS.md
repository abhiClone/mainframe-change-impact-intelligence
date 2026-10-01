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

## GitHub PR analysis (Phase 3B, released in v1.2.0)

- **github.com only.** No GitHub Enterprise support yet.
- **3000-file REST limit.** PRs changing more than 3000 files fail closed
  (`incomplete_change_set`) — no impact is ever computed from a partial list.
- **Synchronous analysis.** Each analysis downloads full base/head snapshots;
  no persistent caching, no webhooks, no background monitoring.
- **Read-only.** No PR comments, check runs, commit statuses, merge blocking,
  bots, or writes of any kind. GitHub App / OAuth installation flows are not
  implemented.
- **Private repositories need the server-side `GITHUB_TOKEN`.**
- **Archive resource limits** (100 MiB download / 256 MiB extracted /
  50,000 files / 20 MiB per file): oversized snapshots are rejected
  (`snapshot_too_large`), never silently truncated.
- **Inherits Phase 1 parser coverage.** Snapshot content is parsed by the same
  regex extractors, with the same dependency types and limitations.
- **No ambient proxy support.** The client is built with `trust_env=False`
  (deliberate: no environment proxy inheritance, no ambient proxy
  credentials, no NETRC inheritance). Phase 3B currently does not support
  environments where outbound GitHub access is possible only through an
  OS/environment-configured HTTP proxy — such deployments fail closed with
  `github_unavailable`. Explicit proxy configuration can be designed
  separately in the future.
- **`source_root` length bound.** Values longer than 1024 characters are
  rejected (`invalid_source_root`); this is input hardening, not filesystem
  security (traversal is rejected independently).
- **Strict upstream metadata validation.** `base.sha`/`head.sha` must be
  full 40-character hex commit SHAs; `base.repo.full_name`/
  `head.repo.full_name` must be valid `owner/repository` names; malformed
  values fail closed (`malformed_github_response`). No branch-name or
  merge-SHA substitution is ever performed.
- **Deleted-fork semantics.** `head.repo: null` is legitimate; the head
  snapshot is then fetched from the base repository by exact head SHA,
  else `head_snapshot_unavailable`.
- **Fail-closed archive host policy.** Only the explicitly audited
  archive destination `codeload.github.com` is accepted (trailing-dot
  hosts rejected). GitHub documents no fixed redirect host; if delivery
  hosts change, analysis fails closed until the new host is reviewed.
- **Actual AI context.** The explainer receives only deterministic Phase 3A
  change-set intelligence — never PR title, author, PR number, repository
  metadata, raw patch text, archive URLs, the token, or snapshot contents.

## What is deliberately not built

Automated release verdicts, failure-probability prediction, automated
root-cause analysis, and any design where an LLM discovers dependencies or
modifies deterministic results. See `ROADMAP.md`.
