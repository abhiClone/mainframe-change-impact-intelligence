"""JCL job and PROC parser (Phase 1: regex-based, modular interface).

JCL jobs:
  //STEP010 EXEC PGM=<pgm>    -> EXECUTES_PROGRAM  (job -> program)
  //STEP020 EXEC PROC=<proc>   -> USES_PROC         (job -> proc)

JCL PROCs:
  //STEP01 EXEC PGM=<pgm>      -> EXECUTES_PROGRAM  (proc -> program)

Comment lines (//*) are skipped. Continuation lines are not needed for
Phase 1 synthetic data but EXEC statements are matched per-line.

Intentionally unsupported (documented, negative-tested):
  - positional PROC execution without the PROC= keyword
    (//STEP020 EXEC WARRANTY): ignored, never guessed
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models.component import Component, make_component
from ..models.dependency import Dependency, Evidence

_EXEC_PGM_RE = re.compile(r"(?i)^//\S+\s+EXEC\s+PGM=([A-Za-z0-9@#$]+)")
_EXEC_PROC_RE = re.compile(r"(?i)^//\S+\s+EXEC\s+PROC=([A-Za-z0-9@#$]+)")
_PROC_DEF_RE = re.compile(r"(?i)^//([A-Za-z0-9@#$]+)\s+PROC\b")


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("//*")


def _exec_pgm_deps(owner_id: str, lines: list[str], rel: str) -> list[Dependency]:
    deps: list[Dependency] = []
    for lineno, line in enumerate(lines, start=1):
        if _is_comment(line):
            continue
        m = _EXEC_PGM_RE.match(line.strip())
        if m:
            pgm = m.group(1).upper()
            deps.append(Dependency(
                source=owner_id,
                target=f"program:{pgm}",
                relationship="EXECUTES_PROGRAM",
                evidence=Evidence(file=rel, line=lineno,
                                  text=line.strip()),
            ))
    return deps


def parse_job(path: Path, rel: str) -> tuple[Component, list[Dependency]]:
    """Parse one JCL job file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    name = path.stem.upper()
    job_id = f"job:{name}"
    component = make_component("job", name, "JCL_JOB", rel)

    deps = _exec_pgm_deps(job_id, lines, rel)
    for lineno, line in enumerate(lines, start=1):
        if _is_comment(line):
            continue
        m = _EXEC_PROC_RE.match(line.strip())
        if m:
            proc = m.group(1).upper()
            deps.append(Dependency(
                source=job_id,
                target=f"proc:{proc}",
                relationship="USES_PROC",
                evidence=Evidence(file=rel, line=lineno,
                                  text=line.strip()),
            ))
    return component, deps


def parse_proc(path: Path, rel: str) -> tuple[Component, list[Dependency]]:
    """Parse one JCL procedure file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    name = path.stem.upper()
    for line in lines:  # prefer the name from the PROC definition line
        m = _PROC_DEF_RE.match(line.strip())
        if m:
            name = m.group(1).upper()
            break
    proc_id = f"proc:{name}"
    component = make_component("proc", name, "JCL_PROC", rel)
    return component, _exec_pgm_deps(proc_id, lines, rel)
