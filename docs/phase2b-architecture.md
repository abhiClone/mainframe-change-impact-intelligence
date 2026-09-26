# Phase 2B Architecture — Historical Incident Intelligence

## Data flow

```
Mainframe source
      ↓
Phase 1 deterministic dependency graph      (frozen)
      ↓
Phase 1 deterministic impact analysis       (frozen)
      ↓
Phase 2A deterministic release intelligence (frozen decision logic)
      ↓
Structured historical incident records      (validated YAML dataset)
      ↓
Deterministic incident relevance engine     (no LLM)
      ↓
Historical Incident Intelligence            (RelevantIncident list)
      ↓
Optional grounded AI summary                (explanation only)
```

## Components

| Piece | Location | Role |
|---|---|---|
| Dataset | `sample_mainframe/incidents/incidents.yaml` | 17 structured synthetic incidents; component links are authoritative structured data |
| Models | `backend/intelligence/incidents/models.py` | `HistoricalIncident`, `RelevanceReason(Type)`, `RelevantIncident`, `IncidentIntelligence` |
| Repository | `backend/intelligence/incidents/repository.py` | `IncidentRepository` ABC (future ServiceNow/Jira integrations plug in here); `YamlFileIncidentRepository` validates at load time |
| Relevance engine | `backend/intelligence/incidents/relevance.py` | Pure deterministic function: context × dataset → `IncidentIntelligence` |
| Service helpers | `backend/intelligence/incidents/service.py` | Lazy validated loading; `incident_intelligence_for(component_id)` |
| API | `backend/api/intelligence.py` | `GET /api/incidents`, `GET /api/incidents/{id}`, `GET /api/incident-intelligence/{component_id}`; `/api/intelligence/{component_id}` extended additively with `incident_intelligence` |
| UI | `frontend/src/views/IntelligenceView.tsx` | HISTORICAL INCIDENT INTELLIGENCE section, API-driven |

## Integration contract with Phase 2A

Phase 2B is **additive only**. The existing deterministic sections —
impact, involved resources, test recommendations, risk signals, release
checklist — are computed by the same Phase 2A functions and are
byte-identical with or without the incident layer. Historical incidents
cannot alter impacted components, dependency paths, test priority, risk
signals, or checklist rules during Phase 2B. Test selection still uses
only Phase 2A deterministic logic; incident history is a separate evidence
layer displayed alongside it (a future phase may combine them — not this
one).

## What the AI may do

The AI may **summarize** the already-selected relevant incidents:
what kinds of failures occurred previously, which incidents are most
directly related, what recurring themes appear, and what the release team
should be aware of — based only on the supplied history. Three new
explanation sections carry this: `incident_summary`,
`historical_patterns`, `release_history_considerations`.

## What the AI may NOT do

- select additional incidents, or decide which incidents are relevant
- create incidents, incident IDs, or component links
- modify relevance reasons or change relevance ordering
- claim recurrence probability or predict a production failure
- invent a root cause or a resolution

The hallucination guard was extended to validate incident IDs: only IDs
present in the supplied `relevant_incidents` are allowed; an unsupplied
id such as `INC-9999` is rejected and the response falls back to the
deterministic provider. Component, test, signal, and subject validation
are unchanged. The trust boundary is unchanged and explicit:

> Identifier grounding is validated automatically. Natural-language
> interpretation may still contain unsupported wording, therefore AI
> prose is non-authoritative and deterministic evidence remains the
> source of truth.

## What was deliberately NOT built

ServiceNow/Jira integration, production-log ingestion, Splunk/Elastic,
vector databases, embeddings, semantic incident search, ML incident
prediction, failure-probability prediction, automated root-cause
analysis, Git integration, Neo4j, CICS/IMS/MQ parsing, automated
deployment, Phase 3. Exact deterministic historical correlation comes
first; the `IncidentRepository` ABC keeps external sources replaceable
later without touching the relevance engine.

## Known limitations

- 17 synthetic incidents only; real history would come from an external
  repository implementation later.
- Involved resources are limited to deterministic DB2
  `READS_TABLE`/`WRITES_TABLE` relationships (Phase 2A semantics).
- A table both read and written yields the `INVOLVED_WRITE` reason
  (documented precedence); the read usage is still visible in the
  involved-resources section.
- The HTTP LLM provider has not been live-tested with a paid API.
- Natural-language AI prose is not fully fact-checked (documented trust
  boundary).
