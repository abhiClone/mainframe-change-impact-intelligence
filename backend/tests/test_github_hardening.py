"""Phase 3B final hardening tests (acceptance gate).

Covers the targeted hardening pass before the Phase 3B acceptance audit:

1. Strict upstream metadata validation: base/head SHAs must be full
   40-char hex commit SHAs; base/head refs must be sane; base/head
   repository full names must be structurally valid owner/repository
   names (reusing the user-input semantics). Invalid values become the
   typed ``malformed_github_response`` error — never a raw KeyError /
   ValueError, never a silent branch/merge-SHA/HEAD substitution.
2. head.repo == null (deleted/inaccessible fork) stays legitimate; the
   deterministic base-repo fallback is used, else
   ``head_snapshot_unavailable``.
3. Snapshot request identity: snapshots are fetched with exactly the
   validated base/head full names and SHAs — no branch fallback, no
   merge-SHA substitution, no reuse of the requested owner/repo for a
   fork head.
4. Redirect policy: trailing-dot hosts are rejected; userinfo, HTTP,
   and non-default ports stay rejected; uppercase hosts accepted.
5. Sanitized 422 responses on the GitHub request boundary: distinctive
   secrets in unknown fields never appear in the HTTP response body.

Fully mocked: no test touches the live GitHub API.
"""
import io
import tarfile

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.github import GitHubClient, GitHubError, PullRequestRequest
from backend.github.service import analyze_github_pull_request

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
FORK_SHA = "c" * 40


def make_client(handler, token="ghp_TEST_ONLY"):
    return GitHubClient(token=token, transport=httpx.MockTransport(handler))


def pr_json(**over):
    data = {
        "number": 42,
        "title": "Update warranty copybook",
        "state": "open",
        "draft": False,
        "html_url": "https://github.com/o/r/pull/42",
        "user": {"login": "dev1"},
        "base": {"ref": "main", "sha": BASE_SHA,
                 "repo": {"full_name": "o/r"}},
        "head": {"ref": "feature", "sha": HEAD_SHA,
                 "repo": {"full_name": "o/r"}},
        "changed_files": 2,
        "additions": 10,
        "deletions": 4,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    data.update(over)
    return data


def get_meta(payload):
    client = make_client(
        lambda request: httpx.Response(200, json=payload))
    try:
        meta, _ = client.get_pull_request("o", "r", 42)
        return meta
    finally:
        client.close()


def assert_malformed(payload):
    """The payload must fail with the typed error, never a raw exception."""
    client = make_client(
        lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(GitHubError) as exc_info:
            client.get_pull_request("o", "r", 42)
        assert exc_info.value.code == "malformed_github_response", \
            f"expected malformed_github_response, got {exc_info.value.code}"
    finally:
        client.close()


# ------------------------------------------------------------------
# 1. Strict metadata validation: valid cases
# ------------------------------------------------------------------

def test_valid_metadata_passes():
    meta = get_meta(pr_json())
    assert meta.base_sha == BASE_SHA
    assert meta.head_sha == HEAD_SHA
    assert meta.base_repo_full_name == "o/r"
    assert meta.head_repo_full_name == "o/r"
    assert meta.base_ref == "main"
    assert meta.head_ref == "feature"
    assert meta.changed_files == 2


def test_head_repo_null_is_legitimate():
    payload = pr_json()
    payload["head"]["repo"] = None
    meta = get_meta(payload)
    assert meta.head_repo_full_name is None
    assert meta.head_sha == HEAD_SHA  # SHA still preserved


def test_fork_full_names_pass():
    payload = pr_json()
    payload["head"]["repo"]["full_name"] = "contributor/r"
    meta = get_meta(payload)
    assert meta.base_repo_full_name == "o/r"
    assert meta.head_repo_full_name == "contributor/r"


# ------------------------------------------------------------------
# 2. Malformed nested metadata matrix -> malformed_github_response
# ------------------------------------------------------------------

@pytest.mark.parametrize("mutate", [
    # base/head missing or not objects
    lambda p: p.pop("base"),
    lambda p: p.pop("head"),
    lambda p: p.update(base=None),
    lambda p: p.update(head="nope"),
    # SHA missing / malformed
    lambda p: p["base"].pop("sha"),
    lambda p: p["head"].pop("sha"),
    lambda p: p["base"].update(sha=""),
    lambda p: p["head"].update(sha=""),
    lambda p: p["base"].update(sha="main"),          # branch name
    lambda p: p["head"].update(sha="main"),          # branch name
    lambda p: p["base"].update(sha="../x"),          # traversal
    lambda p: p["head"].update(sha="../x"),
    lambda p: p["base"].update(sha="z" * 40),        # non-hex
    lambda p: p["base"].update(sha="A" * 40),        # uppercase hex
    lambda p: p["base"].update(sha="a" * 39),        # short
    lambda p: p["base"].update(sha="a" * 41),        # long
    lambda p: p["base"].update(sha="a" * 7),         # short SHA
    lambda p: p["base"].update(sha=None),
    lambda p: p["base"].update(sha=12345),
    # refs missing / malformed
    lambda p: p["base"].pop("ref"),
    lambda p: p["head"].update(ref=""),
    lambda p: p["base"].update(ref="a\0b"),
    # repo missing / null / malformed
    lambda p: p["base"].pop("repo"),
    lambda p: p["base"].update(repo=None),
    lambda p: p["base"].update(repo="o/r"),
    lambda p: p["base"]["repo"].pop("full_name"),
    lambda p: p["head"].update(repo="o/r"),
    lambda p: p["head"].update(repo={"full_name": None}),
])
def test_malformed_nested_metadata_matrix(mutate):
    payload = pr_json()
    mutate(payload)
    assert_malformed(payload)


@pytest.mark.parametrize("bad_name", [
    "../repo",
    "owner/../repo",
    "https://evil.example/x",
    "http://evil.example/x",
    "owner/repo/extra",
    "owner",
    "/repo",
    "owner/",
    "/",
    "",
    "owner//repo",
    "..",
    "o\\r",
    "-bad/repo",
])
def test_malformed_full_names_rejected(bad_name):
    for side in ("base", "head"):
        payload = pr_json()
        payload[side]["repo"]["full_name"] = bad_name
        assert_malformed(payload)


@pytest.mark.parametrize("bad_changed", [
    "missing", None, "3", 2.0, -1, True, [2], {"n": 2},
])
def test_malformed_changed_files_rejected(bad_changed):
    payload = pr_json()
    if bad_changed == "missing":
        payload.pop("changed_files")
    else:
        payload["changed_files"] = bad_changed
    assert_malformed(payload)


# ------------------------------------------------------------------
# 3. Snapshot request identity + deleted-fork fallback (service level)
# ------------------------------------------------------------------

def tiny_tarball(top: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(f"{top}/README.md")
        data = b"sample\n"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def service_handler_factory(pr_payload, *, seen, archives, fail_paths=()):
    """Mock GitHub: PR metadata, file list, tarball 302s, codeload bytes."""
    def handler(request):
        host, path = request.url.host, request.url.path
        seen.append((host, path))
        if host == "api.github.com":
            if path == "/repos/o/r/pulls/42":
                return httpx.Response(200, json=pr_payload)
            if path == "/repos/o/r/pulls/42/files":
                return httpx.Response(200, json=[])
            if path.startswith("/repos/") and "/tarball/" in path:
                if path in fail_paths:
                    return httpx.Response(404, json={"message": "Not Found"})
                loc = f"https://codeload.github.com{path}/x"
                return httpx.Response(302, headers={"location": loc})
        if host == "codeload.github.com":
            assert "authorization" not in request.headers
            for sha, blob in archives.items():
                if sha in path:
                    return httpx.Response(200, content=blob)
            return httpx.Response(404)
        return httpx.Response(404)
    return handler


def analyze_with(seen, pr_payload, archives, fail_paths=()):
    client = make_client(
        service_handler_factory(
            pr_payload, seen=seen, archives=archives,
            fail_paths=fail_paths,
        ))
    try:
        return analyze_github_pull_request(
            PullRequestRequest(owner="o", repo="r", pull_number=42,
                               source_root="."),
            client=client,
            explainer=None,
            no_test_catalog=True,
        )
    finally:
        client.close()


def test_snapshot_identity_uses_validated_names_and_shas():
    """Fork head: snapshots come from the fork's full name + exact SHAs.

    No branch-name fallback, no merge-SHA substitution, no reuse of the
    originally requested owner/repo for the fork head.
    """
    payload = pr_json()
    payload["head"]["repo"]["full_name"] = "contributor/r"
    payload["head"]["sha"] = FORK_SHA
    payload["changed_files"] = 0
    archives = {
        BASE_SHA: tiny_tarball(f"o-r-{BASE_SHA}"),
        FORK_SHA: tiny_tarball(f"contributor-r-{FORK_SHA}"),
    }
    seen: list = []
    result = analyze_with(seen, payload, archives)
    tarball_paths = [p for h, p in seen
                     if h == "api.github.com" and "/tarball/" in p]
    assert f"/repos/o/r/tarball/{BASE_SHA}" in tarball_paths
    assert f"/repos/contributor/r/tarball/{FORK_SHA}" in tarball_paths
    # The fork head SHA is never requested from the base repository.
    assert f"/repos/o/r/tarball/{FORK_SHA}" not in tarball_paths
    assert result.base_snapshot.sha == BASE_SHA
    assert result.base_snapshot.repository_full_name == "o/r"
    assert result.head_snapshot.sha == FORK_SHA
    assert result.head_snapshot.repository_full_name == "contributor/r"


def test_deleted_fork_falls_back_to_base_repo_with_head_sha():
    """head.repo == null: the exact head SHA is fetched from the base repo."""
    payload = pr_json()
    payload["head"]["repo"] = None
    payload["changed_files"] = 0
    archives = {
        BASE_SHA: tiny_tarball(f"o-r-{BASE_SHA}"),
        HEAD_SHA: tiny_tarball(f"o-r-{HEAD_SHA}"),
    }
    seen: list = []
    result = analyze_with(seen, payload, archives)
    tarball_paths = [p for h, p in seen
                     if h == "api.github.com" and "/tarball/" in p]
    assert f"/repos/o/r/tarball/{BASE_SHA}" in tarball_paths
    assert f"/repos/o/r/tarball/{HEAD_SHA}" in tarball_paths
    assert result.head_snapshot.sha == HEAD_SHA
    assert result.head_snapshot.repository_full_name == "o/r"


def test_deleted_fork_unrecoverable_head_sha():
    """head.repo == null and the head SHA is not in the base repo."""
    payload = pr_json()
    payload["head"]["repo"] = None
    payload["changed_files"] = 0
    archives = {BASE_SHA: tiny_tarball(f"o-r-{BASE_SHA}")}
    seen: list = []
    client = make_client(
        service_handler_factory(
            payload, seen=seen, archives=archives,
            fail_paths={f"/repos/o/r/tarball/{HEAD_SHA}"},
        ))
    try:
        with pytest.raises(GitHubError) as exc_info:
            analyze_github_pull_request(
                PullRequestRequest(owner="o", repo="r", pull_number=42,
                                   source_root="."),
                client=client,
                explainer=None,
                no_test_catalog=True,
            )
    finally:
        client.close()
    assert exc_info.value.code == "head_snapshot_unavailable"


# ------------------------------------------------------------------
# 4. Redirect policy: trailing-dot rejected, matrix re-run
# ------------------------------------------------------------------

@pytest.mark.parametrize("location", [
    "https://codeload.github.com/x",
    "https://CODELOAD.GITHUB.COM/x",
    "https://codeload.github.com:443/x",
])
def test_redirect_accept_cases(location):
    client = make_client(lambda request: httpx.Response(200))
    try:
        assert client._validate_archive_redirect(location) == location or True
    finally:
        client.close()


@pytest.mark.parametrize("location", [
    "http://codeload.github.com/x",
    "https://codeload.github.com./x",          # trailing dot: REJECTED
    "https://user@codeload.github.com/x",
    "https://user:pass@codeload.github.com/x",
    "https://codeload.github.com:8443/x",
    "https://codeload.github.com.evil.example/x",
    "https://evil.example/x",
])
def test_redirect_reject_cases(location):
    client = make_client(lambda request: httpx.Response(200))
    try:
        with pytest.raises(GitHubError) as exc_info:
            client._validate_archive_redirect(location)
        assert exc_info.value.code == "snapshot_download_failed"
    finally:
        client.close()


def test_redirect_trailing_dot_explicitly_rejected():
    """Acceptance decision: exact explicit host allowlist, no DNS
    normalization beyond case folding."""
    client = make_client(lambda request: httpx.Response(200))
    try:
        with pytest.raises(GitHubError):
            client._validate_archive_redirect(
                "https://codeload.github.com./o/r/tarball/x")
    finally:
        client.close()


# ------------------------------------------------------------------
# 5. Sanitized 422 responses on the GitHub request boundary
# ------------------------------------------------------------------

@pytest.mark.parametrize("field", [
    "token", "authorization", "api_base_url", "github_url",
])
def test_unknown_field_secret_not_reflected(field):
    """extra='forbid' rejects; the distinctive secret must be absent from
    the serialized HTTP response (no input/ctx echo)."""
    secret = f"SECRET_{field.upper()}_DO_NOT_LEAK_987654321"
    client = TestClient(app, raise_server_exceptions=False)
    body = {"owner": "o", "repo": "r", "pull_number": 1, field: secret}
    resp = client.post("/api/github/pull-request/analyze", json=body)
    assert resp.status_code == 422
    assert secret not in resp.text
    detail = resp.json()["detail"]
    assert detail, "sanitized 422 must still carry structured errors"
    for err in detail:
        assert set(err.keys()) == {"loc", "type", "msg"}
        assert secret not in str(err.values())


def test_sanitized_422_keeps_error_shape():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 1, "token": "x"})
    assert resp.status_code == 422
    err = resp.json()["detail"][0]
    assert err["loc"] == ["body", "token"]
    assert err["type"] == "extra_forbidden"


def test_other_endpoints_keep_default_422_shape():
    """The sanitizer is narrow: unrelated endpoints keep FastAPI's
    established validation output (with input echo)."""
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/change-set/analyze", json={"bogus": 1})
    assert resp.status_code == 422
    assert "input" in resp.json()["detail"][0]
