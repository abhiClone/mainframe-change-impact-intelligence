# Contributing

This is a personal portfolio/demonstration project. External contributions
are not currently expected, but the conventions below apply to anyone
(including the author) working on the codebase.

## Design rules (non-negotiable)

1. **Determinism first.** Dependency discovery, impact analysis, test
   recommendation, risk signals, checklist generation, and incident
   relevance are pure deterministic functions. An LLM must never discover
   dependencies, calculate impact, select tests, create risk signals,
   select incidents, or modify verified deterministic results.
2. **Evidence is mandatory.** A dependency without file, line, and source
   statement text is not emitted. A UI claim without a deterministic
   source is not shown.
3. **Trust-boundary wording is load-bearing.** `VERIFIED IMPACT`,
   `DETERMINISTIC SUMMARY`, and `AI EXPLANATION` have precise meanings
   (see `docs/AI_GROUNDING.md`). Do not blur them in copy.
4. **Frozen baselines stay frozen.** Do not modify behaviour covered by a
   tagged baseline without explicit approval and a new baseline record.

## Development setup

See `docs/SETUP.md` for backend and frontend setup, and `docs/TESTING.md`
for the test suites.

## Before opening a change

- Backend: `.venv/bin/python -m pytest backend/tests/ -q` — all 166 tests must pass.
- Frontend: `cd frontend && npm test` (17 tests) and `npm run build` (tsc + vite).
- If you changed a rule, add or update a regression test that pins it.
- Update `CHANGELOG.md` and any affected `docs/` page.

## Commit conventions

- One logical change per commit; imperative commit messages
  (e.g. `Add Fit to view control to the dependency graph`).
- Documentation-only changes are marked with a `docs:` prefix.
- Do not commit generated artifacts (`frontend/dist/`, `__pycache__/`,
  `.venv/`, `node_modules/`) — they are gitignored.
