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

## AI-layer privacy

The strict provider input (`IntelligenceContext`) contains only serialized
deterministic artifacts — component ids, paths, evidence refs, test/signal/checklist
summaries, incident summaries. No repository paths, no raw source text. If a remote
LLM is configured, only this bounded context leaves the machine.

## Dependencies

- Python dependencies are declared with compatible version constraints in
  `requirements.txt`; frontend dependencies are pinned in
  `frontend/package-lock.json`.
- CI runs the full test suites on every push and pull request
  (`.github/workflows/ci.yml`).

## Reporting

See `SECURITY.md` for the vulnerability reporting policy.
