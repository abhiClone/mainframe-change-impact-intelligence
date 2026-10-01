"""Phase 3B: API endpoint tests (service layer mocked; no live GitHub)."""
import json

import pytest
from fastapi.testclient import TestClient

import backend.api.github as github_api
from backend.github import GitHubError
from backend.github.models import (
    GitHubPullRequestAnalysis,
    PullRequestMetadata,
    SnapshotMetadata,
)

FAKE_TOKEN = "ghp_SUPER_SECRET_TEST_VALUE"


def _analysis():
    from backend.changeset.models import ChangeSetIntelligence, ChangeSetSummary

    intel = ChangeSetIntelligence(
        change_set={"files": [], "source": "github-pr"},
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
    return GitHubPullRequestAnalysis(
        repository="o/r",
        pull_request=PullRequestMetadata(number=42, base_sha="a" * 40,
                                         head_sha="b" * 40),
        source_root=".",
        base_snapshot=SnapshotMetadata(label="base",
                                       repository_full_name="o/r",
                                       sha="a" * 40),
        head_snapshot=SnapshotMetadata(label="head",
                                       repository_full_name="o/r",
                                       sha="b" * 40),
        change_set_intelligence=intel,
    )


@pytest.fixture()
def client(monkeypatch):
    def fake_analyze(request, **kwargs):
        return _analysis()

    monkeypatch.setattr(
        github_api, "analyze_github_pull_request", fake_analyze)
    from backend.api.app import app
    return TestClient(app)


def test_analyze_ok(client):
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 42,
        "source_root": "sample_mainframe",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "github"
    assert body["repository"] == "o/r"
    assert body["pull_request"]["number"] == 42
    assert "change_set_intelligence" in body
    assert FAKE_TOKEN not in resp.text


def test_analyze_defaults_source_root(client):
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 1})
    assert resp.status_code == 200


@pytest.mark.parametrize("payload", [
    {"owner": "o", "repo": "r", "pull_number": 0},
    {"owner": "o", "repo": "r", "pull_number": -3},
    {"owner": "o", "repo": "r", "pull_number": 1, "source_root": ".."},
    {"owner": "o", "repo": "r", "pull_number": 1,
     "source_root": "/tmp/x"},
    {"owner": "not an owner!!", "repo": "r", "pull_number": 1},
    {"owner": "o", "repo": "r", "pull_number": "abc"},
])
def test_analyze_invalid_input_422(client, payload):
    resp = client.post("/api/github/pull-request/analyze", json=payload)
    assert resp.status_code == 422


def _error_client(monkeypatch, error):
    def fake_analyze(request, **kwargs):
        raise error

    monkeypatch.setattr(
        github_api, "analyze_github_pull_request", fake_analyze)
    from backend.api.app import app
    return TestClient(app)


@pytest.mark.parametrize("code,status", [
    ("repository_not_found_or_not_authorized", 404),
    ("pull_request_not_found", 404),
    ("github_authentication_failed", 401),
    ("github_rate_limited", 429),
    ("github_unavailable", 502),
    ("incomplete_change_set", 422),
    ("unsupported_github_status", 422),
    ("snapshot_download_failed", 502),
    ("snapshot_too_large", 413),
    ("unsafe_archive", 422),
    ("invalid_source_root", 400),
    ("head_snapshot_unavailable", 422),
    ("analysis_failed", 500),
])
def test_error_mapping(monkeypatch, code, status):
    client = _error_client(
        monkeypatch, GitHubError(code, "safe message"))
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 42})
    assert resp.status_code == status
    body = resp.json()["detail"]
    assert body["code"] == code
    assert body["message"] == "safe message"
    assert FAKE_TOKEN not in resp.text


def test_status_endpoint_no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from backend.api.app import app
    resp = TestClient(app).get("/api/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"provider": "github", "auth_configured": False}


def test_status_endpoint_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)
    from backend.api.app import app
    resp = TestClient(app).get("/api/github/status")
    assert resp.json()["auth_configured"] is True
    # No credential material anywhere in the response.
    assert FAKE_TOKEN not in resp.text
    assert "token" not in resp.text.lower().replace(
        "auth_configured", "")


def test_existing_endpoints_untouched(client):
    # Phase 3A endpoint still served by the same app.
    resp = client.post("/api/change-set/analyze", json={"files": []})
    assert resp.status_code in (200, 400, 500)  # routed, not 404
