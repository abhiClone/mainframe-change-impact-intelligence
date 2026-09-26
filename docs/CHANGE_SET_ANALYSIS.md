# Change-Set & Release Candidate Analysis (Phase 3A)

**Status: released in v1.1.0** (frozen 2026-09-26 as tag `phase3a-complete`, merged into `main`).

Phase 3A answers a release-manager question: *given a set of changed
files (a release candidate), what is the combined, deduplicated impact
across all of them?* It aggregates the frozen Phase 1 → Phase 2A →
Phase 2B layers per changed component and merges the results at the
release level. It is strictly additive: it never re-implements the
dependency graph, the impact engine, test recommendation, risk signals,
checklist, or incident relevance.

## Design principles

1. **Additive only.** Every deterministic decision below the change-set
   layer keeps its existing semantics:
   - Phase 1 dependency discovery is unchanged.
   - Phase 2A single-component impact/test/signal/checklist decisions
     are unchanged (called per changed component).
   - Phase 2B incident relevance is unchanged (called per changed
     component).
2. **The LLM never decides anything structural.** It only explains the
   already-computed deterministic result, and its output is validated by
   the same identifier guard used in Phase 2A. On any failure the
   deterministic summary is shown instead.
3. **Honest uncertainty.** Ambiguous file→component mappings surface
   candidates and select nothing automatically. Unmapped files stay
   visible and create no Mainframe impact. Deleted files without a base
   snapshot report uncertainty instead of guessing.
4. **Provenance everywhere.** Every aggregated item carries the list of
   change roots that produced it, with per-root detail inspectable.
5. **No opaque release-risk score.** The platform aggregates evidence;
   humans judge release readiness.

## Inputs: change-set providers

A `ChangeSetProvider` supplies changed files (`ChangedFile`: path,
status, old path for renames). Two providers exist:

- **ExplicitFileListProvider** — a caller-supplied list of files with
  statuses (`modified`, `added`, `deleted`, `renamed`). Used by the CLI
  `--file` mode and the API.
- **GitDiffProvider** — runs `git diff --name-status -z <base>...<head>`
  against a local repository. Security properties:
  - subprocess calls use argument lists; never `shell=True`;
  - ref names are validated against a conservative allow-list
    (`HEAD~1`, tags, branches, SHAs accepted; anything else rejected);
  - path traversal is rejected;
  - `source_prefix` (default `sample_mainframe`) scopes the diff to the
    Mainframe subtree; files outside it stay visible as unmapped;
  - base content is read with `git show <base>:<path>` for deleted
    files; trees are extracted with `git archive` into temporary
    directories.

The API endpoint (`POST /api/change-set/analyze`) intentionally accepts
only caller-supplied file metadata — it never accepts repository or
filesystem paths from the network.

## File → component mapping

`FileComponentMapper` maps each changed file to Phase 1 components:

- **Deterministic index:** built from each component's `source_file`
  metadata — `cobol/*.cbl` → `program:*`, `copybook/*.cpy` →
  `copybook:*`, `jcl/*.jcl` → `job:*`, `proc/*.proc` → `proc:*`,
  `sql/*.sql` → all parsed tables (a schema file defines many tables,
  so it is inherently ambiguous).
- **Statuses:**
  - `mapped` — exactly one component.
  - `ambiguous` — multiple candidates; nothing is selected. The caller
    may resolve explicitly with `--resolve path=component-id[,…]`; an
    invalid selection is rejected. An explicitly empty selection is also
    rejected.
  - `unmapped` — not a Mainframe source file (e.g. `README.md`). Stays
    visible in the result; contributes no Mainframe impact.
  - `requires_base_snapshot` — a deleted file that no longer exists in
    the scanned tree and has no base bytes available. Uncertainty is
    reported; no impact is guessed.
- **Deleted files:** in git mode, a deleted file's base bytes are parsed
  with the Phase 1 parsers (under its real filename, since parsers
  derive names from the file stem) and its impact is analyzed against
  the base-snapshot graph. The result carries `snapshot: "base"` and a
  note. If the file still exists in the scanned tree (explicit-list
  deletion of a hypothetical change), head metadata is authoritative.
- **Parser fallback (Phase 1 untouched):** the frozen scanner
  materializes referenced-but-not-yet-scanned targets with
  `source_file="unknown"` and `setdefault` keeps the materialized
  entry when the real definition is scanned later (e.g. PROCs
  referenced by JCL before `proc/*.proc` is walked). When the index
  misses a file that exists in the scanned tree, the mapper parses the
  actual file with the unchanged Phase 1 parsers and maps it only if
  the parsed id is a known graph component — deterministic, no filename
  guessing, no Phase 1 change. The result note says so explicitly.

Deleted-file impact is genuinely "removed-component" impact: it is the
upstream blast radius of losing that component, computed from the
base-snapshot dependency graph.

## Per-change analysis

Each mapped change root is analyzed independently by the frozen engines:

- `ImpactAnalyzer` (Phase 2A) on the head graph — or the base graph for
  deleted files resolved from a base snapshot.
- `recommend_tests` (Phase 2A), `detect_risk_signals` (Phase 2A),
  `build_release_checklist` (Phase 2A) on each root's impact context.
- `IncidentRelevanceEngine` (Phase 2B) on each root's impact context.

The shared graph is reused via the additive helper
`build_impact_context_on(graph, analyzer, component_id)`; the existing
`build_impact_context(component_id)` delegates to it and its behavior
is unchanged.

## Remediation (M1–M8, L1, L2) — branch `phase3-changeset-analysis`

An independent audit of the Phase 3A work produced 8 MEDIUM and 6 LOW
findings. The remediation below is confined to Phase 3 code
(`backend/changeset/`, `changeset.py`, the Change Set view); frozen
Phase 1 / 2A / 2B semantics are untouched.

- **M3 — input normalization.** Exact-duplicate normalized
  `(path, old_path, status)` entries are deduplicated; the same
  normalized path with *conflicting* statuses raises a clear
  `ValueError` instead of double-counting. Explicit ambiguity
  resolutions are deduplicated, and the root plan analyses each
  changed component exactly once even when several files resolve to
  it. `ChangedComponent.originating_files` preserves every
  originating normalized path.
- **M2 — changed vs downstream.** `changed_components` (the explicit
  change roots) and `unique_impacted_components` (downstream only) are
  now disjoint by construction: the release aggregation excludes
  changed roots from downstream impact. Cross-impact between changed
  roots is preserved — not hidden — in
  `ChangedComponent.also_impacted_by` (with snapshot) and in the
  summary's `cross_impacted_changed_components` count. The UI shows a
  dedicated **Changed Components** section and a separate
  **Downstream Impacted Components** section.
- **M1 — order-invariant prose.** Aggregate signal explanations and
  checklist details are regenerated deterministically from the merged,
  sorted structured fields (`backend/changeset/prose.py`) — never
  inherited from the first processed change root. Aggregate evidence
  is deduplicated and sorted by `(file, line, text)`. Swapping the
  input file order produces byte-identical release output.
- **M4 — snapshot provenance.** Every per-root reference (impact
  provenance, tests, resources, signals, checklist, incidents) carries
  its snapshot (`base` / `head`); the UI renders `base`/`head` badges.
  `mixed_snapshot_analysis` is true when base roots (deletions,
  rename-away identities) and head roots are combined, and the
  deterministic summary says so explicitly.
- **M5 — rename semantics.** A git rename stays ONE changed-file
  event with `status == "renamed"`. The old path is mapped from the
  base snapshot, the new path from the head tree;
  `MappedChange.previous_component_ids` / `current_component_ids`
  (union in `component_ids`) expose both identities. The same
  identity on both sides is analyzed once (head); a rename that
  changes identity yields the old-component analysis on base and the
  new-component analysis on head. (Frozen Phase 1 COBOL/copybook
  identity is filename-derived, so COBOL renames always change
  identity; SQL table identity comes from DDL content.)
- **M6 — path containment.** All Phase 3 file reads go through
  `resolve_contained_path()`: POSIX absolute paths, Windows
  drive-letter and UNC paths, any `..` segment, resolved escapes
  from the repository root, and symlink targets outside the root are
  rejected before any read. Git-mode reads (`read_base_file`,
  `extract_file`, `source_prefix` validation) get the same
  treatment. Tests prove `_parse_head_file` never calls `read_text()`
  for traversal, absolute, or symlink-escape paths.
- **L1 — strict types.** Phase 3 models use `Literal` enums:
  `ChangeStatus`, `MappingStatus`, `Snapshot` (`"base"`/`"head"`),
  `TestImpactLevel` (`"MUST_RUN"`/`"SHOULD_RUN"`),
  `RiskSeverity` (`"low"`/`"medium"`/`"high"`),
  `ResourceAccess` (`"read"`/`"write"`). Invalid values are rejected
  at the model boundary with a clear 422-style validation error.
- **L2 — controlled CLI errors.** Invalid `--source-prefix` and
  other Git-path containment failures print a controlled `error: …`
  line (exit 1); no traceback.
- **M7 — demo numbers.** The documented demo change set
  (`copybook/WARRCOPY.cpy` + `cobol/WARR002.cbl`) now reports: 2
  files → 2 changed components, 1 cross-impacted changed component
  (`program:WARR002` also impacted by `copybook:WARRCOPY`), 4
  downstream impacted (`job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`,
  `program:WARR001`), 3 direct / 3 transitive union, overlap
  `job:DAILY01, job:WARRBTCH, proc:WARRANTY`, 7 tests (6 MUST_RUN, 1
  SHOULD_RUN), 1 DB2 read, 2 DB2 writes, 7 signals, 7 checklist
  items, 11 incidents. See `docs/DEMO_GUIDE.md`.
- **M8 — catalog isolation** (tested, unchanged behavior): the
  analyzed tree's own catalog wins, foreign trees without a catalog
  fail closed with a clear error, and git temp repositories get the
  head ref's catalog.

## Release-level aggregation

| Domain | Rule |
|---|---|
| Changed components | The explicit change roots, deduplicated by component id (M2/M3). `originating_files` keeps every source path; `also_impacted_by` records cross-impact between changed roots with snapshot provenance. Excluded from downstream impact by definition. |
| Impacted components | Downstream-only union across roots, deduplicated by component id. `impacted_by` lists every root that impacts it; `impacted_by_count` is the overlap metric. `impacted_by_multiple_changes` / `impacted_by_one_change` partition the union. Per-root evidence (direct/transitive depth, dependency paths, read/write evidence) is preserved in `per_root` with snapshot provenance (M4). |
| Tests | Deduplicated by test id. Strongest level wins: `MUST_RUN > SHOULD_RUN`. `recommended_because_of` lists the roots with snapshot; every per-root level and rationale is retained. |
| DB2 resources | Deduplicated by (table, access); READ and WRITE are independent entries. `associated_change_roots` (with snapshot), `used_by` programs, and evidence are merged with provenance. |
| Risk signals | Deduplicated by signal id; `change_roots` (with snapshot), `triggered_by`, and `supporting_components` merged. The human-readable explanation is regenerated from the merged structured fields (M1). |
| Checklist | Deduplicated by item id; `applicable_change_roots` (with snapshot) merged. The detail text is regenerated from the merged structured fields (M1). |
| Incidents | Deduplicated by incident id. The strongest release-level reason follows the existing Phase 2B precedence; per-root reasons remain inspectable, with snapshot provenance. |

## AI explanation (optional, subordinate)

`explain_change_set` builds a strict context from the deterministic
result (change roots, impacted ids, test ids, signal ids, checklist
ids, incident ids) and validates the explanation with the extended
identifier guard: the subject must be the change-set subject, and any
identifier that is not in the context — a component id, a change root,
a test id, a signal/checklist id, or an incident id — fails validation.
Three providers exist: `DeterministicChangeSetExplainer` (the default),
`FakeChangeSetExplainer` (tests), and `HttpChangeSetExplainer` (chat
completions API). Any provider exception or guard failure falls back to
the deterministic summary; `explanation_source` always reports which
path was used.

The AI output is attached to the result; it never modifies it. A test
asserts the deterministic sections are byte-identical with and without
the AI path.

## Interfaces

- **CLI:** `changeset.py` — `--file PATH[:status]` (repeatable),
  `--resolve PATH=component-id[,…]`, `--json`, `--fake-ai`,
  `--no-test-catalog`; git mode: `--repo`, `--base`, `--head`,
  `--source-prefix`. Test-catalog scoping: the analyzed tree's own
  `tests/test_catalog.yaml` wins; the bundled sample catalog is a
  fallback for the bundled `sample_mainframe` tree only. A foreign
  tree without its own catalog raises a clear error (no traceback)
  advising `--no-test-catalog`; git mode plants the head ref's
  catalog into the temporary source tree when present.
- **API:** `POST /api/change-set/analyze` with `files`,
  optional `resolutions`, optional `fake_ai`. 400 on invalid
  resolutions, 422 on malformed payloads.
- **UI:** sixth view **Release / Change Set** — changed-file rows with
  add/remove, status selection, "Load demo change set" (populates input
  only; all results come from the backend), then sections for mapping,
  **Changed Components** (explicit roots with originating files,
  rename identity, and cross-impact between changed roots, never
  hidden inside downstream impact), **Downstream Impacted
  Components** (changed roots excluded by definition), overlap, DB2
  resources, tests, signals, checklist, incidents, and the
  deterministic/AI summary. Every per-root reference carries a
  `base`/`head` snapshot badge; mixed-snapshot releases are flagged
  in the Release Summary. Provenance badges: (`VERIFIED CHANGE SET`,
  `VERIFIED IMPACT`, `DETERMINISTIC SUMMARY`, `AI EXPLANATION`).

## Verification

- `backend/tests/test_phase3_mapping_providers.py` — 24 tests: mapping
  statuses, explicit/git providers on temporary repos only, base
  snapshots, unsafe-ref rejection, PROC mapping via the deterministic
  parser fallback (Phase 1 scanner metadata stays frozen), foreign-tree
  test-catalog selection and controlled catalog errors.
- `backend/tests/test_phase3_aggregation.py` — 29 tests: dedup +
  provenance rules, strongest-priority-wins, READ/WRITE independence,
  UNUSED negative control, mixed mapped/unmapped sets, AI guard
  rejection of hallucinated ids, API validation.
- All 166 pre-existing backend tests and 17 pre-existing frontend
  tests still pass unchanged.

## Limitations (see `docs/LIMITATIONS.md` for the full list)

- Git mode requires the CLI's repository context; the HTTP API accepts
  only explicit file lists.
- Ambiguous mappings need a human decision; the platform never
  auto-selects.
- Deletions are only resolvable when base bytes are available.
- The demo tree is small; real-world diffs need the `source_prefix`
  scope to match the repository layout.
