"""Phase 3B release-blocking test: GitHub PR path == Phase 3A explicit path.

A deterministic mocked PR (WARRCOPY + WARR002 modified, snapshots
materialized from the real sample tree) must produce intelligence
semantically identical to the Phase 3A explicit file-list analysis,
excluding GitHub-specific metadata. GitHub integration must not alter
deterministic analysis.
"""
import io
import tarfile
from pathlib import Path

import httpx
import pytest

from backend.changeset import (
    ChangeSetAnalyzer,
    ExplicitFileListProvider,
    build_view,
)
from backend.github import (
    GitHubClient,
    PullRequestRequest,
    analyze_github_pull_request,
)

REPO = Path(__file__).resolve().parents[2] / "sample_mainframe"

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40

WARRCOPY = "copybook:WARRCOPY"
WARR002 = "program:WARR002"


def build_tree_tarball(top: str) -> bytes:
    """Tarball of the real sample tree under ``<top>/sample_mainframe/``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(REPO.rglob("*")):
            if path.is_file() and not path.is_symlink():
                rel = path.relative_to(REPO)
                info = tarfile.TarInfo(f"{top}/sample_mainframe/{rel}")
                info.size = path.stat().st_size
                with open(path, "rb") as fh:
                    tar.addfile(info, fh)
    return buf.getvalue()


BASE_TARBALL = build_tree_tarball(f"o-r-{BASE_SHA}")
HEAD_TARBALL = build_tree_tarball(f"o-r-{HEAD_SHA}")


def pr_payload():
    return {
        "number": 42,
        "title": "Warranty changes",
        "state": "open",
        "draft": False,
        "html_url": "https://github.com/o/r/pull/42",
        "user": {"login": "dev1"},
        "base": {"ref": "main", "sha": BASE_SHA,
                 "repo": {"full_name": "o/r"}},
        "head": {"ref": "feature", "sha": HEAD_SHA,
                 "repo": {"full_name": "o/r"}},
        "changed_files": 2,
        "additions": 20,
        "deletions": 5,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }


def files_payload():
    def f(name, n):
        return {"filename": name, "previous_filename": None,
                "status": "modified", "additions": 10, "deletions": 2,
                "changes": 12, "sha": f"{n:040d}"}
    return [
        f("sample_mainframe/copybook/WARRCOPY.cpy", 1),
        f("sample_mainframe/cobol/WARR002.cbl", 2),
    ]


def mock_handler(request):
    host, path = request.url.host, request.url.path
    if host == "api.github.com":
        if path == "/repos/o/r/pulls/42":
            return httpx.Response(200, json=pr_payload())
        if path == "/repos/o/r/pulls/42/files":
            return httpx.Response(200, json=files_payload())
        if path == f"/repos/o/r/tarball/{BASE_SHA}":
            loc = f"https://codeload.github.com/o/r/tarball/{BASE_SHA}/x"
            return httpx.Response(302, headers={"location": loc})
        if path == f"/repos/o/r/tarball/{HEAD_SHA}":
            loc = f"https://codeload.github.com/o/r/tarball/{HEAD_SHA}/y"
            return httpx.Response(302, headers={"location": loc})
    if host == "codeload.github.com":
        assert "authorization" not in request.headers
        if BASE_SHA in path:
            return httpx.Response(200, content=BASE_TARBALL)
        return httpx.Response(200, content=HEAD_TARBALL)
    raise AssertionError(f"unexpected request {request.url}")


@pytest.fixture(scope="module")
def github_result():
    client = GitHubClient(
        token="test", transport=httpx.MockTransport(mock_handler),
        max_retries=0)
    try:
        return analyze_github_pull_request(
            PullRequestRequest(owner="o", repo="r", pull_number=42,
                               source_root="sample_mainframe"),
            client=client,
        )
    finally:
        client.close()


@pytest.fixture(scope="module")
def explicit_intel():
    analyzer = ChangeSetAnalyzer(build_view(REPO))
    provider = ExplicitFileListProvider(
        [{"path": "copybook/WARRCOPY.cpy"},
         {"path": "cobol/WARR002.cbl"}]
    )
    return analyzer.analyze(
        provider.get_changes(), provider=provider, explainer=None)


def _norm(intel):
    """Normalized deterministic projection for semantic comparison."""
    return {
        "summary": intel.summary.model_dump(),
        "changed": sorted(c.component_id for c in intel.changed_components),
        "cross": {
            c.component_id: sorted(c.also_impacted_by)
            for c in intel.changed_components
        },
        "downstream": sorted(
            (e.component_id, tuple(sorted(e.impacted_by)))
            for e in intel.unique_impacted_components
        ),
        "overlap": sorted(intel.impacted_by_multiple_changes),
        "tests": sorted(
            (t.test_id, t.impact_level) for t in intel.recommended_tests),
        "resources": sorted(
            (r.table, r.access) for r in intel.involved_resources),
        "signals": sorted(s.id for s in intel.risk_signals),
        "checklist": sorted(i.id for i in intel.release_checklist),
        "incidents": sorted(a.incident.id for a in intel.relevant_incidents),
        "per_root": sorted(
            (p.component_id, p.snapshot, tuple(sorted(p.impact.direct_impacts)),
             tuple(sorted(p.impact.transitive_impacts)))
            for p in intel.per_change_analysis
        ),
        "deterministic_summary": intel.deterministic_summary,
        "mapped": sorted(
            (m.file.path, m.mapping_status, tuple(sorted(m.component_ids)))
            for m in intel.mapped_changes
        ),
    }


def test_equivalence(github_result, explicit_intel):
    """The release-blocking invariant: identical deterministic semantics."""
    assert _norm(github_result.change_set_intelligence) == _norm(explicit_intel)


def test_expected_primary_numbers(github_result):
    """Phase 3A's verified primary-demo numbers, via the GitHub path."""
    s = github_result.change_set_intelligence.summary
    assert s.changed_components == 2
    assert s.cross_impacted_changed_components == 1
    assert s.unique_impacted_components == 4
    assert s.direct_impact_union == 3
    assert s.transitive_impact_union == 3
    assert s.overlap_impacted_components == 3
    assert s.unique_recommended_tests == 7
    assert s.must_run_tests == 6
    assert s.should_run_tests == 1
    assert s.involved_db2_reads == 1
    assert s.involved_db2_writes == 2
    assert s.risk_signals == 7
    assert s.checklist_items == 7
    assert s.relevant_incidents == 11


def test_github_provenance_present(github_result):
    assert github_result.provider == "github"
    assert github_result.repository == "o/r"
    assert github_result.pull_request.base_sha == BASE_SHA
    assert github_result.pull_request.head_sha == HEAD_SHA
    assert len(github_result.in_scope_files) == 2
    assert github_result.outside_scope_files == []
    assert github_result.base_snapshot.sha == BASE_SHA
    assert github_result.head_snapshot.sha == HEAD_SHA
    assert github_result.base_snapshot.repository_full_name == "o/r"
    by_name = {f.filename: f for f in github_result.in_scope_files}
    w = by_name["sample_mainframe/copybook/WARRCOPY.cpy"]
    assert w.mapping_status == "mapped"
    assert w.mapped_components == [WARRCOPY]
    assert w.source_relative_path == "copybook/WARRCOPY.cpy"
    assert w.phase3a_snapshot == "head"


def test_change_set_source_marked(github_result):
    intel = github_result.change_set_intelligence
    assert intel.change_set.source == "github-pr"
    assert intel.change_set.base_ref == BASE_SHA
    assert intel.change_set.head_ref == HEAD_SHA
