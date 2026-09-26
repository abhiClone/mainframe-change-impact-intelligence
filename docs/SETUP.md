# Setup

Detailed setup for local development and demo. For the short version, see the
Quick start in `README.md`.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 | Backend, CLI, tests |
| Node.js | 18+ | Frontend build/test/dev |
| npm | 9+ | Frontend dependencies |
| Browser | any modern | Interactive Cytoscape graph |

## Backend

```bash
# from the repository root
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` declares compatible version constraints (lower bound = the stack
verified by the frozen baselines, e.g. fastapi 0.141, networkx 3.7, pytest 9.1.1;
upper bound = next major). Transitive dependencies are left to pip's resolver.

Verify:

```bash
.venv/bin/python -m pytest backend/tests/ -q   # expect: 166 passed
```

Start the API:

```bash
./run_api.sh   # uvicorn backend.api.app:app on http://127.0.0.1:8000
```

The graph is built once at startup from `sample_mainframe/`. There is no database
to configure and no migration step.

### Optional: LLM explanation provider

The default provider is deterministic and needs no credentials. To use a remote
chat-completions LLM instead, copy `.env.example` to `.env` (gitignored) and set:

```bash
INTELLIGENCE_PROVIDER=http
INTELLIGENCE_LLM_ENDPOINT=https://your-llm-host/v1/chat/completions
INTELLIGENCE_LLM_API_KEY=...
INTELLIGENCE_LLM_MODEL=...
```

Never commit real keys. The HTTP provider has not been live-tested with a paid API
(see `docs/LIMITATIONS.md`). Any failure falls back to the deterministic provider.

## Frontend

```bash
cd frontend
npm ci            # reproducible install from package-lock.json
```

Verify:

```bash
npm test          # Vitest: 17 tests
npm run build     # tsc -b && vite build (expect a non-blocking Cytoscape chunk-size warning)
npm run dev       # Vite dev server on http://localhost:5173
```

The frontend calls the API at `http://localhost:8000` directly (see
`frontend/src/__tests__/App.test.tsx` for the configured base URL). Start the
backend first.

To serve the production build locally:

```bash
npm run build && npx vite preview --port 4173
```

## CLI

No extra setup — the CLI uses the same `.venv`:

```bash
.venv/bin/python analyze.py sample_mainframe
.venv/bin/python impact.py copybook:WARRCOPY
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pytest` fails with `ModuleNotFoundError: httpx` | Old checkout: reinstall with `pip install -r requirements.txt` (httpx is declared since the audit remediation) |
| Frontend shows API errors | Backend not running on `:8000` — start `./run_api.sh` first |
| `npm ci` fails | Node < 18 — upgrade Node |
| Port 8000 in use | Stop the other uvicorn instance, or change the port in `run_api.sh` |
