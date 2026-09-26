# PHASE3A_BASELINE.md

Phase 3A: Deterministic Change-Set & Release Candidate Analysis

Frozen: 2026-09-26
Branch: `phase3-changeset-analysis` (merged into `main`)
Base: f1009b410c50b762a3a9746bd6da1d225a2823d5
Audit verdict: PASS — READY TO FREEZE (0 HIGH, 0 correctness/security MEDIUM)

## Verification at freeze

- Backend tests: **255 passed**, 0 failed
- Frontend tests: **34 passed** (4 files), 0 failed
- Production build: **passed**
- Frozen Phase 1/2A/2B semantics: unchanged (byte-identical CLI outputs and
  API responses vs base f1009b4)
- Existing phase tags untouched: phase1-complete, phase2a-complete,
  phase2b-complete, audited-product-baseline, interview-ready-baseline

## Phase 3A capabilities

- Explicit multi-file change sets
- Deterministic file -> component mapping
- Mapped / ambiguous / unmapped / base-snapshot states
- Local Git diff provider
- Modified / added / deleted / renamed files
- Multi-root impact analysis
- Changed components separated from downstream impact
- Cross-impact between changed roots
- Root provenance
- Snapshot provenance
- Mixed base/head snapshot analysis
- Rename-aware old/base and new/head analysis
- Deduplicated test recommendations
- MUST_RUN > SHOULD_RUN deterministic priority aggregation
- DB2 resource aggregation
- Independent READ / WRITE semantics
- Risk-signal aggregation
- Checklist aggregation
- Historical incident aggregation
- Optional grounded AI release explanation
- CLI (`changeset.py`)
- API (`POST /api/change-set/analyze`)
- Sixth Release / Change Set UI

## Primary demo (verified)

Input:

- copybook/WARRCOPY.cpy
- cobol/WARR002.cbl

Results:

- Changed components: 2 (`copybook:WARRCOPY`, `program:WARR002`)
- Cross-impacted changed components: 1
  (`program:WARR002` also impacted by `copybook:WARRCOPY`)
- Downstream impacted components: 4
  (`job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`, `program:WARR001`)
- Direct-impact union: 3
- Transitive-impact union: 3
- Impact overlap: 3 (`job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`)
- Recommended tests: 7 (6 MUST_RUN, 1 SHOULD_RUN)
- DB2: 1 READ, 2 WRITE
- Risk signals: 7
- Checklist items: 7
- Historical incidents: 11

### Direct/transitive union semantics

The direct-impact union and the transitive-impact union are **not**
mutually exclusive. Direct/transitive is a per-root relationship; the
release-level unions are "impacted directly by >= 1 changed root" and
"impacted transitively by >= 1 changed root". A component can be direct
from one changed root and transitive from another: in the demo,
`job:WARRBTCH` and `proc:WARRANTY` are transitive via `copybook:WARRCOPY`
and direct via `program:WARR002`, which is exactly why 3 + 3 = 4 unique
downstream components. Changed roots are excluded from downstream impact
by definition; cross-impact between changed roots is preserved via
`also_impacted_by`.

## Deterministic trust guarantees

The AI layer may only explain already-computed deterministic release
intelligence. It is guaranteed that:

- AI does not map files to components.
- AI does not determine impact.
- AI does not resolve ambiguous files.
- AI does not select tests.
- AI does not determine test priority.
- AI does not create risk signals.
- AI does not create checklist items.
- AI does not select historical incidents.
- AI cannot modify deterministic release intelligence.

AI is optional and restricted to grounded explanation. A hallucination
guard rejects any explanation referencing identifiers outside the
computed context; provider failure falls back to the deterministic
summary, and `explanation_source` is set authoritatively.

## Accepted limitations

- AI guard regex brittleness fails safe to deterministic fallback
  (L3/L4, documented, not redesigned).
- Existing documented Phase 1 parser limitations remain
  (e.g. keywords inside COBOL string literals can yield false deps).
- No opaque release-risk score (deliberate).
- Git-diff mode is currently CLI/service-layer only; the HTTP API
  accepts explicit file lists only and never takes repository or
  filesystem paths.
- GitHub PR integration is not part of Phase 3A.
- Vite/Cytoscape chunk-size warning remains non-blocking.

## What Phase 3A did not do

- No Phase 3B work.
- No changes to frozen Phase 1/2A/2B semantics (verified byte-identical).
- No v1.1.0 release (to be decided separately).
