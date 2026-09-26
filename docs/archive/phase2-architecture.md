# Phase 2A Architecture — Change Impact Intelligence

## Design principle: the LLM is never the source of truth

Every fact in this platform — which components exist, which edges connect
them, which tests are recommended, which risks fire, which checklist items
appear — is produced by **deterministic code over the frozen Phase 1
dependency graph**. The optional AI explanation layer sits at the very top
of the stack and is restricted by contract to **summarize and rephrase
information that already exists** in the deterministic artifacts. It can
add no component, dependency, test, table, job, or evidence that the lower
layers did not produce. The hallucination guard enforces this mechanically
(see `docs/ai-grounding.md`): any AI output referencing an identifier outside
the supplied context is rejected and replaced with a deterministic fallback.

Why this layering matters: in an interview (and in production) the decisive
question is "how do you stop the LLM from inventing facts?" The answer is
architectural, not aspirational — the LLM never receives repository paths,
raw source text, or graph access; it receives only serialized deterministic
results, and its output is regex-validated against the same vocabulary
before it can reach a user.

## Layered pipeline

```
 Source repository (sample_mainframe/)
        │
        ▼
 Layer 1 — Phase 1 parsers (FROZEN)
   backend/parsers/* — COBOL, JCL, PROC, DB2, copybook parsers
   emit components + dependencies, each with file:line:statement evidence
        │
        ▼
 Layer 2 — Dependency graph (FROZEN)
   backend/graph/dependency_graph.py — networkx.MultiDiGraph
   backend/graph/impact_analyzer.py — ImpactAnalyzer.analyze(component_id)
   produces direct/transitive impacts, dependency paths, evidence
        │
        ▼
 Layer 3 — Phase 2A ImpactContext
   backend/intelligence/impact_context.py :: build_impact_context()
   Translates the Phase 1 analyze() result into a typed, serializable
   ImpactContext (Pydantic). Reads only existing Phase 1 edges (the
   impacted programs' outgoing DB2 edges for involved resources) — no
   impact-graph traversal change, no LLM, no new parsing.
        │
        ├───────────────────────────┬───────────────────────────┐
        ▼                           ▼                           ▼
 Layer 4a — Test selection   Layer 4b — Risk signals    Layer 4c — Checklist
   test_selector.py            risk_signals.py             release_checklist.py
   coverage ∩ impact set       rule-based signal            rule-based items,
   MUST_RUN / SHOULD_RUN       detection over the           each citing its
                               ImpactContext                rule
        │                           │                           │
        └───────────────────────────┴───────────────────────────┘
                                    ▼
 Layer 5 — Optional AI explanation (backend/intelligence/ai/)
   service.py :: explain_change() builds the STRICT IntelligenceContext
   (serialized deterministic artifacts only), runs the configured provider
   (deterministic / fake / http), and validates the output with the
   hallucination guard. On any failure: deterministic fallback.
        │
        ▼
 Layer 6 — API / UI (see implementation — tracks in progress)
   Phase 2A API endpoint: GET /api/intelligence/{component_id}
   returns the full intelligence bundle + optional AI explanation.
   Frontend Intelligence view renders impact, tests, signals, checklist.
```

## What each layer owns

| Layer | Module | Owns | Forbidden to do |
|---|---|---|---|
| 1. Parsers (Phase 1, frozen) | `backend/parsers/` | Extract components + dependencies from source files with file:line:statement evidence | Modify anything (frozen baseline) |
| 2. Graph + analyzer (Phase 1, frozen) | `backend/graph/` | The MultiDiGraph; impact traversal (`analyze()`) | Modify anything (frozen baseline) |
| 3. ImpactContext | `backend/intelligence/impact_context.py` | Translating `analyze()` output into a typed, serializable context; classifying impacts by component type; involved DB2 resource extraction from the impacted programs' outgoing Phase 1 edges (read/write kept distinct) | Changing impact-graph traversal, LLM calls, new parsing |
| 4a. Test selection | `backend/intelligence/test_selector.py` | The coverage ∩ impact-set rule, MUST_RUN/SHOULD_RUN assignment, rationale text generation | Inventing tests; recommending anything the catalog does not contain |
| 4b. Risk signals | `backend/intelligence/risk_signals.py` | Rule-based signal detection over the context; severities; explanations | Failure probabilities; any heuristic beyond the documented rules |
| 4c. Release checklist | `backend/intelligence/release_checklist.py` | Rule-based checklist items, each citing its originating rule | Uncited items; release verdicts |
| 5. AI explanation | `backend/intelligence/ai/` | Four-section plain-language explanation of the deterministic artifacts; provider abstraction; hallucination guard; fallback | Introducing any identifier not in the context (mechanically enforced) |
| 6. API/UI | API + frontend | Serving and rendering the bundle | Owning any computation the layers above own |

## Component diagram (text)

```
┌──────────────────────────────────────────────────────────────┐
│  Intelligence package  (backend/intelligence/)                │
│                                                              │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────┐  │
│  │ impact_context  │──▶│ test_selector   │   │ risk_signals │  │
│  │ (Phase 1 →      │   │ (deterministic │   │ (deterministic│  │
│  │  ImpactContext) │   │  recommendation)│   │  signals)    │  │
│  └─────────────────┘   └─────────────────┘   └─────────────┘  │
│           │                      │                  │         │
│           └──────────┬───────────┴──────────────────┘         │
│                      ▼                                        │
│              ┌──────────────┐                                 │
│              │ release_     │                                 │
│              │ checklist    │                                 │
│              └──────────────┘                                 │
│                      │                                        │
│  ┌───────────────────▼─────────────────────────────────────┐  │
│  │ ai/ : ai_models (strict contract) → providers → guard   │  │
│  │       → service.explain_change()  [OPTIONAL LAYER]       │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         ▲ uses (frozen)                    ▲ imports models only
         │                                  │
   backend/graph/* (Phase 1)      backend.intelligence.models (Phase 2A)
```

Data contracts (`backend/intelligence/models.py`, Pydantic v2) connect the
layers: `ImpactContext`, `TestCase`, `RecommendedTest`, `RiskSignal`,
`ChecklistItem`, `EvidenceRef`, `PathEdge`, `DependencyPath`,
`InvolvedResource`. The AI layer has its own stricter contract,
`IntelligenceContext`, defined in `backend/intelligence/ai/ai_models.py`.

## Data flow for GET /api/intelligence/{component_id}

> Note: the API and UI tracks were still in progress when this doc was
> written and are documented against the backend intelligence + AI code.
> `backend/api/intelligence.py` (the Phase 2A API router composing the
> `backend.intelligence` services) landed in a parallel track after the
> first draft — consult it for the actual endpoint definitions. No API
> details are invented here.

1. Caller supplies a component id, e.g. `copybook:WARRCOPY`.
2. `build_impact_context("copybook:WARRCOPY")` → `ImpactContext`
   (direct impacts `program:WARR001`, `program:WARR002`; transitive impacts
   `job:DAILY01`, `job:WARRBTCH`, `proc:WARRANTY`; depth 2; 5 components).
3. `load_catalog()` → 12 `TestCase` entries from
   `sample_mainframe/tests/test_catalog.yaml`.
4. `recommend_tests(ctx, catalog)` → 7 `RecommendedTest` entries
   (6 MUST_RUN, 1 SHOULD_RUN), each with a rationale and evidence refs.
5. `detect_risk_signals(ctx)` → 6 `RiskSignal` entries for WARRCOPY
   (e.g. `SHARED_COPYBOOK_CHANGE`, `DB2_WRITE_INVOLVED` when applicable).
6. `build_checklist(ctx, signals)` → `ChecklistItem` entries, each citing
   its rule (`jobs_impacted`, `shared_copybook_change`, ...).
7. Optionally: `explain_change(ctx, recs, signals, checklist)` → the four-
   section `IntelligenceExplanation` (guarded; falls back deterministically
   on any failure).
8. The endpoint returns the bundle: impact context + recommendations +
   signals + checklist + optional explanation.

Every step is pure and reproducible: the same repository and the same
component id always produce the same bundle, whether or not the AI layer
is configured.
