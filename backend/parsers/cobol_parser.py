"""COBOL parser (Phase 1: regex-based, modular interface).

Extracts from a COBOL program source file:
  - COPY <copybook>.            -> USES_COPYBOOK
  - CALL '<program>' ...        -> CALLS            (static calls only)
  - EXEC SQL ... END-EXEC blocks:
      SELECT ... FROM <table>   -> READS_TABLE
      INSERT INTO <table>       -> WRITES_TABLE
      UPDATE <table>            -> WRITES_TABLE
      DELETE FROM <table>       -> WRITES_TABLE

Every emitted dependency carries file/line/statement evidence.
Dynamic CALLs (CALL WS-VAR) cannot be resolved statically and are
deliberately ignored rather than guessed.

Comment lines ('*', '*>', '/' in COBOL; '//*' in JCL) are never scanned
for dependencies — including EXEC SQL blocks, which are matched against
the comment-blanked text so a commented-out SELECT cannot produce a
false READS_TABLE dependency. Blanked lines keep evidence line numbers
aligned with the source file.

Intentionally unsupported (documented, negative-tested):
  - dynamic COBOL CALL (CALL WS-VAR): ignored, never guessed
  - unquoted COBOL CALL (CALL CUST002): ignored
  - quoted COPY name (COPY 'WARRCOPY'.): ignored
  - JCL positional PROC execution (//S EXEC WARRANTY without PROC=): ignored

String literals ('...' and "...", with ''/"" doubled-quote escapes) are
located with a character scanner over the comment-blanked text. A keyword
match is accepted only when the keyword itself starts *outside* a literal
span, so DISPLAY 'COPY ME'. can never create a USES_COPYBOOK dependency.
Static CALL 'WARR001'. still yields CALLS because the CALL keyword is real
code -- the quoted literal is the callee name, and the match starts at the
keyword, not inside the literal. The source text is never rewritten, so
evidence keeps original line numbers and verbatim source statements.

Remaining limitation: an END-EXEC token inside a string literal would
truncate EXEC SQL block matching (the block regex stops at the first
END-EXEC); such exotic SQL is outside Phase 1 scope.

The public entry point is parse_program(); the regexes are kept in
module-level constants so a future grammar-based parser can replace
the internals without changing the interface.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models.component import Component, make_component
from ..models.dependency import Dependency, Evidence

# A COPY statement: the word COPY followed by the copybook name.
_COPY_RE = re.compile(r"(?i)\bCOPY\s+([A-Za-z0-9][A-Za-z0-9_-]*)\b")
# Static CALL with a quoted literal program name.
_CALL_RE = re.compile(r"(?i)\bCALL\s+['\"]([A-Za-z0-9][A-Za-z0-9_-]*)['\"]")
# EXEC SQL ... END-EXEC blocks (may span lines).
_SQL_BLOCK_RE = re.compile(r"(?is)\bEXEC\s+SQL\b(.*?)\bEND-EXEC\b")
# SQL operations inside a block.
_SELECT_FROM_RE = re.compile(r"(?i)\bFROM\s+([A-Za-z][A-Za-z0-9_#]*)")
_INSERT_INTO_RE = re.compile(r"(?i)\bINSERT\s+INTO\s+([A-Za-z][A-Za-z0-9_#]*)")
_UPDATE_RE = re.compile(r"(?i)\bUPDATE\s+([A-Za-z][A-Za-z0-9_#]*)")
_DELETE_FROM_RE = re.compile(r"(?i)\bDELETE\s+FROM\s+([A-Za-z][A-Za-z0-9_#]*)")


def _is_comment(line: str) -> bool:
    stripped = line.lstrip()
    # COBOL fixed-format comment ('*' in column 7) and free-format '*>'
    return stripped.startswith("*") or stripped.startswith("*>") \
        or stripped.startswith("/")


def _string_literal_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of '...' and "..." string literals.

    Doubled quotes ('' and "") are COBOL escapes and do not end the
    literal. An unterminated quote is treated as an ordinary character
    so it cannot swallow the rest of the file.
    """
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'" or ch == '"':
            start = i
            i += 1
            closed = False
            while i < n:
                if text[i] == ch:
                    if i + 1 < n and text[i + 1] == ch:
                        i += 2  # doubled-quote escape, not a terminator
                        continue
                    i += 1
                    closed = True
                    break
                i += 1
            if closed:
                spans.append((start, i))
            else:
                i = start + 1  # lone quote: not a literal, keep scanning
        else:
            i += 1
    return spans


def _in_literal(pos: int, spans: list[tuple[int, int]]) -> bool:
    """True when text position `pos` falls inside a string literal span."""
    return any(s <= pos < e for s, e in spans)


def _copy_deps(program_id: str, text: str, rel: str,
               lit_spans: list[tuple[int, int]]) -> list[Dependency]:
    deps: list[Dependency] = []
    for m in _COPY_RE.finditer(text):
        if _in_literal(m.start(), lit_spans):
            continue  # e.g. DISPLAY 'COPY ME'. -- keyword is literal text
        copybook = m.group(1).upper()
        line_no = text.count("\n", 0, m.start()) + 1
        deps.append(Dependency(
            source=program_id,
            target=f"copybook:{copybook}",
            relationship="USES_COPYBOOK",
            evidence=Evidence(file=rel, line=line_no,
                              text=text.splitlines()[line_no - 1].strip()),
        ))
    return deps


def _call_deps(program_id: str, text: str, rel: str,
               lit_spans: list[tuple[int, int]]) -> list[Dependency]:
    deps: list[Dependency] = []
    for m in _CALL_RE.finditer(text):
        if _in_literal(m.start(), lit_spans):
            continue  # e.g. DISPLAY "CALL 'FAKEPGM'". -- keyword is literal
        callee = m.group(1).upper()
        line_no = text.count("\n", 0, m.start()) + 1
        deps.append(Dependency(
            source=program_id,
            target=f"program:{callee}",
            relationship="CALLS",
            evidence=Evidence(file=rel, line=line_no,
                              text=text.splitlines()[line_no - 1].strip()),
        ))
    return deps


def _delete_before_from(body: str, pos: int, body_abs: int,
                        lit_spans: list[tuple[int, int]]) -> bool:
    """True when a real (non-literal) DELETE keyword is the last keyword
    before `pos` in the SQL block body -- DELETE FROM ... is a write."""
    for dm in re.finditer(r"(?i)\bDELETE\b", body[:pos]):
        if _in_literal(body_abs + dm.start(), lit_spans):
            continue
        if re.fullmatch(r"\s*", body[dm.end():pos]):
            return True
    return False


def _sql_deps(program_id: str, text: str, rel: str,
              lit_spans: list[tuple[int, int]]) -> list[Dependency]:
    deps: list[Dependency] = []
    for block in _SQL_BLOCK_RE.finditer(text):
        if _in_literal(block.start(), lit_spans):
            continue
        body = block.group(1)
        body_abs = block.start(1)
        # 1-based line number where the EXEC SQL block starts.
        block_start_line = text.count("\n", 0, block.start()) + 1

        def abs_pos(match: re.Match) -> int:
            return body_abs + match.start()

        def ev_line(match: re.Match) -> int:
            return block_start_line + body.count("\n", 0, match.start())

        def ev_text(match: re.Match) -> str:
            line_no = text.count("\n", 0, abs_pos(match))
            return text.splitlines()[line_no].strip()

        def in_code(match: re.Match) -> bool:
            return not _in_literal(abs_pos(match), lit_spans)

        # SELECT must be real code, not literal text like 'SELECT ...'.
        has_select = any(
            not _in_literal(body_abs + sm.start(), lit_spans)
            for sm in re.finditer(r"(?i)\bSELECT\b", body)
        )

        for m in _SELECT_FROM_RE.finditer(body):
            if not in_code(m):
                continue
            # Only treat FROM as a read when the block actually SELECTs,
            # and never when the FROM belongs to a DELETE statement.
            if not has_select:
                continue
            if _delete_before_from(body, m.start(), body_abs, lit_spans):
                continue
            table = m.group(1).upper()
            deps.append(Dependency(
                source=program_id, target=f"table:{table}",
                relationship="READS_TABLE",
                evidence=Evidence(file=rel, line=ev_line(m),
                                  text=ev_text(m)),
            ))
        for m in _INSERT_INTO_RE.finditer(body):
            if not in_code(m):
                continue
            table = m.group(1).upper()
            deps.append(Dependency(
                source=program_id, target=f"table:{table}",
                relationship="WRITES_TABLE",
                evidence=Evidence(file=rel, line=ev_line(m),
                                  text=ev_text(m)),
            ))
        for m in _UPDATE_RE.finditer(body):
            if not in_code(m):
                continue
            table = m.group(1).upper()
            deps.append(Dependency(
                source=program_id, target=f"table:{table}",
                relationship="WRITES_TABLE",
                evidence=Evidence(file=rel, line=ev_line(m),
                                  text=ev_text(m)),
            ))
        for m in _DELETE_FROM_RE.finditer(body):
            if not in_code(m):
                continue
            table = m.group(1).upper()
            deps.append(Dependency(
                source=program_id, target=f"table:{table}",
                relationship="WRITES_TABLE",
                evidence=Evidence(file=rel, line=ev_line(m),
                                  text=ev_text(m)),
            ))
    return deps


def parse_program(path: Path, rel: str) -> tuple[Component, list[Dependency]]:
    """Parse one COBOL source file into a component + dependencies."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    name = path.stem.upper()
    program_id = f"program:{name}"
    component = make_component("program", name, "COBOL_PROGRAM", rel)

    # Blank (don't delete) comment lines so EXEC SQL blocks inside
    # comments cannot match, while evidence line numbers stay aligned.
    code_text = "\n".join("" if _is_comment(l) else l for l in lines)

    # Locate string literals once; keyword matches that start inside a
    # literal are filtered out (never turned into dependencies), while
    # the original text is kept verbatim for evidence.
    lit_spans = _string_literal_spans(code_text)

    deps = (
        _copy_deps(program_id, code_text, rel, lit_spans)
        + _call_deps(program_id, code_text, rel, lit_spans)
        + _sql_deps(program_id, code_text, rel, lit_spans)
    )
    return component, _dedupe(deps)


def _dedupe(deps: list[Dependency]) -> list[Dependency]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Dependency] = []
    for d in deps:
        key = (d.source, d.target, d.relationship)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out
