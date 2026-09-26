# Demo Guide

A 10-minute interview/demo script. Start the API (`./run_api.sh`) and the frontend
(`cd frontend && npm run dev`), then open http://localhost:5173.

## 0. Frame the problem (30s)

"Mainframe change-impact analysis has to be trustworthy: every claimed relationship
must trace to a real source statement, and no step may hallucinate. This platform
proves a deterministic core and an optional AI layer can coexist — the AI can never
alter the core's results."

Point at the header: **Deterministic Mainframe Change Impact & Release Intelligence**.

## 1. Repository Overview (1 min)

Show the scan counts: 5 COBOL programs, 4 copybooks, 3 JCL jobs, 2 PROCs, 4 DB2 tables,
**30 dependency edges** — all from parsing real (synthetic) source. Note the footer:
"No LLM, no external services."

## 2. Change Impact — `copybook:WARRCOPY` (2 min)

The canonical scenario. Show: 2 direct impacts (`program:WARR001`, `program:WARR002`),
3 transitive impacts (`job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`), 6 dependency
paths. Click a path edge to open the **Evidence Panel** — file, line, exact statement
(`cobol/WARR001.cbl:15` — `COPY WARRCOPY.`), plus the no-inference message.

Ask the room: "which batch jobs run the affected programs?" — then point at the paths.

## 3. Graph (2 min)

The full dependency graph. Click **Fit to view** / **Reset view**. Then the money
shot: zoom to `WARR001 → WARRANTY` and show the **two independent curves** —
`READS_TABLE` and `WRITES_TABLE` — click each one and show that each opens its own
evidence (`FROM WARRANTY` vs `INSERT INTO WARRANTY`). "A plain directed graph would
collapse these into one edge and lose the read/write distinction."

Explain the arrow semantics: **A → B means A depends on B**; impact flows backwards.

## 4. Release Intelligence — `copybook:WARRCOPY` (3 min)

Walk the bundle top to bottom:

- **Change Summary** — `VERIFIED IMPACT` badge (deterministic).
- **Involved DB2 resources** — tables the impacted programs read/write, explicitly
  "involved in the change, not impacted by it".
- **Test recommendations (7)** — read one rationale aloud; point out it cites a
  file and line. `MUST_RUN` vs `SHOULD_RUN` is a deterministic rule, not a model.
- **Risk signals (7)** — `DB2_WRITE_INVOLVED` is `high`: "a defect here can corrupt
  persistent data". No probabilities are claimed anywhere.
- **Release checklist (7)** — each item cites its rule.
- **Historical incidents (11 of 17)** — each with a deterministic reason; point out
  severity is rendered separately from relevance.
- **Explanation** — `DETERMINISTIC SUMMARY` badge. "With no LLM configured, you still
  get a complete grounded summary. The AI layer is optional and guard-validated."

## 5. Negative control — `copybook:UNUSED` (1 min)

Type `copybook:UNUSED`, analyse. Zero impacts, zero tests, zero signals, zero
incidents — a clean empty state. "The engine reports what the evidence supports,
including nothing."

## 6. The trust boundary (30s, closer)

Recap the three badges and the principle:

> LLMs do not discover dependencies, calculate technical impact, select regression
> tests, create risk signals, select incidents, or modify verified deterministic
> results. AI is optional and is restricted to grounded explanation.

Offer to show the guard code (`backend/intelligence/ai/guard.py`) or the relevance
engine (`backend/intelligence/incidents/relevance.py`) for the technically curious.

## Screenshots

All views are captured in `screenshots/` and embedded in `README.md`:
`01-repository-overview`, `02-dependency-explorer`, `03-change-impact`, `04-graph`,
`05-graph-detail` (parallel edges), `06-release-intelligence`, `07-unused-negative-control`.
