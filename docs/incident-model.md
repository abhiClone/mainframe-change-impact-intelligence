# Phase 2B Incident Model

## Where incidents come from

Historical incidents are **structured synthetic historical evidence**
stored at `sample_mainframe/incidents/incidents.yaml`. They are *not*
mined from production logs, *not* imported from ServiceNow/Jira, and
*not* derived from prose by any LLM. Each incident was authored with
explicit `linked_components` pointing at real Phase 1 component IDs
(e.g. `program:WARR001`, `table:WARRANTY`).

## The model

`HistoricalIncident` (`backend/intelligence/incidents/models.py`):

| Field | Meaning |
|---|---|
| `id` | Unique incident id, e.g. `INC-1042` |
| `title` | Short human title |
| `occurred_at` | Date the incident occurred (ISO `YYYY-MM-DD`) |
| `severity` | `low` \| `medium` \| `high` \| `critical` — historical severity of the past incident |
| `status` | `open` \| `investigating` \| `resolved` |
| `summary` | One-paragraph description |
| `symptoms` | Observable symptoms (SQLCODEs, abends, …) |
| `linked_components` | **Authoritative structured data**: real Phase 1 component IDs |
| `failure_mode` | Machine-readable failure category (`duplicate_database_record`, `database_timeout`, …) |
| `root_cause_category` | `application_logic` \| `operations` \| `data_quality` \| `configuration` \| `change_management` \| `concurrency` |
| `root_cause_summary` | What caused the incident |
| `resolution_summary` | How it was resolved |

## Link validation

`linked_components` are validated **at load time** by
`YamlFileIncidentRepository` against the actual Phase 1 component graph:

- every linked id must exist in the Phase 1 graph — an unknown id such as
  `program:FAKE999` raises `IncidentDatasetError` and the whole dataset is
  rejected; it is never silently accepted or ignored;
- duplicate linked components are normalized/deduplicated;
- incident ids must be unique; dates, severities, statuses and titles are
  validated; every incident needs at least one linked component.

Invalid historical data cannot quietly contaminate intelligence results:
the API surfaces a clear 500 error naming the problem.

## Dataset design (17 incidents)

The dataset is deliberately small and interview-readable. It covers:

- a copybook incident (`INC-1015`: WARRCOPY layout change),
- program-logic incidents (`INC-1031`, `INC-1037`),
- batch failures (`INC-1088`: DAILY01 DB2 timeout, `INC-1045`: WARRBTCH S322),
- a PROC incident (`INC-1023`),
- DB2 duplicate-key incidents (`INC-1042`, `INC-1055`),
- DB2 data-integrity incidents (`INC-1037`, `INC-1060`),
- a read-related DB incident (`INC-1050`: stale warranty read),
- multi-component incidents (`INC-1042`, `INC-1037`, `INC-1050`, `INC-1055`, `INC-1095`),
- six unrelated incidents (`INC-1065`, `INC-1070`, `INC-1075`, `INC-1080`, `INC-1085`, `INC-1090`),
- one **unrelated high-severity** incident (`INC-1075`, severity `high`,
  linked only to `table:CUSTOMER`) — proving severity alone never implies relevance.

No incident is linked to `copybook:UNUSED`, keeping it a clean
negative-control scenario for the relevance engine.
