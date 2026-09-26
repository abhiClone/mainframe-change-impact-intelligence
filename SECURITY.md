# Security Policy

## Supported versions

This repository is a demonstration project. Security fixes are applied to
the latest commit on the default branch.

## Reporting a vulnerability

Please report security vulnerabilities using GitHub's private
vulnerability reporting feature for this repository. Describe the
affected component, the impact, and reproduction steps. You will receive
an acknowledgement and a plan for a fix. Do not open a public issue for
a security concern.

If private vulnerability reporting is not available on this repository,
please use the maintainer's public GitHub profile to make private
contact instead. Never include private contact details or credentials
in a public issue or pull request.

## Security-relevant design notes

- **No secrets in the repository.** LLM access (optional, off by default)
  is configured exclusively via environment variables
  (`INTELLIGENCE_PROVIDER`, `INTELLIGENCE_LLM_ENDPOINT`,
  `INTELLIGENCE_LLM_API_KEY`, `INTELLIGENCE_LLM_MODEL`). See `.env.example`.
  Real keys live in the environment or a local uncommitted `.env`, never
  in git history.
- **Synthetic data only.** The bundled `sample_mainframe/` repository,
  test catalog, and 17 historical incidents are synthetic demonstration
  data. They contain no employer/client production code or data.
- **Deterministic default.** The default AI provider is deterministic and
  requires no network access and no credentials. A remote LLM is never
  instantiated unless explicitly configured.
- **No authentication on the demo API.** The FastAPI backend is intended
  for local demonstration (`127.0.0.1:8000`). Do not expose it to
  untrusted networks without adding authentication.
- **Dependency hygiene.** Python dependencies are declared with compatible
  version constraints in `requirements.txt`. Frontend dependencies are
  pinned in `frontend/package-lock.json`.

See `docs/SECURITY_AND_PRIVACY.md` for the full discussion.
