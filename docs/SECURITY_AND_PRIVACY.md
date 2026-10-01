# Security and Privacy

## Data policy

**All mainframe source, test cases, and historical incidents in `sample_mainframe/`
are synthetic demonstration data**, authored for this project. They contain no
employer or client production code or data. Incident narratives, SQLCODEs, abends,
dates, and component names are invented. No personal data is present anywhere in the
repository.

## Secrets

- The only credential surface is the optional LLM provider, configured exclusively
  via environment variables: `INTELLIGENCE_PROVIDER`, `INTELLIGENCE_LLM_ENDPOINT`,
  `INTELLIGENCE_LLM_API_KEY`, `INTELLIGENCE_LLM_MODEL`.
- Phase 3B (unreleased) adds a second credential surface: `GITHUB_TOKEN`, also
  configured exclusively via the server environment — never via a CLI flag
  (none exists), API request body, query parameter, URL, or browser form.
  It is never written to logs, tracebacks, exceptions, API responses, local
  caches, generated files, or screenshots.
- `.env.example` is committed as documentation; a real `.env` is gitignored and
  must never be committed.
- The default provider (`deterministic`) needs no credentials and makes no network
  calls. A remote LLM is never instantiated unless explicitly configured.
- A public-release safety scan is part of the publication checklist (see below);
  it covers API keys, tokens, `.env` files, credentials, passwords, private URLs,
  personal data, proprietary code/data, local absolute paths, and stray
  audit/debug artifacts.

## Network posture

- The FastAPI backend binds `127.0.0.1:8000` by default — local demonstration only.
  Do not expose it to untrusted networks without adding authentication (none is
  built in; this is a demo, not a production service).
- The frontend calls the API directly from the browser; no secrets are shipped to
  the client (there are none to ship — the API key, if configured, stays
  server-side in the environment).
- Phase 3B (unreleased): all GitHub interaction is server-side. The browser
  only ever calls the local backend; the frontend never contacts
  `api.github.com` or `codeload.github.com` (the only GitHub URL in the UI is
  the user-clicked "View on GitHub" link).

## AI-layer privacy

The strict provider input (`IntelligenceContext`) contains only serialized
deterministic artifacts — component ids, paths, evidence refs, test/signal/checklist
summaries, incident summaries. No repository paths, no raw source text. If a remote
LLM is configured, only this bounded context leaves the machine.

## GitHub PR adapter (Phase 3B, unreleased)

- **Token handling.** `GITHUB_TOKEN` is read only from the server environment.
  It is never accepted from a CLI flag (none exists), API request body, query
  parameter, URL, or browser form; never written to logs, tracebacks,
  exceptions, API responses, local caches, generated files, or screenshots.
  `GET /api/github/status` exposes only `auth_configured`.
- **Archive safety.** Every archive member is pre-scanned before extraction:
  traversal, absolute paths, Windows drive/UNC paths, symlinks, hard links,
  device files, and FIFOs are rejected; extraction is contained to the
  temporary root (tar-slip/zip-slip guard); byte and file-count limits are
  enforced (`snapshot_too_large` on breach, never silent truncation).
- **Redirect handling.** GitHub's archive endpoint answers `302`; the client
  handles it manually: the redirect target must be HTTPS on the default
  port, contain **no URL userinfo** (username/password — httpx would
  otherwise synthesize an `Authorization: Basic` header from it at send
  time), contain **no trailing-dot host**, and sit on an approved
  GitHub-controlled host (`codeload.github.com`, exact hostname
  comparison after case normalization only), and the archive is fetched
  **without** forwarding `GITHUB_TOKEN` — verified against the final
  request as received by the transport for 301/302/303/307/308. Any
  other host, any non-HTTPS scheme, any non-default port, any
  trailing-dot host, or any userinfo-bearing target is rejected
  (`snapshot_download_failed`). The host allowlist is explicit and
  fail-closed: GitHub documents no fixed archive redirect host, so if
  delivery hosts change, analysis fails closed until the new host is
  reviewed and added.
- **Upstream metadata validation.** The GitHub PR response is treated as
  externally supplied data: `base.sha`/`head.sha` must be full
  40-character hex commit SHAs, `base.repo.full_name`/`head.repo.full_name`
  must be structurally valid `owner/repository` names, and malformed
  values raise the typed `malformed_github_response` error — never a
  silent branch/merge-SHA substitution.
- **Sanitized request validation.** On the GitHub request boundary,
  HTTP 422 validation errors carry only error location, type, and
  message — never the caller-supplied value — so a smuggled `token`
  field is not reflected in the response.
- **No ambient proxy inheritance.** The client is constructed with
  `trust_env=False`, so environment proxy configuration (and any credentials
  in it) is never inherited into GitHub-bound requests.
- **Temporary materialization.** Snapshots extract to secure temporary
  directories and are deleted after the request — never committed, never
  placed under the project tree or `frontend/public/`, never logged.

## Dependencies

- Python dependencies are declared with compatible version constraints in
  `requirements.txt`; frontend dependencies are pinned in
  `frontend/package-lock.json`.
- CI runs the full test suites on every push and pull request
  (`.github/workflows/ci.yml`).

## Reporting

See `SECURITY.md` for the vulnerability reporting policy.
