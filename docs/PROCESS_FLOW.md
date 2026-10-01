# Process Flow

## Full pipeline (source → intelligence)

```mermaid
flowchart LR
    A["sample_mainframe/\nCOBOL · copybooks · JCL\nPROCs · DB2 DDL"] --> B["repository_scanner\nwalk + dispatch"]
    B --> C["cobol_parser\nCOPY · CALL · EXEC SQL"]
    B --> D["jcl_parser\nEXEC PGM= · EXEC PROC="]
    B --> E["sql_parser\nCREATE TABLE"]
    C --> F["components[]\ndependencies[]\n(each with evidence)"]
    D --> F
    E --> F
    F --> G["DependencyGraph\nNetworkX MultiDiGraph"]
    G --> H["ImpactAnalyzer.analyze(id)\nBFS on reversed graph"]
    H --> I["ImpactContext\ntyped + serializable"]
    I --> J["recommend_tests\ncoverage ∩ impact set"]
    I --> K["detect_risk_signals\n8 deterministic rules"]
    I --> L["build_checklist\nrule-cited items"]
    I --> M["incident relevance\n5 reason types × 17 incidents"]
    J --> N["explain_change()\nstrict context → provider → guard"]
    K --> N
    L --> N
    M --> N
    N --> O["API bundle\n+ UI views"]
    H --> P["CLI\nanalyze.py / impact.py"]

    CS["changed files\n(explicit list or git diff)"] --> MAP["FileComponentMapper\nmapped / ambiguous / unmapped\n/ requires_base_snapshot"]
    MAP --> PER["per change root:\nImpactAnalyzer + rules + incidents\n(on head or base-snapshot graph)"]
    PER --> AGG["ChangeSetAggregator\nunion · dedup · overlap · provenance\nstrongest test priority wins"]
    AGG --> N2["explain_change_set()\nstrict context → provider → guard"]
    N2 --> O2["API bundle\nPOST /api/change-set/analyze\n+ Release / Change Set view"]
    PER --> CLI2["CLI\nchangeset.py"]
```

## Request flow: `GET /api/intelligence/copybook:WARRCOPY`

```mermaid
sequenceDiagram
    participant UI as Frontend / curl
    participant API as FastAPI router
    participant CTX as build_impact_context
    participant G as DependencyGraph (frozen)
    participant R as Rules (tests/signals/checklist)
    participant INC as Incident relevance
    participant AI as AI service (optional)

    UI->>API: GET /api/intelligence/copybook:WARRCOPY
    API->>CTX: build_impact_context(id)
    CTX->>G: analyze() → direct/transitive/paths/evidence
    CTX-->>API: ImpactContext
    API->>R: recommend_tests / detect_risk_signals / build_checklist
    R-->>API: 7 tests, 7 signals, 7 checklist items
    API->>INC: build_incident_intelligence(ctx, dataset)
    INC-->>API: 11 relevant incidents + reasons
    API->>AI: explain_change(...) [optional]
    AI-->>API: validated 4-section explanation or deterministic fallback
    API-->>UI: intelligence bundle (JSON)
```

## Request flow: `POST /api/github/pull-request/analyze` (Phase 3B, released in v1.2.0)

```mermaid
sequenceDiagram
    participant UI as Frontend / CLI
    participant API as FastAPI router
    participant GH as GitHubClient (read-only REST)
    participant SNAP as snapshots (secure temp extraction)
    participant P as GitHubPullRequestProvider
    participant A as ChangeSetAnalyzer (frozen Phase 3A)

    UI->>API: POST /api/github/pull-request/analyze {owner, repo, pull_number, source_root}
    API->>API: validate owner/repo/number/source_root (422 / 400 on bad input)
    API->>GH: GET PR metadata (exact base.sha / head.sha)
    API->>GH: GET changed files (paginated; >3000 → incomplete_change_set)
    GH-->>API: metadata + files
    API->>GH: GET tarball(base.sha) from base repo; GET tarball(head.sha) from head repo
    GH-->>SNAP: archives (manual 302 handling; approved-host check; no token forwarded)
    SNAP-->>API: extracted base/head trees (pre-scan + size guards; unsafe → unsafe_archive)
    API->>P: build provider (status translation, source_root scope, rename boundaries)
    P->>A: analyze() on head/base snapshots
    A-->>API: ChangeSetIntelligence (embedded intact)
    API-->>UI: GitHubPullRequestAnalysis (metadata + files + snapshots + intelligence)
```

## Impact traversal detail

```mermaid
flowchart TD
    CHG["changed: copybook:WARRCOPY"]
    D1["program:WARR001"]
    D2["program:WARR002"]
    T1["job:DAILY01"]
    T2["job:WARRBTCH"]
    T3["proc:WARRANTY"]

    CHG -->|reverse of USES_COPYBOOK| D1
    CHG -->|reverse of USES_COPYBOOK| D2
    D1 -->|reverse of EXECUTES_PROGRAM| T1
    D1 -->|reverse of EXECUTES_PROGRAM| T3
    D2 -->|reverse of EXECUTES_PROGRAM| T2
    D2 -->|reverse of EXECUTES_PROGRAM| T3
```

Edges in the graph point **dependent → dependency** ("depends on"); impact walks them
backwards. Direct = distance 1, transitive = distance ≥ 2.

## Failure and edge behaviour

| Situation | Behaviour |
|---|---|
| Unknown component id | CLI: clear error · API: HTTP 404 |
| Component with no dependents (`copybook:UNUSED`) | Empty impact sets, empty paths, empty evidence — a valid zero result |
| Ambiguous change-set file, no resolution | Candidates surfaced; nothing auto-selected; no impact contributed |
| Unmapped change-set file (e.g. `README.md`) | Stays visible; contributes no Mainframe impact |
| Deleted change-set file, no base snapshot | `requires_base_snapshot`; uncertainty reported, no impact guessed |
| Invalid change-set resolution | CLI: clear error · API: HTTP 400 |
| Malformed `incidents.yaml` / `test_catalog.yaml` | Controlled domain error (HTTP 500 naming the problem), never a traceback |
| LLM provider misconfigured / unreachable / guard rejection | Deterministic fallback explanation; deterministic results unaffected |
| Unknown `INTELLIGENCE_PROVIDER` value | Silently falls back to `deterministic` |
| GitHub PR with > 3000 changed files (Phase 3B) | `incomplete_change_set` (HTTP 422): no impact computed from a partial list |
| Private repo without `GITHUB_TOKEN` / unknown repo or PR (Phase 3B) | `repository_not_found_or_not_authorized` / `pull_request_not_found` (HTTP 404): not-found and no-access are indistinguishable by design |
| GitHub rate limit hit (Phase 3B) | `github_rate_limited` (HTTP 429) with reset time; never retried in this phase |
| Unsafe archive member / snapshot size limit exceeded (Phase 3B) | `unsafe_archive` (HTTP 422) / `snapshot_too_large` (HTTP 413): archives are never silently truncated |
| PR file outside `source_root` (Phase 3B) | Stays visible (`outside_source_scope`); contributes no Mainframe impact |
| Unknown GitHub file status (Phase 3B) | `unsupported_github_status` (HTTP 422): never silently converted |
| Deleted-fork PR with unreachable head SHA (Phase 3B) | `head_snapshot_unavailable` (HTTP 422) |
