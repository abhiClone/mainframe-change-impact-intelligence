# API Reference

Base URL: `http://127.0.0.1:8000` (see `./run_api.sh`). All responses are JSON.
Component ids use the `"<kind>:<NAME>"` form (e.g. `copybook:WARRCOPY`).

## Error contract

| Situation | Response |
|---|---|
| Unknown component id | HTTP 404 with a clear message (same contract across all `{component_id}` endpoints) |
| Unknown incident id | HTTP 404 |
| Corrupted incident dataset / test catalog | HTTP 500 naming the problem (fail loud, never silent) |
| GitHub adapter errors (`/api/github/*`) | HTTP status per the typed mapping below, with body `{"detail": {"code": "<code>", "message": "<safe message>"}}` — no raw GitHub bodies, no secrets, no tracebacks |

## Endpoints

### `GET /api/summary`

Repository counts: component totals by type and total dependency count.

### `GET /api/components`

All 18 components: `id`, `name`, `type`, `source_file`.

### `GET /api/dependencies`

All 30 dependencies: `source`, `target`, `relationship`, `evidence{file, line, text}`.

### `GET /api/graph`

Nodes + edges shaped for the Cytoscape UI (parallel edges preserved as independent elements).

### `GET /api/component/{component_id}`

One component with its upstream (dependencies) and downstream (dependents) neighbourhoods.

### `GET /api/impact/{component_id}`

Change-impact analysis: `direct_impacts`, `transitive_impacts`, `dependency_paths`
(each path a list of edges with evidence), and `evidence` refs.

Example: `GET /api/impact/copybook:WARRCOPY` →
2 direct, 3 transitive, 6 paths. `GET /api/impact/copybook:UNUSED` → all empty.

### `GET /api/intelligence/{component_id}`

The full release-intelligence bundle:

```json
{
  "impact_context": { "changed_component": "...", "direct_impacts": [...], "...": "..." },
  "involved_resources": [ { "component_id": "table:WARRANTY", "access": "write", "evidence": {...} } ],
  "test_recommendations": [ { "test_id": "TC-WARR-002", "impact_level": "MUST_RUN", "rationale": "...", "evidence": [...] } ],
  "risk_signals": [ { "id": "DB2_WRITE_INVOLVED", "severity": "high", "...": "..." } ],
  "release_checklist": [ { "item_id": "CHK-DB2-WRITE", "rule": "db2_write_involved", "...": "..." } ],
  "incident_intelligence": { "total_relevant_incidents": 11, "incidents": [...], "primary_tier_counts": {...}, "reason_counts": {...} },
  "explanation": { "executive_summary": "...", "explanation_source": "deterministic" }
}
```

### `GET /api/test-recommendations/{component_id}`

Recommended tests only (same `RecommendedTest` objects as the bundle).

### `GET /api/risk-signals/{component_id}`

Risk signals only.

### `GET /api/test-catalog`

The 12-test catalog: `id`, `name`, `type`, `covers[]`, `execution.job`, `description`.

### `GET /api/incidents`

All 17 historical incidents (full records).

### `GET /api/incidents/{incident_id}`

One incident by id (404 if unknown).

### `GET /api/incident-intelligence/{component_id}`

Relevant incidents with deterministic reasons: `incidents[]` (each with `reasons[]`
and `primary_reason`), `total_relevant_incidents`, `primary_tier_counts`,
`reason_counts`.

### `POST /api/change-set/analyze`

Change-set (release candidate) analysis. The request supplies changed-file
metadata only — the API never accepts repository or filesystem paths:

```json
{
  "files": [
    {"path": "copybook/WARRCOPY.cpy", "status": "modified"},
    {"path": "cobol/WARR002.cbl", "status": "modified"}
  ],
  "resolutions": {"sql/schema.sql": ["table:WARRANTY"]},
  "fake_ai": false
}
```

Statuses: `modified` (default), `added`, `deleted`, `renamed`. Returns the
full `ChangeSetIntelligence`: file→component mapping (mapped / ambiguous
with candidates / unmapped / requires_base_snapshot), per-change analysis,
`changed_components` (explicit roots, disjoint from downstream impact,
with cross-impact and snapshot provenance), deduplicated downstream
union with root and snapshot provenance, overlap detection,
`mixed_snapshot_analysis`, `summary`, `deterministic_summary`, and
`ai_explanation` (`explanation_source`: `deterministic` | `ai`).
Ambiguous files with no resolution contribute no impact — nothing is
auto-selected. Invalid resolutions return HTTP 400; malformed payloads
return HTTP 422. Duplicate `(path, old_path, status)` entries are
deduplicated; conflicting statuses for one path are rejected (400).

### `POST /api/github/pull-request/analyze` (Phase 3B, unreleased)

Read-only GitHub PR analysis. The request identifies the PR and the Mainframe
subtree — the token is **never** accepted via the API (server-side
`GITHUB_TOKEN` only):

```json
{
  "owner": "abhiClone",
  "repo": "mainframe-change-impact-intelligence",
  "pull_number": 42,
  "source_root": "sample_mainframe"
}
```

Validation: `owner` (GitHub login shape, no URLs), `repo` (name shape, no
slashes/URLs), `pull_number` (integer > 0), `source_root` (safe
repository-relative path, default `"."`; rejects `..`, absolute paths,
Windows drive/UNC paths, and values over 1024 characters). Unknown
request fields are rejected (`extra="forbid"`). Malformed payloads
return HTTP 422; an unsafe `source_root` returns HTTP 400
(`invalid_source_root`). On this security-sensitive boundary, HTTP 422
validation errors are sanitized: the response carries only error
location, type, and message — never the caller-supplied value — so a
smuggled field such as `token` is not reflected back. Other endpoints
keep FastAPI's established validation output.

Returns `GitHubPullRequestAnalysis`: `provider`, `repository`, `pull_request`
(number, title, state, draft, `html_url`, author, base/head refs + exact SHAs
+ repositories, file counts), `source_root`, `github_files` (every PR file with
GitHub status, previous path, additions/deletions, `in_source_scope` /
`outside_source_scope`, effective Phase 3A status, mapping status, mapped
components, snapshot provenance), `in_scope_files`, `outside_scope_files`,
`base_snapshot` / `head_snapshot` (repository, SHA, file/byte counts),
`change_set_intelligence` (the Phase 3A result, embedded intact), and
`rate_limit` (safe operational metadata only).

Known-error mapping (body `{"detail": {"code", "message"}}`):

| Code | HTTP | Meaning |
|---|---|---|
| `repository_not_found_or_not_authorized` | 404 | Unknown repo, or the configured credentials cannot access it (deliberately indistinguishable) |
| `pull_request_not_found` | 404 | No such PR in the repository |
| `github_authentication_failed` | 401 | Token rejected by GitHub |
| `github_rate_limited` | 429 | Primary (403 `x-ratelimit-remaining: 0`), secondary (403 + `Retry-After`), or 429 rate limit; `message` carries the reset time; not retried |
| `github_unavailable` | 502 | GitHub unreachable or repeated 5xx after bounded retries |
| `malformed_github_response` | 502 | Upstream schema violation (non-integer/negative counts, non-integer PR number, invalid commit SHAs, malformed refs, malformed repository full names, missing base/head objects) — typed, never a raw `ValueError` |
| `incomplete_change_set` | 422 | PR changes > 3000 files, or pagination incomplete — no partial-list analysis is produced |
| `unsupported_github_status` | 422 | Unknown file status from GitHub — never silently converted |
| `snapshot_download_failed` | 502 | Tarball fetch failed, or the archive redirect pointed at a non-approved host, used userinfo, used a non-default port, or used a trailing-dot host |
| `snapshot_too_large` | 413 | Archive exceeded the download/extraction/file-count limits — never silently truncated |
| `unsafe_archive` | 422 | Archive member failed the security pre-scan (traversal, symlink, device, …) |
| `invalid_source_root` | 400 | Unsafe `source_root` value (traversal, absolute path, or over 1024 characters) |
| `head_snapshot_unavailable` | 422 | Head SHA cannot be fetched (e.g. deleted fork with no deterministic fallback) |
| `analysis_failed` | 500 | Frozen Phase 3A analysis raised unexpectedly |

### `GET /api/github/status` (Phase 3B, unreleased)

```json
{"provider": "github", "auth_configured": true}
```

Reports only whether a server-side `GITHUB_TOKEN` is configured — never the
token, its prefix/length, scopes, or headers.

## Notes for integrators

- The graph is built once at API startup from `sample_mainframe/`; it is in-memory
  and per-process.
- All endpoints are deterministic: identical requests return identical responses.
- The `explanation.explanation_source` field (`deterministic` | `ai`) is authoritative;
  render badges from it, never from text parsing.
- `reason_counts` may exceed `total_relevant_incidents` (secondary reasons preserved);
  `primary_tier_counts` sums to the total.
