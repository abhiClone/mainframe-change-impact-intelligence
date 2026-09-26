# Evidence Model

Every factual claim in the platform traces to **source evidence**. A dependency without
evidence is not emitted; a UI claim without a deterministic source is not shown.

## The Evidence contract

```python
@dataclass(frozen=True)
class Evidence:
    file: str   # repo-relative path, e.g. "cobol/WARR001.cbl"
    line: int   # 1-based line number in `file`
    text: str   # the stripped source statement
```

Serialized as `EvidenceRef` in API responses. `test_every_dependency_has_evidence`
enforces completeness on every scan of the sample repository.

## Where evidence flows

| Stage | Evidence carried |
|---|---|
| Parsers | `{file, line, text}` per dependency (the statement the parser matched) |
| Dependency graph | every edge owns its evidence independently (parallel edges, parallel evidence) |
| Impact analysis | dependency paths cite per-edge evidence |
| Test recommendation | each `RecommendedTest` carries deduplicated `EvidenceRef`s from its paths; rationales cite `{file}:{line}` |
| Risk signals | `DB2_WRITE_INVOLVED` attaches only the `WRITES_TABLE` evidence; other signals attach impact-path edge evidence |
| Incident relevance | each reason carries supporting dependency paths with real file/line/text evidence |
| AI context | the serialized evidence is part of the strict provider input — the only "facts" the AI may cite |

## The Evidence Panel (UI)

Clicking any graph edge, explorer row, or impact path opens the Evidence Panel:

- the relationship (`READS_TABLE`, `WRITES_TABLE`, `USES_COPYBOOK`, …)
- the source file and 1-based line number
- the exact source statement text
- the parser/no-inference message: relationships come from deterministic source
  parsing — **no inference, no LLM**

The panel makes the trust boundary tangible: a user can always ask "says who?" and get
a file, a line, and a statement.

## Involved vs impacted in evidence terms

Impact evidence answers "why is this component impacted?" (the reverse-traversal chain
with per-edge statements). Involved-resource evidence answers "why is this table
involved?" (the impacted program's *outgoing* read/write edge with its statement).
The two are different questions, different edges, different statements — and the UI
labels them accordingly.
