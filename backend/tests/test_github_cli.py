"""Phase 3B: CLI tests (no live GitHub; service layer mocked)."""
import json

import pytest

import github_pr
from backend.github import GitHubError


def _fake_result():
    from backend.github.models import (
        GitHubChangedFile,
        GitHubFileStatus,
        GitHubPullRequestAnalysis,
        PullRequestMetadata,
        SnapshotMetadata,
        SourceScope,
    )
    from backend.changeset.models import ChangeSetIntelligence, ChangeSetSummary

    intel = ChangeSetIntelligence(
        change_set={"files": [], "source": "github-pr"},
        deterministic_summary="deterministic",
        summary=ChangeSetSummary(
            changed_files=0, changed_components=0,
            cross_impacted_changed_components=0, ambiguous_files=0,
            unmapped_files=0, unresolved_files=0, direct_impact_union=0,
            transitive_impact_union=0, unique_impacted_components=0,
            overlap_impacted_components=0, unique_recommended_tests=0,
            must_run_tests=0, should_run_tests=0, involved_db2_reads=0,
            involved_db2_writes=0, risk_signals=0, checklist_items=0,
            relevant_incidents=0,
        ),
    )
    pr = PullRequestMetadata(
        number=42, title="T", state="open", draft=False,
        html_url="https://github.com/o/r/pull/42", author_login="dev",
        base_ref="main", base_sha="a" * 40, base_repo_full_name="o/r",
        head_ref="feat", head_sha="b" * 40, head_repo_full_name="o/r",
        changed_files=1, additions=1, deletions=0)
    f = GitHubChangedFile(
        filename="sample_mainframe/copybook/WARRCOPY.cpy",
        status=GitHubFileStatus.MODIFIED,
        source_scope=SourceScope.IN_SOURCE_SCOPE,
        effective_status="modified",
        source_relative_path="copybook/WARRCOPY.cpy",
        mapping_status="mapped", mapped_components=["copybook:WARRCOPY"],
        phase3a_snapshot="head")
    return GitHubPullRequestAnalysis(
        repository="o/r", pull_request=pr, source_root="sample_mainframe",
        github_files=[f], in_scope_files=[f], outside_scope_files=[],
        base_snapshot=SnapshotMetadata(label="base",
                                       repository_full_name="o/r",
                                       sha="a" * 40, file_count=3),
        head_snapshot=SnapshotMetadata(label="head",
                                       repository_full_name="o/r",
                                       sha="b" * 40, file_count=3),
        change_set_intelligence=intel)


@pytest.fixture()
def fake_service(monkeypatch):
    monkeypatch.setattr(
        github_pr, "analyze_github_pull_request",
        lambda request, **kw: _fake_result())


def test_cli_has_no_token_flag():
    import argparse

    # Rebuild the parser the same way main() does, via --help text.
    import subprocess, sys
    out = subprocess.run(
        [sys.executable, "github_pr.py", "--help"],
        capture_output=True, text=True, cwd=".")
    assert out.returncode == 0
    assert "--token" not in out.stdout
    assert "token" not in out.stdout.lower()


def test_cli_human_output(monkeypatch, fake_service, capsys, tmp_path):
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo", "o/r",
                                     "--pr", "42"])
    assert github_pr.main() == 0
    out = capsys.readouterr().out
    assert "GITHUB PULL REQUEST" in out
    assert "PR #42" in out
    assert "aaaaaaa" in out  # short base SHA
    assert "bbbbbbb" in out  # short head SHA
    assert "IN SCOPE" in out
    assert "VERIFIED PR CHANGE SET" in out


def test_cli_json_output(monkeypatch, fake_service, capsys):
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo", "o/r",
                                     "--pr", "42", "--json"])
    assert github_pr.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["provider"] == "github"
    assert body["pull_request"]["number"] == 42


def test_cli_rejects_url_repo(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo",
                                     "https://github.com/o/r", "--pr", "1"])
    assert github_pr.main() == 2
    assert "error" in capsys.readouterr().err


def test_cli_rejects_bad_pr(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo", "o/r",
                                     "--pr", "0"])
    assert github_pr.main() == 2


def test_cli_github_error(monkeypatch, capsys):
    def boom(request, **kw):
        raise GitHubError("pull_request_not_found", "nope")

    monkeypatch.setattr(github_pr, "analyze_github_pull_request", boom)
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo", "o/r",
                                     "--pr", "42"])
    assert github_pr.main() == 1
    err = capsys.readouterr().err
    assert "[pull_request_not_found]" in err


def test_cli_never_prints_token(monkeypatch, fake_service, capsys):
    fake = "ghp_SUPER_SECRET_TEST_VALUE"
    monkeypatch.setenv("GITHUB_TOKEN", fake)
    monkeypatch.setattr("sys.argv", ["github_pr.py", "--repo", "o/r",
                                     "--pr", "42", "--json"])
    assert github_pr.main() == 0
    out = capsys.readouterr().out
    assert fake not in out
