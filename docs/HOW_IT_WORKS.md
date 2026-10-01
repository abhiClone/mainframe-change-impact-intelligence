# How It Works

A walkthrough of one change — `copybook:WARRCOPY` (the shared warranty copybook) — from
source scan to release intelligence.

## 1. Scan the repository

```bash
.venv/bin/python analyze.py sample_mainframe
```

The scanner walks `sample_mainframe/`: COBOL programs in `cobol/`, copybooks in `copybook/`,
JCL jobs in `jcl/`, PROCs in `proc/`, DB2 DDL in `sql/schema.sql`. Parsers extract
**18 components** and **30 dependencies**, each dependency carrying mandatory evidence
(file, 1-based line, exact source statement).

Example: in `cobol/WARR001.cbl` line 15, the statement `COPY WARRCOPY.` produces the
dependency `program:WARR001 --USES_COPYBOOK--> copybook:WARRCOPY`.

## 2. Ask what the change affects

```bash
.venv/bin/python impact.py copybook:WARRCOPY
```

Impact flows **opposite** to dependency direction: an edge `A → B` means "A depends on B",
so changing `copybook:WARRCOPY` impacts its dependents. The analyzer runs BFS on the
reversed graph:

- **Direct impacts (distance 1):** `program:WARR001`, `program:WARR002`
- **Transitive impacts (distance ≥ 2):** `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`
- **Dependency paths (6):** shortest chains such as
  `copybook:WARRCOPY <- program:WARR001 <- job:DAILY01`, each edge citing its evidence.

## 3. See what the impacted programs touch

The impacted programs' outgoing DB2 edges are collected as **involved resources**:
`WARR001` reads and writes `table:WARRANTY`; `WARR002` writes `table:WARRANTY` and
`table:CLAIM_HISTORY`. These tables are *involved in* the change, not *impacted by* it —
the UI says so explicitly.

## 4. Get the release intelligence

`GET /api/intelligence/copybook:WARRCOPY` returns the full bundle:

- **Test recommendations (7):** the deterministic rule recommends a test iff its catalog
  coverage intersects the impact set. `TC-WARR-002` covers `copybook:WARRCOPY` itself and both
  directly impacted programs → `MUST_RUN`, with a generated rationale citing
  `cobol/WARR001.cbl:15`.
- **Risk signals (7):** rules fire over the impact context — `SHARED_COPYBOOK_CHANGE`,
  `DB2_WRITE_INVOLVED` (high), `MULTIPLE_BATCH_JOBS_IMPACTED`, `HIGH_FAN_OUT`, and more.
- **Release checklist (7):** items like `CHK-DB2-WRITE`, each citing the rule that produced it.
- **Incident intelligence (11 of 17):** past incidents deterministically matched — e.g. an
  incident linked to `program:WARR001` carries reason `DIRECT_IMPACT_MATCH`.
- **Explanation:** a `DETERMINISTIC SUMMARY` (default) — or `AI EXPLANATION` if a validated
  LLM provider is configured.

## 5. Verify the negative control

```bash
.venv/bin/python impact.py copybook:UNUSED
```

Nothing depends on `copybook:UNUSED`: 0 impacts, 0 tests, 0 signals, 0 incidents. The engine
reports the empty result instead of inventing relationships — this is verified by tests and is
a deliberate demo asset.

## The guarantee behind every step

No step above involves an LLM. Identifiers, counts, selections, and orderings are produced by
pure deterministic functions; re-running the same query on the same repository yields
byte-identical results. The optional AI layer can only *rephrase* what these steps produced.

## Release candidates: more than one changed file

`changeset.py` (CLI), `POST /api/change-set/analyze`, and the **Release / Change Set** UI view
lift the pipeline to change sets. Each changed file is mapped to its component(s) using the
parsers' `source_file` metadata — ambiguous files (e.g. `sql/schema.sql`, which declares many
tables) surface candidates for a human to resolve; unmapped files (e.g. `README.md`) stay
visible and contribute no Mainframe impact; deleted files are resolved from a git base
snapshot when one is available, otherwise reported as uncertain. Each mapped component then
goes through the exact pipeline above, and the results are merged at the release level:
deduplicated impact union with per-root provenance, impact-overlap detection, strongest-priority
test merge (`MUST_RUN > SHOULD_RUN`), merged DB2 resources, signals, checklist, and incidents.
Full rules: `docs/CHANGE_SET_ANALYSIS.md`.

## Pull requests: a real GitHub PR as a change set (Phase 3B, unreleased)

`github_pr.py` (CLI), `POST /api/github/pull-request/analyze`, and the **GitHub PR**
UI view (seventh view) run the same pipeline against an actual pull request:

1. The PR is identified by `owner`, `repo`, `pull_number`, and `source_root`
   (the Mainframe subtree, e.g. `sample_mainframe`).
2. The backend fetches PR metadata and the changed-file list (paginated,
   `per_page=100`). More than 3000 files fails closed with
   `incomplete_change_set` — no impact is ever computed from a partial list.
3. Exact `base.sha` / `head.sha` snapshots are materialized into secure
   temporary directories (pre-scanned, size-limited, deleted afterwards);
   fork PRs download base and head from their respective repositories.
4. Files outside `source_root` stay visible but never enter the analysis;
   renames crossing the source-root boundary become `added`/`deleted`, with
   the original GitHub status preserved for provenance.
5. The frozen Phase 3A engine produces the identical `ChangeSetIntelligence`
   an equivalent explicit change set would — GitHub never determines impact.

Full rules: `docs/GITHUB_PR_ANALYSIS.md`.
