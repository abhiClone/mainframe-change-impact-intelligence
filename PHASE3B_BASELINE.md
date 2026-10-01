# Phase 3B Baseline — GitHub Pull Request Impact Analysis

## Phase 3B
GitHub Pull Request Impact Analysis

## Base
`14187c9660d3a38d90697acf2fcc23f10e5070e5` (Phase 3A / v1.1.0 public release)

## Verification at freeze (2026-10-01)
- Backend tests: **499 passed**, 0 failed
- Frontend tests: **49 passed**, 0 failed
- Production build: **passed** (only the pre-existing chunk-size warning)
- Chromium (Chrome for Testing 153.0.8010.12 via Playwright, same-host, `--no-proxy-server`):
  - 1440x900: PASS
  - 1280x800: PASS
  - 900x800: PASS
- Phase 3A equivalence: **PASS** (mocked GitHub PR WARRCOPY + WARR002
  semantically identical to explicit Phase 3A WARRCOPY + WARR002)
- Final acceptance audit verdict (2026-10-01): **PASS — READY TO FREEZE**
  (HIGH findings: 0; correctness/security MEDIUM findings: 0)

## Architecture
```
GitHub PR
    ↓
read-only GitHub provider
    ↓
PR metadata + changed files
    ↓
exact base/head SHA snapshots
    ↓
secure snapshot materialization
    ↓
Phase 3A ChangeSet engine
    ↓
deterministic impact intelligence
```

## Phase 3B capabilities
- GitHub.com PR analysis
- Read-only GitHub REST integration
- Public repo support
- Optional server-side token for private repos
- Exact base/head SHA analysis
- Same-repository PRs
- Fork PRs
- Deleted-fork handling (exact head SHA fetched from base repo; deterministic
  `head_snapshot_unavailable` when unrecoverable)
- PR changed-file pagination
- 3000-file fail-closed behavior (partial lists are never analyzed)
- Added / modified / deleted / renamed mappings
- Source-root scoping
- Rename crossing source-root boundaries
  (inside→inside = renamed, outside→inside = effective added,
   inside→outside = effective deleted, outside→outside = excluded from Phase 3A)
- Secure archive download
- Secure archive extraction
- Archive traversal protection
- Symlink/hardlink/special-file rejection
- Archive resource limits (download streaming limit, per-file limit,
  extracted-size limit, file-count limit)
- Credential-safe redirect handling (Authorization never reaches the archive
  request; validated explicit allowlist; userinfo/trailing-dot/non-default-port
  rejected)
- Deterministic Phase 3A reuse
- GitHub-specific provenance
- CLI (`github_pr.py`)
- API (`/api/github/pull-request/analyze`, `/api/github/status`)
- Seventh GitHub PR UI view
- Rate-limit handling (primary, secondary, 429 → typed `github_rate_limited`;
  bounded retries only for transient 5xx and timeout/network failure)
- Typed GitHub errors (`malformed_github_response`, `pull_request_not_found`,
  `github_authentication_failed`, `github_rate_limited`,
  `snapshot_download_failed`, `unsafe_archive`, `snapshot_too_large`,
  `incomplete_change_set`, `head_snapshot_unavailable`, `github_unavailable`)

## Core invariant
GitHub identifies the change set.

GitHub does NOT calculate impact.

AI does NOT calculate impact.

Phase 3A remains authoritative for:
- mapping
- dependencies
- impact
- tests
- test priorities
- resources
- risks
- checklist
- historical incidents

## Security guarantees
- GITHUB_TOKEN is server-side only.
- No token field exists in the frontend.
- No token CLI argument exists.
- Browser never contacts GitHub APIs directly.
- Archive redirects do not receive Authorization.
- Userinfo redirects are rejected.
- Trailing-dot hosts are rejected.
- Non-default HTTPS ports are rejected.
- GitHub archive hosts use an explicit allowlist.
- Repository snapshots are temporary.
- Unsafe archives fail closed.
- Partial PR file lists are never analyzed.

## Accepted limitations
- GitHub.com only
- No GitHub Enterprise
- trust_env=False / no ambient proxy support
- Synchronous analysis
- 3000-file GitHub REST limit
- Explicit archive-host allowlist may require future maintenance
- Uppercase hexadecimal SHA rejected (GitHub normally supplies lowercase SHAs)
- No GitHub writes
- No comments/check runs
- No GitHub App/OAuth
- No persistent source caching
- Inherited Phase 1 parser limitations

(These are accepted, documented limitations — not defects.)
