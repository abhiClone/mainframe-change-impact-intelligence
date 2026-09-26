# Roadmap

The platform is delivered in frozen phases. Nothing on this roadmap is
committed or scheduled; each item would require its own explicit approval
before work begins.

## Delivered (frozen baselines)

- ✅ Phase 1 — deterministic COBOL/JCL/DB2 dependency discovery + change impact
- ✅ Phase 2A — deterministic release intelligence + grounded AI explanation
- ✅ Phase 2B — deterministic historical incident intelligence
- ✅ Audit remediation — reproducible setup, validation, UI trust tests
- ✅ Interview-ready baseline — final graph and Release Intelligence UX
- ✅ Phase 3A — deterministic change-set & release candidate analysis
  (completed — released in **v1.1.0**, 2026-09-26)

## Possible future phases (not started)

### Phase 3B (future — does not exist yet)
- GitHub Pull Request integration: analyse the files changed by a PR as a
  Phase 3A change set directly from the PR diff. Not implemented.

### Phase 3 candidates
- Real mainframe source parsing at scale: grammar/AST-based COBOL parser
  replacing the current regex extractors (interfaces are already swappable).
- Additional dependency types: CICS, IMS, MQ, dataset (GDG/PS) relationships.
- Persistent graph backend (Neo4j) behind the existing `DependencyGraph` interface.
- Multi-repository / multi-environment analysis.

### Incident intelligence
- Real incident-source integration via the `IncidentRepository` ABC
  (ServiceNow, Jira, Splunk/Elastic) — the relevance engine would not change.
- Semantic incident similarity as an *additional* signal, kept subordinate
  to deterministic relevance.

### AI layer
- Live testing of the HTTP LLM provider against a real chat-completions API.
- Additional grounded explanation sections, still guard-validated.

### Operations
- Incremental re-scanning (watch a repository and update the graph).
- Authenticated multi-user deployment, audit logging.

## Explicitly out of scope

Automated release verdicts (the platform advises; humans approve), failure
probability prediction, automated root-cause analysis, and any design where
an LLM discovers dependencies, selects tests, or modifies deterministic
results.
