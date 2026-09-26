# Phase 1 Baseline — Mainframe Change Impact & Release Intelligence Platform

Frozen baseline of the verified Phase 1 deterministic dependency &
change impact engine. No Phase 2 work is included in this baseline.

- 41 tests passed, 0 failed
- 18 components
- 30 dependencies
  - USES_COPYBOOK: 7
  - EXECUTES_PROGRAM: 7
  - READS_TABLE: 5
  - WRITES_TABLE: 5
  - CALLS: 3
  - USES_PROC: 3
- graph type: networkx.MultiDiGraph
- date of Phase 1 completion: 2026-09-26

Note: Phase 1 is fully deterministic. All dependency relationships are
discovered from source/configuration evidence by regex-based parsers
(COBOL COPY/CALL/EXEC SQL, JCL EXEC PGM=/PROC=, SQL schema). Every
dependency carries source file, line number, and evidence statement.
Phase 1 contains no LLM dependency discovery — no OpenAI, Gemini,
Claude, Llama, or any other model is used or required.
