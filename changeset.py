#!/usr/bin/env python3
"""Phase 3A CLI: deterministic change-set & release-candidate analysis.

Two modes:

1. Explicit file list (no Git needed)::

      python changeset.py --file copybook/WARRCOPY.cpy --file cobol/WARR002.cbl

   Per-file status: ``--file PATH[:status]`` where status is one of
   modified (default), added, deleted, renamed, unknown. Ambiguous files
   (e.g. sql/schema.sql) can be resolved explicitly::

      python changeset.py --file sql/schema.sql --resolve sql/schema.sql=table:WARRANTY

2. Local Git diff (local Git metadata only, no network)::

      python changeset.py --repo . --base v1.0.0 --head main

   The Mainframe sources are read from ``--source-prefix`` (default
   ``sample_mainframe``) inside the Git repository; the head and base
   trees are extracted deterministically via ``git archive`` so results
   never depend on working-tree state.

Output is human-readable by default; ``--json`` prints the structured
ChangeSetIntelligence. ``--repo-root`` selects the Mainframe source
tree for explicit-file mode (default: sample_mainframe).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.changeset import (
    ChangeSetAnalyzer,
    ExplicitFileListProvider,
    GitDiffProvider,
    build_view,
)
from backend.changeset.ai import FakeChangeSetExplainer, get_change_set_explainer
from backend.changeset.models import ChangedFile, ChangeSet

STATUSES = ("modified", "added", "deleted", "renamed", "unknown")


def _parse_file_arg(arg: str) -> ChangedFile:
    """Parse ``PATH`` or ``PATH:status`` (status validated)."""
    path, sep, status = arg.rpartition(":")
    if sep and status in STATUSES and "/" not in status and "\\" not in status:
        return ChangedFile(path=path, status=status)  # type: ignore[arg-type]
    if sep and status not in STATUSES and ("/" in arg or "\\" in arg or ":" in path):
        # A Windows-style path or a path containing ':' that is not a
        # status suffix: treat the whole arg as the path.
        return ChangedFile(path=arg, status="modified")
    if sep and status not in STATUSES:
        raise ValueError(
            f"invalid status {status!r} in --file {arg!r}; "
            f"expected one of: {', '.join(STATUSES)}"
        )
    return ChangedFile(path=arg, status="modified")


def _parse_resolve_arg(arg: str) -> tuple[str, list[str]]:
    """Parse ``PATH=component-id[,component-id...]``."""
    path, sep, ids = arg.partition("=")
    if not sep or not path or not ids:
        raise ValueError(
            f"invalid --resolve {arg!r}; expected PATH=component-id[,component-id...]"
        )
    return path, [i.strip() for i in ids.split(",") if i.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic change-set & release-candidate analysis. "
            "Aggregates the frozen Phase 1/2A/2B engines over multiple "
            "changed files; no LLM decides mapping, impact, tests, risks, "
            "checklist items, or incidents."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python changeset.py --file copybook/WARRCOPY.cpy --file cobol/WARR002.cbl\n"
            "  python changeset.py --file sql/schema.sql --resolve sql/schema.sql=table:WARRANTY\n"
            "  python changeset.py --file copybook/UNUSED.cpy\n"
            "  python changeset.py --repo . --base v1.0.0 --head main --json\n"
        ),
    )
    parser.add_argument(
        "--file", action="append", default=[],
        help="Changed file as PATH or PATH:status (repeatable).",
    )
    parser.add_argument(
        "--resolve", action="append", default=[],
        help="Explicit ambiguity resolution: PATH=component-id[,component-id...] (repeatable).",
    )
    parser.add_argument(
        "--repo-root", default="sample_mainframe",
        help="Mainframe source tree for --file mode (default: sample_mainframe).",
    )
    parser.add_argument(
        "--repo", default=None,
        help="Git repository path for --base/--head diff mode.",
    )
    parser.add_argument("--base", default=None, help="Git base ref for diff mode.")
    parser.add_argument(
        "--head", default="HEAD", help="Git head ref for diff mode (default: HEAD)."
    )
    parser.add_argument(
        "--source-prefix", default="sample_mainframe",
        help="Subtree holding Mainframe sources inside the Git repo "
        "(default: sample_mainframe; empty string = repo root).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the structured ChangeSetIntelligence as JSON.",
    )
    parser.add_argument(
        "--fake-ai", action="store_true",
        help="Use the canned fake AI explainer on the AI code path (demos/tests).",
    )
    parser.add_argument(
        "--no-test-catalog", action="store_true",
        help="Analyze without test recommendations (for trees with no "
        "applicable test catalog).",
    )
    return parser


def _print_human(intel) -> None:
    s = intel.summary
    print("=" * 72)
    print("CHANGE-SET & RELEASE ANALYSIS (deterministic)")
    print("=" * 72)
    print()
    print("Changed files:")
    for m in intel.mapped_changes:
        print(f"  [mapped]   {m.file.path} -> {', '.join(m.component_ids)}")
    for m in intel.ambiguous_changes:
        print(f"  [ambiguous] {m.file.path}")
        for cand in m.candidate_components:
            print(f"      candidate: {cand}")
    for m in intel.unmapped_changes:
        print(f"  [unmapped] {m.file.path}")
    for m in intel.unresolved_changes:
        print(f"  [unresolved] {m.file.path} (needs base snapshot)")
    print()
    print("Per-change impact:")
    for p in intel.per_change_analysis:
        n = len(p.impact.direct_impacts) + len(p.impact.transitive_impacts)
        print(f"  {p.component_id}: {len(p.impact.direct_impacts)} direct, "
              f"{len(p.impact.transitive_impacts)} transitive ({n} total)")
    print()
    print(f"Combined impacted components ({s.unique_impacted_components} unique):")
    for e in intel.unique_impacted_components:
        print(f"  {e.component_id}")
        print(f"      impacted by: {', '.join(e.impacted_by)}")
    if intel.impacted_by_multiple_changes:
        print("Overlap (impacted by multiple changes): "
              + ", ".join(intel.impacted_by_multiple_changes))
    print()
    print(f"Recommended tests ({s.unique_recommended_tests}, "
          f"{s.must_run_tests} MUST_RUN / {s.should_run_tests} SHOULD_RUN):")
    for t in intel.recommended_tests:
        print(f"  [{t.impact_level}] {t.test_id} {t.test_name}")
        print(f"      recommended because of: {', '.join(t.recommended_because_of)}")
    print()
    print(f"Involved DB2 resources ({s.involved_db2_reads} read / "
          f"{s.involved_db2_writes} write; involved != impacted):")
    for r in intel.involved_resources:
        print(f"  [{r.access}] {r.table} "
              f"(changes: {', '.join(r.associated_change_roots)})")
    print()
    print(f"Risk signals ({s.risk_signals}):")
    for sig in intel.risk_signals:
        print(f"  [{sig.severity}] {sig.id} "
              f"(changes: {', '.join(sig.change_roots)})")
    print()
    print(f"Release checklist ({s.checklist_items}):")
    for item in intel.release_checklist:
        print(f"  {item.id}: {item.title} "
              f"(changes: {', '.join(item.applicable_change_roots)})")
    print()
    print(f"Historical incidents ({s.relevant_incidents}):")
    for agg in intel.relevant_incidents:
        inc = agg.incident
        print(f"  {inc.id} [{inc.severity}] {inc.title}")
        print(f"      relevant to: {', '.join(agg.relevant_to_changes)} "
              f"(primary reason: {agg.primary_reason.value})")
    print()
    print("-" * 72)
    print("DETERMINISTIC SUMMARY")
    print(intel.deterministic_summary)
    print()
    ai = intel.ai_explanation or {}
    print(f"Release explanation [{ai.get('explanation_source', '?')}]:")
    print(ai.get("scope_summary", ""))


def _run_explicit(args) -> int:
    try:
        files = [_parse_file_arg(f) for f in args.file]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        resolutions = dict(_parse_resolve_arg(r) for r in args.resolve)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root)
    if not repo_root.is_dir():
        print(f"error: repository directory not found: {repo_root}", file=sys.stderr)
        return 1

    provider = ExplicitFileListProvider(
        [ChangedFile(path=f.path, status=f.status, old_path=f.old_path) for f in files]
    )
    try:
        analyzer = ChangeSetAnalyzer(
            build_view(repo_root),
            catalog=[] if args.no_test_catalog else None,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    explainer = FakeChangeSetExplainer() if args.fake_ai else get_change_set_explainer()
    try:
        intel = analyzer.analyze(
            provider.get_changes(),
            resolutions=resolutions,
            provider=provider,
            explainer=explainer,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(intel.model_dump(mode="json"), indent=2))
    else:
        _print_human(intel)
    return 0


def _run_git(args) -> int:
    try:
        provider = GitDiffProvider(
            repository_path=args.repo,
            base_ref=args.base,
            head_ref=args.head,
            source_prefix=args.source_prefix,
        )
        change_set: ChangeSet = provider.get_changes()
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Extract head/base trees deterministically via git archive so results
    # never depend on working-tree state.
    with TemporaryDirectory(prefix="changeset-head-") as head_tmp, \
         TemporaryDirectory(prefix="changeset-base-") as base_tmp:
        try:
            head_root = provider.extract_tree(provider.head_ref, Path(head_tmp))
            base_root = provider.extract_tree(provider.base_ref, Path(base_tmp))
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        # The test catalog is release metadata authored for the analyzed
        # tree: if the source repo carries one at the head ref, plant it
        # into the extracted head tree so it is validated against the
        # extracted components. Foreign trees without a catalog need
        # --no-test-catalog.
        catalog_rel = (
            f"{args.source_prefix}/tests/test_catalog.yaml"
            if args.source_prefix
            else "tests/test_catalog.yaml"
        )
        catalog_bytes = None
        try:
            catalog_bytes = provider.extract_file(provider.head_ref, catalog_rel)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if catalog_bytes is not None:
            catalog_dest = head_root / "tests" / "test_catalog.yaml"
            catalog_dest.parent.mkdir(parents=True, exist_ok=True)
            catalog_dest.write_text(catalog_bytes, encoding="utf-8")
        try:
            analyzer = ChangeSetAnalyzer(
                build_view(head_root, label="head"),
                build_view(base_root, label="base"),
                catalog=[] if args.no_test_catalog else None,
            )
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        explainer = FakeChangeSetExplainer() if args.fake_ai else get_change_set_explainer()
        try:
            intel = analyzer.analyze(
                change_set, provider=provider, explainer=explainer
            )
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps(intel.model_dump(mode="json"), indent=2))
    else:
        _print_human(intel)
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    git_mode = args.repo is not None or args.base is not None
    if git_mode:
        if not args.repo or not args.base:
            print("error: git diff mode needs both --repo and --base",
                  file=sys.stderr)
            return 2
        if args.file:
            print("error: --file cannot be combined with git diff mode",
                  file=sys.stderr)
            return 2
        return _run_git(args)

    if not args.file:
        parser.print_help(sys.stderr)
        return 2
    return _run_explicit(args)


if __name__ == "__main__":
    raise SystemExit(main())
