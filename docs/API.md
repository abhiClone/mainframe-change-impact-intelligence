# API Reference

Base URL: `http://127.0.0.1:8000` (see `./run_api.sh`). All responses are JSON.
Component ids use the `"<kind>:<NAME>"` form (e.g. `copybook:WARRCOPY`).

## Error contract

| Situation | Response |
|---|---|
| Unknown component id | HTTP 404 with a clear message (same contract across all `{component_id}` endpoints) |
| Unknown incident id | HTTP 404 |
| Corrupted incident dataset / test catalog | HTTP 500 naming the problem (fail loud, never silent) |

## Endpoints

### `GET /api/summary`

Repository counts: component totals by type and total dependency count.

### `GET /api/components`

All 18 components: `id`, `name`, `type`, `source_file`.

### `GET /api/dependencies`

All 30 dependencies: `source`, `target`, `relationship`, `evidence{file, line, text}`.

### `GET /api/graph`

Nodes + edges shaped for the Cytoscape UI (parallel edges preserved as independent elements).

### `GET /api/component/{component_id}`

One component with its upstream (dependencies) and downstream (dependents) neighbourhoods.

### `GET /api/impact/{component_id}`

Change-impact analysis: `direct_impacts`, `transitive_impacts`, `dependency_paths`
(each path a list of edges with evidence), and `evidence` refs.

Example: `GET /api/impact/copybook:WARRCOPY` →
2 direct, 3 transitive, 6 paths. `GET /api/impact/copybook:UNUSED` → all empty.

### `GET /api/intelligence/{component_id}`

The full release-intelligence bundle:

```json
{
  "impact_context": { "changed_component": "...", "direct_impacts": [...], "...": "..." },
  "involved_resources": [ { "component_id": "table:WARRANTY", "access": "write", "evidence": {...} } ],
  "test_recommendations": [ { "test_id": "TC-WARR-002", "impact_level": "MUST_RUN", "rationale": "...", "evidence": [...] } ],
  "risk_signals": [ { "id": "DB2_WRITE_INVOLVED", "severity": "high", "...": "..." } ],
  "release_checklist": [ { "item_id": "CHK-DB2-WRITE", "rule": "db2_write_involved", "...": "..." } ],
  "incident_intelligence": { "total_relevant_incidents": 11, "incidents": [...], "primary_tier_counts": {...}, "reason_counts": {...} },
  "explanation": { "executive_summary": "...", "explanation_source": "deterministic" }
}
```

### `GET /api/test-recommendations/{component_id}`

Recommended tests only (same `RecommendedTest` objects as the bundle).

### `GET /api/risk-signals/{component_id}`

Risk signals only.

### `GET /api/test-catalog`

The 12-test catalog: `id`, `name`, `type`, `covers[]`, `execution.job`, `description`.

### `GET /api/incidents`

All 17 historical incidents (full records).

### `GET /api/incidents/{incident_id}`

One incident by id (404 if unknown).

### `GET /api/incident-intelligence/{component_id}`

Relevant incidents with deterministic reasons: `incidents[]` (each with `reasons[]`
and `primary_reason`), `total_relevant_incidents`, `primary_tier_counts`,
`reason_counts`.

## Notes for integrators

- The graph is built once at API startup from `sample_mainframe/`; it is in-memory
  and per-process.
- All endpoints are deterministic: identical requests return identical responses.
- The `explanation.explanation_source` field (`deterministic` | `ai`) is authoritative;
  render badges from it, never from text parsing.
- `reason_counts` may exceed `total_relevant_incidents` (secondary reasons preserved);
  `primary_tier_counts` sums to the total.
