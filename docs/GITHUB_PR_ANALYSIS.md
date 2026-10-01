# GitHub Pull Request Analysis (Phase 3B)

Read-only GitHub integration that answers: **what is the Mainframe impact
of this actual pull request?**

```
GitHub PR
   │
   ▼
GitHub read-only provider (REST)
   ├── PR metadata (number, title, SHAs, file counts)
   ├── changed files (paginated, max 3000 — fail closed above)
   ├── base SHA ──▶ exact base snapshot (secure tarball materialization)
   └── head SHA ──▶ exact head snapshot (secure tarball materialization)
   │
   ▼
Secure snapshot materialization (temp dirs, extracted safely, cleaned up)
   │
   ▼
Phase 3A ChangeSet engine (frozen — reused, never reimplemented)
   │
   ▼
Deterministic release intelligence (+ optional grounded explanation)
```

**GitHub does not calculate impact.** GitHub is a change-source provider:
it supplies PR metadata, the changed-file list, and the exact base/head
repository snapshots. Component mapping, dependencies, impact, test
recommendations, priorities, DB2 involvement, risk signals, checklists,
and incident relevance are all determined by the frozen Phase 3A
deterministic engine, exactly as for explicit change sets. No parallel
GitHub-specific impact engine exists.

## GitHub REST API version

All requests pin the currently supported version, verified against the
official GitHub docs at implementation time:

- `X-GitHub-Api-Version: 2026-03-10`
- `Accept: application/vnd.github+json`
- `User-Agent: mainframe-change-impact-intelligence`

The client never relies on GitHub's unversioned defaults. The constant
lives in `backend/github/models.py` as `GITHUB_API_VERSION`.

## Authentication model

| Repository | Token |
|---|---|
| Public | Optional (`GITHUB_TOKEN` unset works, lower rate limit) |
| Private | Required, server-side |

Rules:

- Token source is **only** the `GITHUB_TOKEN` environment variable.
- The token is **never** accepted from a frontend form, query parameter,
  API request body, URL, or CLI argument (there is deliberately no
  `--token` flag).
- The token is **never** written to logs, tracebacks, exceptions, API
  responses, local caches, generated files, or screenshots.
- Fine-grained personal access tokens are preferred. Minimum expected
  permissions for the read-only feature set:
  - **Pull requests: read**
  - **Contents: read**
- GitHub write permission is never required and never requested.
- `GET /api/github/status` exposes only `auth_configured: true/false`
  — never the token, its prefix/length, scopes, or headers.

GitHub deliberately returns `404` for private repositories the caller
cannot access, so a missing repo and a missing permission share one
controlled state: `repository_not_found_or_not_authorized`, surfaced in
the UI as *"Repository or pull request was not found, or the configured
GitHub credentials do not have access."*

## What Phase 3B does not do

Read-only means read-only. Phase 3B never: posts PR comments, creates
check runs or commit statuses, blocks merges, uses webhooks, polls or
schedules monitoring, runs a GitHub Actions bot, writes to GitHub,
creates or modifies PRs, clones repositories with credentials, or talks
to GitLab/Bitbucket/ServiceNow/Jira. GitHub App / OAuth installation
flows are future deployment work; Phase 3B uses the server-side token
only and stays locally demoable.

## Request model

`POST /api/github/pull-request/analyze`

```json
{
  "owner": "abhiClone",
  "repo": "mainframe-change-impact-intelligence",
  "pull_number": 42,
  "source_root": "sample_mainframe"
}
```

Validation (all fail with HTTP 422 unless noted):

- `owner`: GitHub login shape (no URLs, no protocols).
- `repo`: repository name shape (no slashes, no URLs).
- `pull_number`: integer > 0.
- `source_root`: safe repository-relative path, default `"."`.
  Rejects `..`, absolute paths, Windows drive paths (`C:\…`), and UNC
  paths (`\\host\…`) — with `invalid_source_root` (HTTP 400 via the
  typed error path). Input-hardening bound: values longer than 1024
  characters are rejected (`SOURCE_ROOT_MAX_LENGTH`).
- The request model rejects unknown fields (`extra="forbid"`): a body
  that smuggles `token`, `api_base_url`, or similar fields fails
  validation (HTTP 422) instead of being silently ignored. Validation
  errors on this security-sensitive boundary are sanitized: the 422
  response carries only error location, type, and message — never the
  caller-supplied value — so a smuggled secret is not reflected back.
  Other endpoints keep FastAPI's established validation output.
- The GitHub API hostname never comes from user input: only
  `github.com` / `api.github.com` (+ the approved archive host below).
  GitHub Enterprise is future work.

## PR metadata

`GET /repos/{owner}/{repo}/pulls/{pull_number}` preserves: repository,
number, title, state, draft flag, `html_url`, author login, base
ref/SHA/repository, head ref/SHA/repository, changed-files/additions/
deletions counts, created/updated timestamps.

`merge_commit_sha` is **not** used: branch names move, so the analysis
is reproducible only against the exact `base.sha` / `head.sha` from the
PR. Both SHAs are returned in the final analysis.

### Strict upstream metadata validation

The GitHub response is treated as externally supplied data. Every field
that controls snapshot identity or repository selection is strictly
typed-validated before use; violations raise the typed
`malformed_github_response` error (HTTP 502), never a raw `KeyError` /
`ValueError` and never a silent substitution:

- `base.sha` / `head.sha` must be full 40-character lowercase
  hexadecimal commit SHAs. Branch names (`"main"`), short SHAs,
  traversal strings, and non-hex values are rejected. Phase 3B never
  substitutes a branch ref, a merge SHA, or current HEAD for an invalid
  SHA — snapshot identity is exact and content-addressed, or the
  analysis fails closed.
- `base.repo.full_name` / `head.repo.full_name` must be structurally
  valid `owner/repository` names (the same owner/repository semantics as
  the user's repository input). Malformed values (`../repo`,
  `owner/../repo`, URLs, `owner/repo/extra`, …) are rejected; these
  names are interpolated into API paths, so they must never alter the
  request host, URL path structure, query, or fragment.
- `base.ref` / `head.ref` must be non-empty, bounded, control-character
  free strings (display-only metadata; never used for snapshot
  identity).
- `base` / `head` / `base.repo` must be present objects;
  `changed_files` must be a genuine non-negative integer (missing,
  null, strings, floats, and negatives are rejected).
- `head.repo: null` is the legitimate GitHub case for a
  deleted/inaccessible fork: it is preserved, and the head snapshot is
  then fetched from the base repository addressed by the exact head
  SHA. If that SHA cannot be retrieved from the base repository, the
  analysis fails with `head_snapshot_unavailable` — the PR is not
  rejected merely because the fork is gone.

## Changed files

`GET /repos/{owner}/{repo}/pulls/{pull_number}/files` with
`per_page=100`, paginated via the `Link` header until complete. Per file:
`filename`, `previous_filename`, `status`, `additions`, `deletions`,
`changes`, `sha`. Patch text is not fetched and never used to infer
dependencies.

**3000-file hard limit.** GitHub's endpoint returns at most 3000 files.
If PR metadata reports `changed_files > 3000`, Phase 3B returns
`incomplete_change_set` ("GitHub file-list API limit exceeded") and
produces **no** impact intelligence from a knowingly partial list.
Unexpected pagination incompleteness (fewer files than advertised) also
fails closed.

### Status translation

| GitHub | Phase 3A |
|---|---|
| `added` | `added` |
| `modified` | `modified` |
| `removed` | `deleted` |
| `renamed` | `renamed` (`filename` → new path, `previous_filename` → old path) |

Any other GitHub status raises `unsupported_github_status` — it is never
silently converted to `modified`. The original GitHub status is always
preserved on the file record for provenance.

## Source root & scope

A repository may hold many non-Mainframe files. `source_root` selects
the Mainframe subtree (e.g. `sample_mainframe`). Every PR file is
classified:

- `in_source_scope` — enters Phase 3A analysis with its path translated
  to source-relative form (`sample_mainframe/copybook/WARRCOPY.cpy` →
  `copybook/WARRCOPY.cpy`). The original GitHub path is preserved.
- `outside_source_scope` — stays visible in the PR report but never
  enters Phase 3A analysis. `README.md` is never rewritten into
  `../README.md` and pushed through the mapper.

### Rename across the source-root boundary

| Case | Mainframe treatment | GitHub provenance |
|---|---|---|
| inside → inside | `renamed` (both paths source-relative) | `renamed` |
| outside → inside | `added` (new path) | `renamed` preserved |
| inside → outside | `deleted` (old path) | `renamed` preserved |
| outside → outside | not analyzed | visible as `outside_source_scope` |

## Snapshots

Changed files alone are not enough: unchanged files can depend on
changed files. Phase 3B materializes the **full base and head source
snapshots at the exact PR SHAs** via `GET /repos/{owner}/{repo}/tarball/{sha}`.

- **Fork PRs:** the base snapshot downloads from the *base* repository
  and the head snapshot from the *head* repository — never assumed
  equal. If `head.repo` is null (deleted fork), the only deterministic
  fallback is fetching the exact head SHA from the base repository
  (content-addressed, never guessed); otherwise `head_snapshot_unavailable`.
- **Same SHA:** within one analysis a repeated `(repo, SHA)` is
  downloaded once and reused; nothing is cached persistently (no private
  source on disk after the request).
- Snapshots materialize under secure temporary directories and are
  deleted after analysis — never committed, never placed under the
  project repo, `frontend/public/`, logs, or screenshots.

### Archive security (HIGH priority)

Before any byte touches the filesystem, every member is pre-scanned;
extraction then uses `tarfile`'s `data` filter as defense-in-depth, and
the materialized tree is re-verified:

- rejects `..` traversal, absolute paths, Windows drive/UNC paths
  (backslashes treated as separators);
- rejects symlinks, hard links, device files, FIFOs/sockets and other
  special objects — before materialization;
- every extracted path must resolve under the intended temporary root
  (tar-slip / zip-slip guard);
- resource limits (configurable, documented defaults):
  - max archive download: 100 MiB
  - max extracted bytes: 256 MiB
  - max files: 50,000
  - max individual file: 20 MiB
- exceeding a limit raises `snapshot_too_large` — archives are never
  silently truncated.

### Redirect / token safety

GitHub's archive endpoint answers `302`. The client handles it manually:

1. authenticated request to the trusted GitHub API;
2. read the redirect; require HTTPS, the default HTTPS port, **no URL
   userinfo of any kind** (username/password — httpx would otherwise
   synthesize an `Authorization: Basic` header from it at send time),
   **no trailing-dot host**, and an approved GitHub-controlled host
   (`codeload.github.com`, compared by exact hostname after case
   normalization only, never `endswith`);
3. fetch the archive **without** forwarding `GITHUB_TOKEN` — verified
   against the final request as received by the transport (not only the
   pre-send request object), for every redirect status
   (301/302/303/307/308), covering `Authorization` and
   `Proxy-Authorization`.

A redirect to any other host, any non-HTTPS scheme, any non-default
port, any trailing-dot host, or any target containing userinfo is
rejected (`snapshot_download_failed`). Tests prove the `Authorization`
header is present on the API request and absent on the archive-host
request.

**Archive host policy (fail-closed).** GitHub's REST archive endpoint
returns a redirect; Phase 3B accepts only the explicitly audited
destination `codeload.github.com` (`api.github.com` for same-origin API
redirects). GitHub does not document a fixed archive redirect host, so
this is Phase 3B's own explicit allowlist — it is deliberately not
broadened for theoretical compatibility. If GitHub changes archive
delivery hosts in the future, analysis fails closed until the new host
is reviewed and added.

## Phase 3A integration

`GitHubPullRequestProvider` (a Phase 3A `ChangeSetProvider`) feeds the
frozen `ChangeSetAnalyzer`:

- reuses file→component mapping, multi-root analysis, changed/downstream
  separation, cross-impact, root/snapshot provenance, rename semantics,
  deterministic test aggregation, DB2/resource/risk/checklist/incident
  aggregation, and the AI guard — none duplicated;
- deleted files and rename old-paths resolve against the materialized
  base snapshot via the provider's containment-checked
  `read_base_source_file`.

**Strongest invariant (release-blocking test):** a GitHub PR resolving to
the same change set as Phase 3A explicit input, with equivalent
snapshots, yields semantically identical `ChangeSetIntelligence`,
excluding GitHub-specific metadata. The mocked primary test
(`WARRCOPY` + `WARR002` modified) asserts the verified Phase 3A numbers:
2 changed components, 1 cross-impacted, 4 downstream, 3/3/3 direct/
transitive/overlap unions, 7 tests (6 MUST_RUN / 1 SHOULD_RUN), 1 DB2
READ / 2 WRITE, 7 risk signals, 7 checklist items, 11 incidents.

## Result model

`GitHubPullRequestAnalysis`:

- `provider`, `repository`, `pull_request` (metadata), `source_root`
- `github_files` (all, with provenance), `in_scope_files`,
  `outside_scope_files`
- `base_snapshot`, `head_snapshot` (repo, SHA, file/byte counts)
- `change_set_intelligence` — the Phase 3A result, embedded intact
- `rate_limit` — safe operational metadata only

Per-file GitHub provenance answers *"which exact PR file caused this
changed component?"*: GitHub path, previous path, GitHub status, base
SHA, head SHA, source-relative path, mapped component(s), Phase 3A
snapshot.

## Rate limits & retries

`x-ratelimit-limit/remaining/reset/resource` are captured from every
response and exposed (unobtrusively in the UI) as operational metadata —
never mixed into technical risk.

Rate-limit classification is deterministic:

- `429` → `github_rate_limited`;
- `403` with `x-ratelimit-remaining: 0` (primary rate limit) →
  `github_rate_limited` (with reset time);
- `403` with a `Retry-After` header (GitHub's documented
  secondary/abuse rate-limit signal) → `github_rate_limited`, even when
  no primary rate-limit header is present;
- an ordinary permission `403` (no rate-limit signal) stays
  `repository_not_found_or_not_authorized`.

The client does not hammer GitHub and does not retry-until-reset in this
phase.

Bounded retries (max 2, exponential backoff) apply only to transient
`500/502/503/504` and network timeouts. `401/403/404/422/429` are never
retried.

## Error model

Typed, controlled errors (no raw GitHub bodies, no secrets):

`repository_not_found_or_not_authorized`, `pull_request_not_found`,
`github_authentication_failed`, `github_rate_limited`,
`github_unavailable`, `malformed_github_response`,
`incomplete_change_set`, `unsupported_github_status`,
`snapshot_download_failed`, `snapshot_too_large`, `unsafe_archive`,
`invalid_source_root`, `head_snapshot_unavailable`, `analysis_failed`.

`malformed_github_response` covers upstream schema violations —
non-integer or negative counts (`additions`, `deletions`, `changes`,
`changed_files`), non-integer PR numbers — converted deterministically
into a typed error (HTTP 502) instead of a raw `ValueError`/HTTP 500.
No wrong deterministic analysis is ever produced from malformed input.

PR workflow metadata (comment counts, age, author tenure, draft state,
commit counts) is displayed when useful but never mixed into technical
release risk.

## CLI

```
python github_pr.py --repo owner/name --pr 42 --source-root sample_mainframe [--json] [--no-test-catalog]
```

Token from `GITHUB_TOKEN` only. Human output prints the PR header
(repository, number/title/state, author, base/head refs + short SHAs,
html_url), changed files with scope badges, snapshot provenance, then
the deterministic ChangeSet sections and summary. `--json` prints the
full typed result.

## UI

Seventh view: **GitHub PR**. Inputs for repository (`owner/repo`), PR
number, and Mainframe source root; no token field. Shows a neutral
"GitHub authentication configured" badge (server status only), the PR
header with a safe external link, the changed-file list (GitHub status
vs mapping status kept distinct, IN SCOPE / OUTSIDE SOURCE ROOT
badges, rename old→new), then the shared `ChangeSetResults` component
for the deterministic intelligence. Trust label: **VERIFIED PR CHANGE
SET** — the file list came deterministically from GitHub PR metadata;
it does not claim GitHub verified business correctness. All error
states from the error model are handled without stack traces. The
browser only ever talks to the local backend — GitHub interaction is
server-side (verified via network inspection).

## AI boundaries

The optional explainer receives only the deterministic
`ChangeSetIntelligence` as its factual source. Phase 3B does **not**
send PR title, author, PR number, repository metadata, raw patch text,
archive URLs, the token, or repository snapshot contents to the AI
provider. Changed component/file identifiers reach the explanation layer
only insofar as they are already part of the deterministic Phase 3A
change-set intelligence. The LLM never infers impact from PR title/body,
commit messages, author, comments, or patch text. Source-graph evidence
remains authoritative (a PR body saying "this affects WARRANTY" creates
no `table:WARRANTY` impact).

## Limitations

- GitHub.com only (no GitHub Enterprise yet).
- REST file-list maximum: 3000 files (fail-closed above).
- Synchronous analysis; snapshot download required per analysis.
- No webhooks, PR comments, check runs, merge blocking, GitHub App /
  OAuth installation, or background monitoring.
- Private repositories need the server-side token.
- Archive size/file limits (see above).
- Inherits Phase 1 parser coverage limitations.

## Testing

All automated tests are mocked (`httpx.MockTransport`, in-test-built
archives) — no test depends on live GitHub, CI, or network. Suites:
client (headers, auth, pagination, 3000-boundary, error mapping,
retries, redirect token safety), snapshots (traversal, absolute paths,
symlinks, hard links, devices, FIFOs, all resource limits),
source-scope (validation, scope classification, all four rename
boundaries), equivalence (release-blocking), API (endpoint + full error
mapping + status), CLI (flags, output, token absence), frontend
(GitHubPRView rendering, states, errors, no token field).
