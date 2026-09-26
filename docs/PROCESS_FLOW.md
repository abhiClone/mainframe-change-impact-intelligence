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
