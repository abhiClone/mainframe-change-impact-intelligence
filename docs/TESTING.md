# Testing

## Suites

| Suite | Command | Result |
|---|---|---|
| Backend | `.venv/bin/python -m pytest backend/tests/ -q` (or `./run_tests.sh`) | **371 passed, 0 failed** |
| Frontend | `cd frontend && npm test` (Vitest) | **49 passed, 0 failed** |
| Production build | `cd frontend && npm run build` | ✅ `tsc -b` + `vite build` succeed |

## What the backend tests pin (371 = 255 frozen v1.1.0 + 116 Phase 3B)

The 255 frozen tests are unchanged: 166 frozen-phase tests (below) plus the
89 Phase 3A tests (see "Phase 3A (released in v1.1.0)" below). Phase 3B adds
116 tests across six new suites — see "Phase 3B (released in v1.2.0)" below.

- **Parsers & robustness** (`test_phase1.py`, `test_parser_robustness.py`):
  COPY/CALL/SELECT/INSERT/UPDATE/DELETE extraction, JCL `PGM=`/`PROC=`, comment
  guards, case-insensitivity, multiline SQL, dynamic-CALL negative tests,
  intentionally unsupported syntax negative tests.
- **Graph semantics**: MultiDiGraph parallel-edge preservation
  (`READS_TABLE` + `WRITES_TABLE` stay independent), node/edge counts.
- **Impact direction**: impact flows to dependents, not dependencies; shortest
  paths; per-edge evidence.
- **Evidence completeness**: every dependency carries file, line, and statement.
- **Repository counts**: 18 components, 30 dependencies, frozen.
- **Deterministic intelligence** (`test_phase2_intelligence.py`): test-selection
  rule and byte-identical repeat runs, MUST/SHOULD level logic, rationale format,
  all 8 risk-signal rules, checklist rule citations, involved-resource derivation.
- **Incident validation & relevance** (`test_phase2b_incidents.py`, `test_catalog_validation.py`):
  dataset load-time validation (unknown ids rejected, no silent acceptance),
  all 5 reason types, precedence and ordering, primary-tier vs all-reason counts,
  severity ≠ relevance (unrelated high-severity incident excluded), UNUSED
  negative control.
- **AI layer** (`test_phase2_ai.py`): provider selection and fallback, strict
  input contract, hallucination guard (subject check, vocabulary check, offending
  identifier listing), `explanation_source` authority, incident-id validation.
- **API contracts** (`test_phase2_api.py`): endpoint shapes, 404 on unknown
  components, 500 on corrupted datasets.
- **Validation & edge cases** (audit remediation): malformed YAML → controlled
  domain errors, empty-input validation, catalog↔graph consistency.

## What the frontend tests pin (49 = 34 frozen v1.1.0 + 15 Phase 3B, Vitest)

The 34 frozen tests are unchanged: 17 frozen-phase tests plus the 17 Phase 3A
`ChangeSetView` tests (the refactor to the shared `ChangeSetResults`
component kept all 17 passing unmodified — behaviour preserved by construction).

- `frontend/src/__tests__/App.test.tsx`: product subtitle, absence of stale
  Phase 1 wording, tab structure.
- `frontend/src/views/__tests__/GraphView.test.tsx`: Fit/Reset controls and
  actions, independent parallel-edge data, distinct curve offsets, edge evidence
  retention, collapsible graph hint.
- `frontend/src/views/__tests__/IntelligenceView.test.tsx`: provider-neutral
  intro copy, trust-boundary badges (`VERIFIED IMPACT`, `DETERMINISTIC SUMMARY`
  vs `AI EXPLANATION`), severity/relevance separation, involved-vs-impacted
  wording, evidence-drawer no-inference message.

## Browser verification (manual, real Chromium)

Chrome for Testing at 1440×900, 1280×800, 900×800: graph render, zoom/pan,
Fit to view, Reset view, evidence panel, parallel-edge visual + interactive
verification (both `WARR001 → WARRANTY` curves clicked independently), Release
Intelligence view, UNUSED empty state, invalid-input and loading behaviour, no
horizontal overflow at 900px.

## Browser acceptance — Phase 3B hardening pass (automated, real Chromium)

Chrome for Testing 153.0.8010.12 (Playwright, same host; servers on
127.0.0.1, `--no-proxy-server`) at 1440×900, 1280×800, 900×800, scripted in
`browser_acceptance/run_audit.py` against a route-intercepted deterministic
backend result (`browser_acceptance/make_canned_pr.py`):

- all seven views render at every viewport: no page-level horizontal
  overflow, no page errors;
- GitHub PR scenarios: empty form and invalid repository rejected
  client-side with no API call; intercepted valid PR shows long title,
  long repository, long file path, renamed file with old path,
  outside-source-root badge, base/head SHAs, auth badge, and rate-limit
  line; typed 404 renders the friendly not-found message; delayed
  response shows the "Analyzing…" loading state;
- a 200-character PR title initially clipped past the card edge; fixed
  with `overflow-wrap: anywhere` on `.intel-section-head h3`
  (`frontend/src/App.css`), re-verified at all three viewports;
- network audit: every browser request went to 127.0.0.1/localhost only —
  no browser-side requests to `api.github.com` or `codeload.github.com`;
- token audit: the distinctive backend token never appeared in the DOM,
  `localStorage`, `sessionStorage`, or cookies. (One console 404 per
  viewport is the expected log line from the intercepted typed-error
  scenario's own 404 fulfillment, not a missing resource.)

## Running everything

```bash
.venv/bin/python -m pytest backend/tests/ -q
cd frontend && npm test && npm run build
```

## Phase 3A (released in v1.1.0)

Merged into `main` and tagged `phase3a-complete` (frozen 2026-09-26):

- **Backend: 255 passed, 0 failed** — 166 frozen-phase tests unchanged +
  89 Phase 3A tests: `test_phase3_mapping_providers.py` (35: file→component
  mapping statuses, explicit/git providers on temporary repos only, base
  snapshots, unsafe-ref rejection, PROC mapping via the deterministic parser
  fallback, foreign-tree test-catalog selection and controlled catalog errors),
  `test_phase3_aggregation.py` (30: multi-root dedup + provenance,
  strongest-priority-wins, READ/WRITE independence, UNUSED negative control,
  mixed mapped/unmapped sets, AI guard rejection of hallucinated ids, API
  validation) and `test_phase3_remediation.py` (24: remediated M1–M8/L1/L2
  behaviours — change-set mapping, aggregation, cross-impact, duplicate
  normalisation, snapshot provenance, rename semantics, path security,
  catalogue isolation and strict Phase 3 aggregate models).
- **Frontend: 34 passed, 0 failed** — 17 frozen-phase tests unchanged +
  17 Phase 3A tests for the new `ChangeSetView` (sixth view; demo preset
  populates input only, results from the backend; `VERIFIED CHANGE SET` /
  `VERIFIED IMPACT` / `DETERMINISTIC SUMMARY` / `AI EXPLANATION` badges).
- Frozen baseline counts (166 / 17) describe the tagged
  `v1.0.0`/`interview-ready-baseline` state; Phase 3A adds to them without
  changing frozen behaviour.

## Phase 3B (released in v1.2.0, merged into main)

No test depends on live GitHub, CI, or the network: HTTP is mocked with
`httpx.MockTransport` and archives are built in-test. A read-only live smoke
against the public API is supplemental only (it confirmed the pinned
`X-GitHub-Api-Version: 2026-03-10` is accepted and that `previous_filename`
appears on renamed files only).

- **Backend: 116 new tests, 0 failed** — `test_github_client.py` (27: pinned
  version/media/user-agent headers, public vs authenticated requests, PR
  metadata parsing incl. forks and null head repo, 1/100/multi-page
  pagination, >3000 fail-closed, incomplete-pagination fail-closed,
  401/403/404/429/5xx/network error mapping, rate-limit capture, bounded
  retries, token absence from errors, redirect token-stripping, malicious
  redirect rejection, archive size limit, malformed SHA rejection),
  `test_github_snapshots.py` (21: traversal, backslash traversal, absolute
  paths, symlink/symlink-escape, hard links, devices, FIFOs, zip variants,
  file-count/per-file/extracted-bytes/archive-bytes limits, invalid
  layout, source-root resolution), `test_github_provider.py` (33:
  source-root validation, all status translations, unsupported status,
  scope classification, all four rename-boundary cases, base-snapshot
  reads, traversal containment), `test_github_equivalence.py` (4, incl. the
  **release-blocking invariant**: a mocked GitHub PR resolving to
  WARRCOPY+WARR002 yields semantically identical `ChangeSetIntelligence`
  to Phase 3A explicit input — 2 changed, 1 cross-impacted, 4 downstream,
  3/3/3 direct/transitive/overlap unions, 7 tests, 1 DB2 read / 2 writes,
  7 risks, 7 checklist, 11 incidents), `test_github_api.py` (24: endpoint
  contract, source-root default, all input validation, all 13 error-code →
  HTTP mappings, status endpoint with/without token, token absence from
  responses, Phase 3A route still registered), `test_github_cli.py` (7:
  flags, human/JSON output, invalid input, GitHubError exit path, token
  never printed).
- **Frontend: 15 new tests, 0 failed** — `GitHubPRView.test.tsx`: input
  rendering + source-root default, no token field, auth badge, analyze
  fires `POST` with the correct body, loading state, PR header + abbreviated
  SHAs + safe external-link attributes, changed files with scope badges,
  rename old/new paths, outside-scope visibility, `ChangeSetResults` reuse,
  >3000 incomplete state, rate-limit and not-found/not-authorized error
  states, malformed repo / non-positive PR number rejected without an API call.
- **Final hardening pass (uncommitted): 73 tests** —
  `test_github_hardening.py`: strict upstream metadata validation matrix
  (base/head/SHA/ref/repo-full-name/changed_files malformed shapes →
  `malformed_github_response`, no raw `KeyError`/`ValueError`), fork and
  deleted-fork (`head.repo: null`) semantics, snapshot request identity
  (validated full names + exact SHAs, no branch/merge-SHA fallback, no
  fork-head reuse of the requested owner/repo), redirect policy matrix
  (trailing-dot hosts rejected, userinfo/HTTP/non-default ports rejected,
  uppercase accepted), and sanitized HTTP 422 responses on the GitHub
  request boundary (distinctive secrets in `token`/`authorization`/
  `api_base_url`/`github_url` never reflected; other endpoints keep
  FastAPI's established 422 output).
- Source inspection proves `GITHUB_TOKEN` and `Authorization` never appear in
  frontend product code; the browser only calls the local backend.
