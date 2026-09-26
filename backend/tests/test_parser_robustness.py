"""Parser robustness tests (Phase 1 audit).

Documents what the Phase 1 regex parsers support and -- via explicit
negative tests -- what they intentionally do NOT support. Nothing here
expands Phase 1 scope: unsupported syntax is documented and proven to
produce no false dependency, never silently implemented.

Supported (asserted below):
  - static COBOL CALL with a single- or double-quoted literal
  - multiline EXEC SQL SELECT / INSERT / UPDATE / DELETE blocks
  - COPY statements in any case, with extra whitespace; names upper-cased
  - lowercase / mixed-case source (all regexes are case-insensitive)
  - JCL //step EXEC PGM= and EXEC PROC= (any case)
  - comment lines ('*', '*>', '/', '//*') never produce dependencies,
    including EXEC SQL blocks hidden inside comments
  - keywords inside '...'/"..." string literals never create dependencies
    (with ''/"" escape handling); static CALL 'PGM' still works because
    the CALL keyword itself is real code

Intentionally unsupported (negative tests document the limitation):
  - dynamic COBOL CALL (CALL WS-VAR): ignored, never guessed
  - unquoted COBOL CALL (CALL CUST002): ignored
  - quoted COPY name (COPY 'WARRCOPY'.): ignored
  - JCL positional PROC execution (//STEP020 EXEC WARRANTY, no PROC=): ignored
"""
from pathlib import Path

import networkx as nx

from backend.graph.dependency_graph import DependencyGraph
from backend.parsers.cobol_parser import parse_program
from backend.parsers.jcl_parser import parse_job, parse_proc
from backend.parsers.repository_scanner import scan_repository

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cobol(tmp_path: Path, name: str, src: str):
    p = tmp_path / f"{name}.cbl"
    p.write_text(src)
    return parse_program(p, f"cobol/{name}.cbl")


def _jcl(tmp_path: Path, name: str, src: str):
    p = tmp_path / f"{name}.jcl"
    p.write_text(src)
    return parse_job(p, f"jcl/{name}.jcl")


def _rels(deps):
    return {(d.source, d.relationship, d.target) for d in deps}


def _by_rel(deps):
    out = {}
    for d in deps:
        out.setdefault(d.relationship, []).append(d)
    return out


# ---------------------------------------------------------------- static CALL

def test_static_call_single_quoted(tmp_path):
    _, deps = _cobol(tmp_path, "T1", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T1.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'CUST002' USING WS-ID.\n"
        "           STOP RUN.\n"
    ))
    assert ("program:T1", "CALLS", "program:CUST002") in _rels(deps)
    dep = _by_rel(deps)["CALLS"][0]
    assert dep.evidence.line == 4
    assert dep.evidence.text == "CALL 'CUST002' USING WS-ID."


def test_static_call_double_quoted(tmp_path):
    _, deps = _cobol(tmp_path, "T2", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T2.\n"
        "       PROCEDURE DIVISION.\n"
        '           CALL "VEH001".\n'
        "           STOP RUN.\n"
    ))
    assert ("program:T2", "CALLS", "program:VEH001") in _rels(deps)


def test_dynamic_call_is_ignored_not_guessed(tmp_path):
    """CALL WS-PGM-NAME cannot be resolved statically: ignore it."""
    _, deps = _cobol(tmp_path, "T3", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T3.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL WS-PGM-NAME.\n"
        "           STOP RUN.\n"
    ))
    assert "CALLS" not in _by_rel(deps)


def test_unquoted_call_is_ignored(tmp_path):
    """Limitation: unquoted CALL targets are not supported; no false dep."""
    _, deps = _cobol(tmp_path, "T4", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T4.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL CUST002.\n"
        "           STOP RUN.\n"
    ))
    assert "CALLS" not in _by_rel(deps)


# ------------------------------------------------------- multiline EXEC SQL

def test_multiline_sql_select_is_read(tmp_path):
    _, deps = _cobol(tmp_path, "T5", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T5.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               SELECT WARRANTY_STATUS\n"
        "               INTO :WS-S\n"
        "               FROM WARRANTY\n"
        "               WHERE WARRANTY_ID = :WS-ID\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    assert ("program:T5", "READS_TABLE", "table:WARRANTY") in _rels(deps)
    dep = _by_rel(deps)["READS_TABLE"][0]
    assert dep.evidence.line == 7
    assert dep.evidence.text == "FROM WARRANTY"


def test_multiline_sql_insert_is_write(tmp_path):
    _, deps = _cobol(tmp_path, "T6", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T6.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               INSERT INTO CLAIM_HISTORY\n"
        "                   (CLAIM_ID, STATUS)\n"
        "               VALUES\n"
        "                   (:WS-ID, :WS-S)\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    assert ("program:T6", "WRITES_TABLE", "table:CLAIM_HISTORY") in _rels(deps)
    dep = _by_rel(deps)["WRITES_TABLE"][0]
    assert dep.evidence.line == 5
    assert dep.evidence.text == "INSERT INTO CLAIM_HISTORY"


def test_multiline_sql_update_is_write(tmp_path):
    _, deps = _cobol(tmp_path, "T7", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T7.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               UPDATE WARRANTY\n"
        "               SET WARRANTY_STATUS = :WS-S\n"
        "               WHERE WARRANTY_ID = :WS-ID\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    assert ("program:T7", "WRITES_TABLE", "table:WARRANTY") in _rels(deps)
    dep = _by_rel(deps)["WRITES_TABLE"][0]
    assert dep.evidence.line == 5
    assert dep.evidence.text == "UPDATE WARRANTY"


def test_multiline_sql_delete_is_write(tmp_path):
    _, deps = _cobol(tmp_path, "T8", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T8.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               DELETE FROM CLAIM_HISTORY\n"
        "               WHERE CLAIM_ID = :WS-ID\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    assert ("program:T8", "WRITES_TABLE", "table:CLAIM_HISTORY") in _rels(deps)
    dep = _by_rel(deps)["WRITES_TABLE"][0]
    assert dep.evidence.line == 5
    assert dep.evidence.text == "DELETE FROM CLAIM_HISTORY"


# -------------------------------------------------------------------- COPY

def test_copy_statements_case_and_whitespace(tmp_path):
    _, deps = _cobol(tmp_path, "T9", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T9.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY WARRCOPY.\n"
        "       COPY    CUSTCOPY.\n"
        "       copy vehcopy.\n"
        "       CoPy ClAiMcPy.\n"
    ))
    rels = _rels(deps)
    assert ("program:T9", "USES_COPYBOOK", "copybook:WARRCOPY") in rels
    assert ("program:T9", "USES_COPYBOOK", "copybook:CUSTCOPY") in rels
    assert ("program:T9", "USES_COPYBOOK", "copybook:VEHCOPY") in rels
    assert ("program:T9", "USES_COPYBOOK", "copybook:CLAIMCPY") in rels
    lines = sorted(d.evidence.line for d in _by_rel(deps)["USES_COPYBOOK"])
    assert lines == [5, 6, 7, 8]


def test_quoted_copy_name_is_ignored(tmp_path):
    """Limitation: COPY with a quoted name is not supported; no false dep."""
    _, deps = _cobol(tmp_path, "T10", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T10.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY 'WARRCOPY'.\n"
    ))
    assert "USES_COPYBOOK" not in _by_rel(deps)


# --------------------------------- comments containing parser keywords

def test_cobol_comments_with_keywords_produce_nothing(tmp_path):
    """'*', '*>' and '/' comment lines must not create dependencies,
    even when they contain COPY / CALL / SELECT / EXEC keywords."""
    _, deps = _cobol(tmp_path, "T11", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T11.\n"
        "* COPY FAKECOPY. CALL 'FAKEPGM'.\n"
        "*> EXEC SQL SELECT A FROM FAKETABLE END-EXEC.\n"
        "/ a slash comment with SELECT B FROM FAKETABLE2\n"
        "       PROCEDURE DIVISION.\n"
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_commented_sql_block_produces_no_false_table(tmp_path):
    """An EXEC SQL block hidden inside a '*' comment box must be ignored."""
    _, deps = _cobol(tmp_path, "T12", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T12.\n"
        "      **************************************************\n"
        "*     EXEC SQL                                       *\n"
        "*         SELECT X                                   *\n"
        "*         FROM FAKETABLE                             *\n"
        "*     END-EXEC.                                      *\n"
        "      **************************************************\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY REALCOPY.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               SELECT A FROM REALTABLE\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    rels = _rels(deps)
    assert ("program:T12", "USES_COPYBOOK", "copybook:REALCOPY") in rels
    assert ("program:T12", "READS_TABLE", "table:REALTABLE") in rels
    assert not any("FAKE" in target for _, _, target in rels)


# ------------------------------------------- lowercase / mixed-case source

def test_lowercase_source_all_constructs(tmp_path):
    """Parsers are case-insensitive; extracted names are upper-cased."""
    _, deps = _cobol(tmp_path, "T13", (
        "       identification division.\n"
        "       program-id. t13.\n"
        "       data division.\n"
        "       working-storage section.\n"
        "       copy warrcopy.\n"
        "       procedure division.\n"
        "           call 'cust002'.\n"
        "           exec sql\n"
        "               select a from warranty\n"
        "           end-exec.\n"
        "           stop run.\n"
    ))
    rels = _rels(deps)
    assert ("program:T13", "USES_COPYBOOK", "copybook:WARRCOPY") in rels
    assert ("program:T13", "CALLS", "program:CUST002") in rels
    assert ("program:T13", "READS_TABLE", "table:WARRANTY") in rels
    dep = _by_rel(deps)["READS_TABLE"][0]
    assert dep.evidence.line == 9
    assert dep.evidence.text == "select a from warranty"


# --------------------------------------------------------------------- JCL

def test_jcl_exec_pgm(tmp_path):
    comp, deps = _jcl(tmp_path, "T14JOB", (
        "//T14JOB JOB (ACCT),'TEST'\n"
        "//STEP010  EXEC PGM=CUST001\n"
        "//STEP020  EXEC PGM=WARR001\n"
    ))
    assert comp.id == "job:T14JOB"
    rels = _rels(deps)
    assert ("job:T14JOB", "EXECUTES_PROGRAM", "program:CUST001") in rels
    assert ("job:T14JOB", "EXECUTES_PROGRAM", "program:WARR001") in rels
    lines = sorted(d.evidence.line for d in deps)
    assert lines == [2, 3]


def test_jcl_exec_proc(tmp_path):
    _, deps = _jcl(tmp_path, "T15JOB", (
        "//T15JOB JOB (ACCT),'TEST'\n"
        "//STEP010  EXEC PROC=WARRANTY\n"
    ))
    assert ("job:T15JOB", "USES_PROC", "proc:WARRANTY") in _rels(deps)
    assert _by_rel(deps)["USES_PROC"][0].evidence.line == 2


def test_jcl_lowercase_exec(tmp_path):
    _, deps = _jcl(tmp_path, "T16JOB", (
        "//t16job job (acct),'test'\n"
        "//step010  exec pgm=cust001\n"
        "//step020  exec proc=warranty\n"
    ))
    rels = _rels(deps)
    assert ("job:T16JOB", "EXECUTES_PROGRAM", "program:CUST001") in rels
    assert ("job:T16JOB", "USES_PROC", "proc:WARRANTY") in rels


def test_jcl_comment_exec_is_ignored(tmp_path):
    """'//*' comment lines must not create dependencies."""
    _, deps = _jcl(tmp_path, "T17JOB", (
        "//T17JOB JOB (ACCT),'TEST'\n"
        "//* //STEP010 EXEC PGM=FAKEPGM\n"
        "//* //STEP020 EXEC PROC=FAKEPROC\n"
        "//STEP030  EXEC PGM=CUST001\n"
    ))
    rels = _rels(deps)
    assert rels == {("job:T17JOB", "EXECUTES_PROGRAM", "program:CUST001")}


def test_jcl_positional_proc_is_ignored(tmp_path):
    """Limitation: '//STEP EXEC WARRANTY' without the PROC= keyword is
    not supported and must not create a guessed dependency."""
    _, deps = _jcl(tmp_path, "T18JOB", (
        "//T18JOB JOB (ACCT),'TEST'\n"
        "//STEP010  EXEC WARRANTY\n"
    ))
    assert deps == []


def test_proc_exec_pgm_lowercase(tmp_path):
    p = tmp_path / "T19.proc"
    p.write_text(
        "//warranty PROC\n"
        "//step01 exec pgm=warr002\n"
        "// PEND\n"
    )
    comp, deps = parse_proc(p, "proc/T19.proc")
    assert comp.id == "proc:WARRANTY"
    rels = _rels(deps)
    assert ("proc:WARRANTY", "EXECUTES_PROGRAM", "program:WARR002") in rels
    assert _by_rel(deps)["EXECUTES_PROGRAM"][0].evidence.line == 2


# --------------------------------- string literals are not dependencies

def test_display_copy_in_string_literal_creates_nothing(tmp_path):
    """DISPLAY 'COPY ME'. must not create USES_COPYBOOK -> ME."""
    _, deps = _cobol(tmp_path, "T20", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T20.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'COPY ME'.\n"
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_display_call_in_string_literal_creates_nothing(tmp_path):
    """DISPLAY "CALL 'FAKEPGM'". must not create CALLS -> FAKEPGM."""
    _, deps = _cobol(tmp_path, "T21", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T21.\n"
        "       PROCEDURE DIVISION.\n"
        '           DISPLAY "CALL \'FAKEPGM\'".\n'
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_display_select_in_string_literal_creates_nothing(tmp_path):
    _, deps = _cobol(tmp_path, "T22", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T22.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'SELECT * FROM WARRANTY'.\n"
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_display_update_in_string_literal_creates_nothing(tmp_path):
    _, deps = _cobol(tmp_path, "T23", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T23.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'UPDATE WARRANTY SET X = 1'.\n"
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_doubled_quote_escape_still_masks_literal(tmp_path):
    """'' inside a literal is an escape, not a terminator: the whole
    'IT''S A COPY TRAP' literal must be masked as one span."""
    _, deps = _cobol(tmp_path, "T27", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T27.\n"
        "       PROCEDURE DIVISION.\n"
        "           DISPLAY 'IT''S A COPY TRAP'.\n"
        "           STOP RUN.\n"
    ))
    assert deps == []


def test_real_call_survives_next_to_literal_call(tmp_path):
    """A real static CALL on the same line region as a DISPLAY whose
    literal contains CALL-like text: only the real one is kept."""
    _, deps = _cobol(tmp_path, "T26", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T26.\n"
        "       PROCEDURE DIVISION.\n"
        "           CALL 'WARR001'.\n"
        '           DISPLAY "CALL \'FAKEPGM\'".\n'
        "           STOP RUN.\n"
    ))
    assert _rels(deps) == {("program:T26", "CALLS", "program:WARR001")}


def test_valid_copy_call_and_sql_still_work(tmp_path):
    """Valid constructs keep working with original line numbers and
    verbatim evidence after the string-literal fix."""
    _, deps = _cobol(tmp_path, "T24", (
        "       IDENTIFICATION DIVISION.\n"      # 1
        "       PROGRAM-ID. T24.\n"              # 2
        "       DATA DIVISION.\n"                # 3
        "       WORKING-STORAGE SECTION.\n"     # 4
        "       COPY WARRCOPY.\n"               # 5
        "       PROCEDURE DIVISION.\n"           # 6
        "           CALL 'WARR001'.\n"           # 7
        "           EXEC SQL\n"                  # 8
        "               SELECT STATUS\n"        # 9
        "                 FROM WARRANTY\n"      # 10
        "           END-EXEC.\n"                 # 11
        "           EXEC SQL\n"                  # 12
        "               UPDATE WARRANTY\n"      # 13
        "                  SET STATUS = 'A'\n"  # 14
        "           END-EXEC.\n"                 # 15
        "           STOP RUN.\n"                 # 16
    ))
    rels = _rels(deps)
    assert ("program:T24", "USES_COPYBOOK", "copybook:WARRCOPY") in rels
    assert ("program:T24", "CALLS", "program:WARR001") in rels
    assert ("program:T24", "READS_TABLE", "table:WARRANTY") in rels
    assert ("program:T24", "WRITES_TABLE", "table:WARRANTY") in rels
    by_rel = _by_rel(deps)
    call = by_rel["CALLS"][0]
    assert call.evidence.line == 7
    assert call.evidence.text == "CALL 'WARR001'."
    copy = by_rel["USES_COPYBOOK"][0]
    assert copy.evidence.line == 5
    assert copy.evidence.text == "COPY WARRCOPY."
    read = by_rel["READS_TABLE"][0]
    assert read.evidence.line == 10
    assert read.evidence.text == "FROM WARRANTY"
    write = by_rel["WRITES_TABLE"][0]
    assert write.evidence.line == 13
    assert write.evidence.text == "UPDATE WARRANTY"


def test_sql_string_literal_with_sql_text_creates_only_real_dep(tmp_path):
    """INSERT INTO CLAIM_HISTORY VALUES ('SELECT FROM WARRANTY'):
    only the real WRITES_TABLE -> CLAIM_HISTORY; the SELECT/FROM inside
    the string literal must not create a fake READS_TABLE -> WARRANTY."""
    _, deps = _cobol(tmp_path, "T25", (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T25.\n"
        "       PROCEDURE DIVISION.\n"
        "           EXEC SQL\n"
        "               INSERT INTO CLAIM_HISTORY\n"
        "               VALUES ('SELECT FROM WARRANTY')\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    ))
    assert _rels(deps) == {
        ("program:T25", "WRITES_TABLE", "table:CLAIM_HISTORY")}

# ------------------------------------------------- multi-edge regression

def test_parallel_edges_reads_and_writes_coexist():
    """MultiDiGraph proof: program:WARR001 both READS and WRITES
    table:WARRANTY. Both edges must survive with their own relationship
    type, file, line number and evidence statement (regression test)."""
    components, dependencies = scan_repository(PROJECT_ROOT / "sample_mainframe")
    graph = DependencyGraph.from_scan(components, dependencies)

    assert isinstance(graph._g, nx.MultiDiGraph)
    assert graph._g.number_of_edges("program:WARR001", "table:WARRANTY") == 2

    rows = graph.edges_between("program:WARR001", "table:WARRANTY")
    assert len(rows) == 2
    by_rel = {r["relationship"]: r for r in rows}
    assert set(by_rel) == {"READS_TABLE", "WRITES_TABLE"}

    read, write = by_rel["READS_TABLE"], by_rel["WRITES_TABLE"]
    assert read["evidence"]["file"] == "cobol/WARR001.cbl"
    assert write["evidence"]["file"] == "cobol/WARR001.cbl"
    assert read["evidence"]["line"] != write["evidence"]["line"]
    assert "FROM" in read["evidence"]["text"].upper()
    assert "INSERT" in write["evidence"]["text"].upper()
    # each edge carries its own evidence record
    assert read["evidence"] != write["evidence"]
