# Frontend — Mainframe Change Impact & Release Intelligence UI

React + TypeScript + Vite UI for the Mainframe Change Impact & Release
Intelligence Platform. It is API-driven: every number, badge, and evidence
reference is rendered from the backend's deterministic results. No
intelligence data is hard-coded in the frontend.

## Views

1. **Repository Overview** — component counts and dependency totals.
2. **Dependency Explorer** — browse components and relationships with
   evidence.
3. **Change Impact** — direct/transitive impact for a component id, with
   dependency paths.
4. **Graph** — interactive Cytoscape dependency graph; clicking an edge
   opens the Evidence Panel (relationship, source file, line number,
   exact source statement).
5. **Release Intelligence** — the full report: change summary, impacted
   components, involved DB2 resources, recommended tests, risk signals,
   release checklist, historical incidents, and the explanation section.

Trust distinctions the UI protects (covered by component tests in
`src/views/__tests__/`):

- VERIFIED IMPACT / DETERMINISTIC SUMMARY badges are never labelled AI;
  AI EXPLANATION appears only when a genuine provider produced it.
- Historical incident severity is a separate badge from change relevance.
- Involved DB2 resources are presented as involved, not impacted.

## Development

```bash
npm install
npm run dev      # dev server (expects the API at http://localhost:8000)
npm test         # vitest component tests
npm run build    # production build (tsc + vite)
npm run lint     # oxlint
npx vite preview # serve the production build
```

The backend API base URL is configured in `src/api.ts` (`API_BASE`).
