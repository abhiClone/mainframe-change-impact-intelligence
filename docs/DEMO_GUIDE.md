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

## 6. Release / Change Set — two changed files (2 min)

The Phase 3A scenario. Open the **Release / Change Set** tab, click **Load demo
change set** (`copybook/WARRCOPY.cpy` + `cobol/WARR002.cbl` — input only; every
result comes from the backend), then **Analyze release**. Walk the sections:

- **Changed Files & Mapping** — both files `mapped`; note the `VERIFIED CHANGE SET` badge.
- **Changed Components** — the two explicit change roots (`copybook:WARRCOPY`, `program:WARR002`), each with its originating file and a `head` snapshot badge. Note the cross-impact line: `program:WARR002` is *also downstream-impacted by* `copybook:WARRCOPY` — changed roots are never hidden inside the downstream list.
- **Downstream Impacted Components** — 4 components (`job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`, `program:WARR001`); changed roots are excluded by definition. Each entry keeps per-root provenance with snapshot badges.
- **Impact Overlap** — 3 components impacted by *both* changes: `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`.
- **Release Summary** — read the deterministic summary: 2 files → 2 changed components; 4 downstream impacted (3 direct union, 3 transitive union); 7 tests (6 `MUST_RUN`, 1 `SHOULD_RUN`); 1 DB2 read, 2 DB2 writes; 7 signals; 7 checklist items; 11 incidents.
- **Recommended Tests** — deduplicated; `TC-WARR-001` keeps both per-change reasons and the strongest level (`MUST_RUN`).
- **Historical Incidents** — deduplicated with per-change relevance reasons.
- **AI Release Explanation** — `DETERMINISTIC SUMMARY` badge: the AI cannot add components, impact, tests, risks, or incidents.

Optional order-invariance check: swap the two files in the input rows and re-run —
the release summary, prose, and evidence order are byte-identical, because
aggregate signal explanations and checklist details are regenerated from merged
structured fields (sorted), never copied from the first processed change root.

Optional live detour: add `README.md` to the change set and re-run — it appears as
`unmapped` and the Mainframe result is unchanged. "Non-Mainframe files stay visible
but contribute no impact."

## 7. The trust boundary (30s, closer)

Recap the three badges and the principle:

> LLMs do not discover dependencies, calculate technical impact, select regression
> tests, create risk signals, select incidents, or modify verified deterministic
> results. AI is optional and is restricted to grounded explanation.

Offer to show the guard code (`backend/intelligence/ai/guard.py`) or the relevance
engine (`backend/intelligence/incidents/relevance.py`) for the technically curious.

## 8. GitHub PR — a real pull request as a change set (Phase 3B, unreleased, 2 min)

Open the seventh tab, **GitHub PR**. Enter a repository (`owner/repo`), a PR
number, and the Mainframe source root, then **Analyze Pull Request**:

- The PR header shows number, title, state, author, base/head branches with
  short SHAs — the analysis runs against the exact SHAs, never branch names.
- **Changed Files** lists every PR file with its GitHub status, additions/
  deletions, scope badge (`IN SCOPE` / `OUTSIDE SOURCE ROOT`), and mapping
  status. GitHub status and mapping status are visually distinct; renames show
  old → new paths.
- The **VERIFIED PR CHANGE SET** badge means the file list came
  deterministically from GitHub PR metadata — it does not claim GitHub verified
  business correctness.
- Below, the same intelligence sections as the Release / Change Set view render
  via the shared `ChangeSetResults` component (identical numbers for identical
  change sets).
- There is deliberately **no token field**: private repositories use the
  server-side `GITHUB_TOKEN`; the neutral auth badge reports only whether one
  is configured.

Demo note: automated tests mock GitHub (`httpx.MockTransport`) — no test
depends on live GitHub. A live read-only smoke against a public PR is optional
and supplemental only.

## Screenshots

All views are captured in `screenshots/` and embedded in `README.md`:
`01-repository-overview`, `02-dependency-explorer`, `03-change-impact`, `04-graph`,
`05-graph-detail` (parallel edges), `06-release-intelligence`, `07-unused-negative-control`.
