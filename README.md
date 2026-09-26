# Mainframe Change Impact & Release Intelligence Platform

A deterministic platform for answering *"what does changing this mainframe
component affect?"* — from dependency discovery through release readiness,
with historical incident intelligence and an optional grounded AI summary.

It provides:

- **deterministic dependency discovery** — COBOL/JCL/DB2 relationships
  extracted from source, every one citing file, line, and exact statement
- **change impact analysis** — direct + transitive dependents of any
  component, with dependency paths and evidence
- **involved DB2 resources** — tables read/written by impacted programs,
  kept strictly distinct from impacted components
- **deterministic regression test recommendations** — MUST_RUN / SHOULD_RUN
  from a validated test catalog, with rationale and evidence per test
- **release-risk signals** — deterministic rules (e.g. DB2 write involved,
  multi-job blast radius) with reasons and evidence
- **release checklist** — deterministic per-change checklist items with
  triggering rules
- **historical incident intelligence** — past incidents deterministically
  matched to the change (changed-component, direct, transitive,
  involved-write, involved-read), with severity kept separate from
  change relevance
- **optional grounded AI explanation** — an LLM may *summarise* the
  deterministic results; it can never alter them

## Architecture

```
Mainframe source (COBOL / JCL / PROC / copybooks / SQL)
        │
        ▼
deterministic parsers (regex-based, evidence-carrying)
        │
        ▼
dependency graph (NetworkX MultiDiGraph, in-memory, per process)
        │
        ▼
impact analysis (direct + transitive, dependency paths, evidence)
        │
        ▼
release intelligence (test recommendations, risk signals, checklist)
        │
        ▼
historical incident intelligence (validated incident dataset,
        deterministic relevance engine, five reason types)
        │
        ▼
optional AI explanation (grounded summary only)
```

**LLMs are not the source of truth** for dependencies, impact, test
selection, risk signals, or incident relevance. The AI layer receives a
one-way serialised context of already-computed deterministic results; its
output is guard-validated text placed only in the `ai_explanation` response
section. Identifiers are automatically grounded; AI prose remains
non-authoritative and deterministic evidence is the source of truth.

## Frozen baselines

| Phase | Scope | Commit | Tag |
|---|---|---|---|
| 1 | Deterministic dependency & change-impact engine | `dd154309275682c6c796baa558b4bab4b454ec7f` | `phase1-complete` |
| 2A | Release intelligence & test recommendation | `c705291` | `phase2a-complete` |
| 2B | Historical incident intelligence | `f697ae9` | `phase2b-complete` |

Phase 1 and Phase 2A logic are frozen: Phase 2B work is additive and does
not change dependency semantics, test-selection rules, or risk/checklist
rules.

## Prerequisites

Tested with:

- **Python 3.12** (verified on 3.12.3)
- **Node 24 / npm 10** for the frontend (verified on Node v24.20.0,
  npm 10.9.4)

Python dependencies are declared in `requirements.txt` with compatible
version constraints (lower bound = the verified stack, upper bound = next
major). The frontend's exact dependency tree is locked in
`frontend/package-lock.json`.

## Setup

```bash
git clone <repo-url> mainframe-impact
cd mainframe-impact

# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Backend tests (must pass: 166 passed, 0 failed)
.venv/bin/python -m pytest backend/tests/ -q
# or
./run_tests.sh

# 3. CLI analysis
.venv/bin/python analyze.py sample_mainframe
.venv/bin/python impact.py copybook:WARRCOPY

# 4. Start the backend API
./run_api.sh
# API at http://localhost:8000

# 5. Frontend (new terminal)
cd frontend
npm install
npm test        # frontend tests (9 passed)
npm run dev     # dev server, expects the API at http://localhost:8000
npm run build   # production build
npx vite preview  # serve the production build
```

No `.env` file is required. The backend is fully offline by default: no
network calls at runtime unless you explicitly configure the optional HTTP
AI provider (see "AI configuration" below).

## Main demo

### `copybook:WARRCOPY` — the primary scenario

Changing the WARRCOPY copybook demonstrates the whole product:

1. **Change impact** — direct: `program:WARR001`, `program:WARR002`;
   transitive: `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`, each with
   file/line/statement evidence.
2. **Involved DB2 resources** — `table:WARRANTY` (read and write, kept
   distinct) and `table:CLAIM_HISTORY` (write), used by the impacted
   programs. Involved is not impacted: the tables do not depend on the
   change.
3. **Test recommendations** — 7 deterministic recommendations
   (MUST_RUN/SHOULD_RUN by direct/transitive coverage), each with
   rationale and evidence.
4. **Release-risk signals & checklist** — deterministic rules with
   reasons and evidence (e.g. `DB2_WRITE_INVOLVED`).
5. **Historical incidents** — 11 deterministically relevant incidents,
   each with its relevance reason(s) and evidence; primary-tier counts
   are separated from all-reason counts, and historical severity is
   separated from current-change relevance.
6. **Explanation** — a DETERMINISTIC SUMMARY by default ("no LLM was
   involved"); an AI summary only appears when a genuine provider is
   configured and validated.

### `copybook:UNUSED` — the negative control

A copybook nothing references. The entire application stays quiet: 0
impacted components, 0 involved resources, 0 test recommendations, 0
risk signals, 0 checklist items, 0 relevant incidents — and no
fabricated narrative. This is the most important demo scenario after
WARRCOPY.

## UI views

The React + Vite frontend has five views:

1. **Repository Overview** — component counts and dependency totals.
2. **Dependency Explorer** — browse components and their relationships
   with evidence.
3. **Change Impact** — direct/transitive impact for a component id, with
   dependency paths.
4. **Graph** — interactive Cytoscape dependency graph; clicking any edge
   opens the Evidence Panel (relationship, source file, line number,
   exact source statement).
5. **Release Intelligence** — the full report: change summary, impacted
   components, involved DB2 resources, recommended tests, risk signals,
   release checklist, historical incidents, and the explanation section
   (labelled DETERMINISTIC SUMMARY or AI EXPLANATION).

VERIFIED data is visually distinct from AI-generated explanation;
historical severity is visually distinct from change relevance; impacted
components are distinct from involved resources.

## API

Phase 1 (frozen):

- `GET /api/components` — all components
- `GET /api/dependencies` — all dependencies with evidence
- `GET /api/graph` — full graph payload
- `GET /api/component/{id}` — one component (404 if unknown)
- `GET /api/impact/{id}` — direct/transitive impact with evidence
- `GET /api/summary` — repository summary

Phase 2A (frozen):

- `GET /api/intelligence/{id}` — full intelligence bundle: impact,
  recommended tests, risk signals, release checklist, incident
  intelligence, explanation
- `GET /api/test-recommendations/{id}` — deterministic test
  recommendations
- `GET /api/risk-signals/{id}` — deterministic risk signals
- `GET /api/test-catalog` — the 12-test synthetic catalog (validated
  against the Phase 1 graph at load time)

Phase 2B:

- `GET /api/incidents` — all 17 validated historical incidents
- `GET /api/incidents/{incident_id}` — one incident (404 if unknown)
- `GET /api/incident-intelligence/{id}` — deterministic incident
  relevance for a component, with per-reason evidence and
  `primary_tier_counts` / `reason_counts`

Unknown component ids return a controlled 404; malformed ids never
crash the server. Repeated calls are byte-identical (deterministic).

## AI configuration

The default is the **deterministic provider**: no credentials, no
network, `explanation_source: "deterministic"`, and the UI shows
DETERMINISTIC SUMMARY.

To use a remote LLM for the summary layer only:

```bash
INTELLIGENCE_PROVIDER=http
INTELLIGENCE_LLM_ENDPOINT=https://your-llm-host/v1/chat/completions
INTELLIGENCE_LLM_API_KEY=<your-key>
INTELLIGENCE_LLM_MODEL=<model-name>
```

See `.env.example` for the template. **Never commit real keys.**

Trust boundary:

- The provider receives only already-computed deterministic results.
- Its output is validated by the hallucination guard: unknown
  component/test/signal/incident ids, subject mismatch, or provider
  failure all fall back to the deterministic summary.
- `explanation_source` is `"deterministic"` or `"ai"` and the UI
  labels the section accordingly.
- There is no code path by which provider output can reach impacted
  components, test selection, test priorities, risk signals, the
  checklist, incident selection, or relevance reasons.

## Testing

```bash
.venv/bin/python -m pytest backend/tests/ -q   # 166 passed, 0 failed
cd frontend && npm test                         # 9 passed
```

Backend coverage: parser robustness (commented SQL, string-literal
traps), evidence integrity across all six relationship types,
deterministic test selection and MUST_RUN/SHOULD_RUN rules, risk
signals, checklist rules, incident dataset validation, all five
relevance reasons with precedence and primary-vs-all count semantics,
determinism across runs, AI hallucination guard (including incident-ID
grounding), and API contracts including 404s and curated error paths.

Frontend coverage: explanation provenance badges (DETERMINISTIC SUMMARY
vs AI EXPLANATION, never mislabelled), historical severity vs change
relevance, involved-vs-impacted DB2 resources, API error display,
loading state, and empty-input validation.

## Synthetic data

Everything under `sample_mainframe/` is hand-written synthetic data for
an imaginary automotive after-sales application: 5 COBOL programs,
4 copybooks, 3 JCL jobs, 2 PROCs, 4 DB2 tables, 30 dependencies,
a 12-test regression catalog, and 17 historical incidents. No
proprietary code, no external services.

## Known limitations

- 17 synthetic incidents only; no real ServiceNow/Jira integration.
- No semantic similarity or embeddings; incident relevance is purely
  deterministic from structured links and impact data.
- Involved resources are limited to DB2 READS_TABLE/WRITES_TABLE
  relationships.
- The HTTP LLM provider has not been live-tested against a paid API;
  AI prose is not fully fact-checked.
- Parsers are regex-based: unusual COBOL formatting, complex
  `EXEC SQL` joins/aliases, and dynamic `CALL`s are not resolved
  (dynamic calls are ignored rather than guessed).
- No CICS, IMS, MQ, GDG, or dataset dependencies.
- Impact paths report shortest chains only.
- The graph is built in memory per process (no database).
- The frontend has not been visually inspected in a browser during
  automated verification; only the production build and component
  tests are automated.

## Project layout

```
mainframe-impact/
├── sample_mainframe/      synthetic repo: cobol/, copybook/, jcl/, proc/,
│                          sql/, tests/test_catalog.yaml,
│                          incidents/incidents.yaml
├── backend/
│   ├── parsers/           deterministic COBOL/JCL/SQL parsers (Phase 1, frozen)
│   ├── graph/             MultiDiGraph + impact analyzer (Phase 1, frozen)
│   ├── intelligence/      impact context, test catalog, selector,
│   │                      risk signals, checklist (Phase 2A, frozen),
│   │                      incidents/ (Phase 2B), ai/ (grounded explanation)
│   └── api/               FastAPI routers
├── frontend/              React + Vite UI (five views)
├── docs/                  architecture, dependency/incident/test/risk models
├── analyze.py             CLI: repository summary
├── impact.py              CLI: change impact for a component
├── run_api.sh             start the backend
├── run_tests.sh           run the backend test suite
└── requirements.txt       Python dependencies (constrained versions)
```
