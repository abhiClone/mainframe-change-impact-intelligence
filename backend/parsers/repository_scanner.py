"""Repository scanner: walks the synthetic mainframe repo and produces
the normalized component + dependency lists.

Layout expected:
  <repo>/cobol/*.cbl
  <repo>/copybook/*.cpy
  <repo>/jcl/*.jcl
  <repo>/proc/*.proc
  <repo>/sql/*.sql   (DDL; CREATE TABLE -> DB2_TABLE)

Targets that are referenced but have no source file of their own
(e.g. a program CALLed but not present) are materialized as
"unresolved" components so the graph stays connected; they are
explicitly marked rather than silently dropped. In the Phase 1
synthetic repo every reference resolves.
"""
from __future__ import annotations

from pathlib import Path

from ..models.component import Component, make_component
from ..models.dependency import Dependency
from .cobol_parser import parse_program
from .jcl_parser import parse_job, parse_proc
from .sql_parser import parse_schema


def _rel(repo: Path, path: Path) -> str:
    return str(path.relative_to(repo)).replace("\\", "/")


def scan_repository(repo_root: str | Path) -> tuple[list[Component], list[Dependency]]:
    repo = Path(repo_root)
    components: dict[str, Component] = {}
    dependencies: list[Dependency] = []

    def add(comp: Component) -> None:
        components.setdefault(comp.id, comp)

    def ensure_target(dep: Dependency) -> None:
        if dep.target not in components:
            kind = dep.target.split(":", 1)[0]
            name = dep.target.split(":", 1)[1]
            type_map = {
                "program": "COBOL_PROGRAM",
                "copybook": "COPYBOOK",
                "table": "DB2_TABLE",
                "proc": "JCL_PROC",
                "job": "JCL_JOB",
            }
            add(make_component(kind, name,
                               type_map.get(kind, "UNKNOWN"),
                               source_file="unknown"))

    # 1. Copybooks (every .cpy becomes a component, referenced or not).
    for path in sorted((repo / "copybook").glob("*.cpy")):
        rel = _rel(repo, path)
        add(make_component("copybook", path.stem.upper(), "COPYBOOK", rel))

    # 2. DB2 tables from DDL.
    for path in sorted((repo / "sql").glob("*.sql")):
        for comp in parse_schema(path, _rel(repo, path)):
            add(comp)

    # 3. COBOL programs + their dependencies.
    for path in sorted((repo / "cobol").glob("*.cbl")):
        comp, deps = parse_program(path, _rel(repo, path))
        add(comp)
        for d in deps:
            ensure_target(d)
        dependencies.extend(deps)

    # 4. JCL jobs.
    for path in sorted((repo / "jcl").glob("*.jcl")):
        comp, deps = parse_job(path, _rel(repo, path))
        add(comp)
        for d in deps:
            ensure_target(d)
        dependencies.extend(deps)

    # 5. PROCs.
    for path in sorted((repo / "proc").glob("*.proc")):
        comp, deps = parse_proc(path, _rel(repo, path))
        add(comp)
        for d in deps:
            ensure_target(d)
        dependencies.extend(deps)

    return list(components.values()), dependencies
