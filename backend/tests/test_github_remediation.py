"""Phase 3B remediation tests (M1, L1-L7).

Targeted regression coverage for the post-audit remediation:

- M1: archive redirect targets containing URL userinfo are rejected;
  non-default ports are rejected; exact normalized hostname comparison.
- Final-send proof: for 301/302/303/307/308 the archive request as
  received by the transport carries no Authorization (Bearer or Basic)
  and no Proxy-Authorization header.
- L1: secondary rate limits (403 + Retry-After) classify as
  github_rate_limited; ordinary 403s do not; no retry storm.
- L2: malformed upstream field types become typed
  malformed_github_response errors, never raw ValueError / HTTP 500.
- L3: the API request model rejects unknown fields (extra="forbid").
- L4: source_root has a documented length bound.
- L6: negative changed_files is malformed metadata.

Fully mocked: no test touches the live GitHub API.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.github import GitHubClient, GitHubError
from backend.github.models import (
    PullRequestRequest,
    validate_source_root,
    SOURCE_ROOT_MAX_LENGTH,
)
from backend.github.provider import translate_github_files

FAKE_TOKEN = "ghp_SUPER_SECRET_TEST_VALUE"

BASE_SHA = "a" * 40


def make_client(handler, token=FAKE_TOKEN):
    transport = httpx.MockTransport(handler)
    return GitHubClient(token=token, transport=transport)


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
        "head": {"ref": "feature", "sha": "b" * 40,
                 "repo": {"full_name": "o/r"}},
        "changed_files": 0,
        "additions": 0,
        "deletions": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    data.update(over)
    return data


def file_json(name, **over):
    data = {
        "filename": name,
        "previous_filename": None,
        "status": "modified",
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "sha": "c" * 40,
    }
    data.update(over)
    return data


# ------------------------------------------------------------------
# M1: redirect target validation matrix
# ------------------------------------------------------------------

@pytest.mark.parametrize("location", [
    "https://user:pass@codeload.github.com/o/r/tarball/x",
    "https://user@codeload.github.com/o/r/tarball/x",
    "https://:pass@codeload.github.com/o/r/tarball/x",
    "https://codeload.github.com:8443/o/r/tarball/x",
    "https://objects.githubusercontent.com:444/o/r/tarball/x",
])
def test_redirect_userinfo_and_non_default_port_rejected(location):
    """M1: userinfo of any kind and non-default ports are refused."""
    client = make_client(lambda request: httpx.Response(200))
    with pytest.raises(GitHubError) as exc_info:
        client._validate_archive_redirect(location)
    assert exc_info.value.code == "snapshot_download_failed"
    client.close()


@pytest.mark.parametrize("location", [
    "http://codeload.github.com/o/r/tarball/x",
    "https://evil.example/o/r/tarball/x",
    "https://codeload.github.com.evil.example/o/r/tarball/x",
    "https://github.example.attacker.com/o/r/tarball/x",
    "https://objects.githubusercontent.com/o/r/tarball/x",
])
def test_redirect_host_validation_matrix(location):
    """Exact normalized hostname comparison; no endswith matching.

    objects.githubusercontent.com is not on the allowlist (unchanged,
    pre-existing behavior; the allowlist was not broadened).
    """
    client = make_client(lambda request: httpx.Response(200))
    with pytest.raises(GitHubError) as exc_info:
        client._validate_archive_redirect(location)
    assert exc_info.value.code == "snapshot_download_failed"
    client.close()


@pytest.mark.parametrize("location,expected", [
    ("https://codeload.github.com/o/r/tarball/x",
     "https://codeload.github.com/o/r/tarball/x"),
    # Explicit :443 is normalized away by httpx and accepted.
    ("https://codeload.github.com:443/o/r/tarball/x",
     "https://codeload.github.com/o/r/tarball/x"),
    ("https://CODELOAD.GITHUB.COM/o/r/tarball/x",
     "https://codeload.github.com/o/r/tarball/x"),
    ("https://api.github.com/repos/o/r/tarball/x",
     "https://api.github.com/repos/o/r/tarball/x"),
])
def test_redirect_valid_targets_accepted(location, expected):
    client = make_client(lambda request: httpx.Response(200))
    assert client._validate_archive_redirect(location) == expected
    client.close()


def test_userinfo_would_synthesize_basic_at_transport():
    """Threat demonstration: proves *why* validation must reject userinfo.

    If a userinfo URL ever reached httpx's send path, the transport would
    see an Authorization: Basic header synthesized from the URL — the
    pre-send ``assert "authorization" not in req.headers`` cannot catch
    it. Validation is therefore the control, and it rejects such URLs.
    """
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"ok")

    client = make_client(handler)
    req = httpx.Request("GET", "https://user:pass@codeload.github.com/x",
                        headers={"Accept": "application/octet-stream"})
    assert "authorization" not in req.headers  # pre-send: looks clean
    client._http.send(req, follow_redirects=False)
    assert seen["authorization"] == "Basic dXNlcjpwYXNz"  # transport: leaked
    client.close()


# ------------------------------------------------------------------
# Final-send Authorization proof (301/302/303/307/308)
# ------------------------------------------------------------------

@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_archive_final_send_has_no_auth_header(status):
    """The archive request *as received by the transport* carries no
    credential-bearing authorization header for any redirect status.

    The API request itself is authenticated (Bearer present); only the
    archive download must be clean.
    """
    seen = {}

    def handler(request):
        if request.url.host == "api.github.com":
            seen["api_auth"] = request.headers.get("authorization")
            return httpx.Response(
                status,
                headers={"location": "https://codeload.github.com/o/r/t/x"},
            )
        # This is the final archive request as the transport sees it,
        # after all of httpx's URL/auth processing.
        seen["archive_auth"] = request.headers.get("authorization")
        seen["archive_proxy_auth"] = request.headers.get("proxy-authorization")
        seen["archive_headers"] = dict(request.headers)
        return httpx.Response(200, content=b"archive-bytes")

    client = make_client(handler)
    data = client.download_repository_snapshot(
        "o", "r", BASE_SHA, max_archive_bytes=1024 * 1024)
    assert data == b"archive-bytes"
    assert seen["api_auth"] == f"Bearer {FAKE_TOKEN}"
    assert seen["archive_auth"] is None, "Authorization leaked to archive!"
    assert seen["archive_proxy_auth"] is None
    # The token must not appear anywhere in the archive request headers.
    assert FAKE_TOKEN not in str(seen["archive_headers"])
    client.close()


def test_userinfo_redirect_never_sent():
    """A userinfo redirect is rejected before any archive request is made."""
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"location":
                         "https://user:pass@codeload.github.com/o/r/t/x"},
            )
        raise AssertionError("archive request must never be sent")

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.download_repository_snapshot(
            "o", "r", BASE_SHA, max_archive_bytes=1024 * 1024)
    assert exc_info.value.code == "snapshot_download_failed"
    assert calls == ["api.github.com"]
    client.close()


# ------------------------------------------------------------------
# L1: secondary rate limit classification
# ------------------------------------------------------------------

def _status_handler(status, headers):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, headers=headers, json={"x": 1})

    return handler, calls


def test_primary_rate_limit_403():
    handler, _ = _status_handler(
        403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"})
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 1)
    assert exc_info.value.code == "github_rate_limited"
    assert "Rate limit resets at" in exc_info.value.message  # reset preserved
    client.close()


def test_secondary_rate_limit_403_with_retry_after():
    """L1: 403 + Retry-After (+ secondary wording) is rate limiting."""
    handler, calls = _status_handler(403, {
        "Retry-After": "60",
    })
    client = make_client(handler)

    def json_403(request):
        calls.append(1)
        return httpx.Response(403, headers={"Retry-After": "60"},
                              json={"message": "You have exceeded a secondary "
                                               "rate limit and have been "
                                               "temporarily blocked."})

    client2 = make_client(json_403)
    with pytest.raises(GitHubError) as exc_info:
        client2.get_pull_request("o", "r", 1)
    assert exc_info.value.code == "github_rate_limited"
    assert len(calls) == 1, "retry storm on 403!"
    client.close()
    client2.close()


def test_secondary_rate_limit_retry_after_only():
    """Retry-After alone (no prose parsing) still classifies as limited."""
    def handler(request):
        return httpx.Response(403, headers={"Retry-After": "120"},
                              json={"message": "abuse detection"})
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 1)
    assert exc_info.value.code == "github_rate_limited"
    client.close()


def test_ordinary_403_stays_not_authorized():
    """A permission 403 without rate-limit signals is not rate limiting."""
    def handler(request):
        return httpx.Response(403, json={"message": "Forbidden"})
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 1)
    assert exc_info.value.code == "repository_not_found_or_not_authorized"
    client.close()


def test_429_is_rate_limited_no_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "30"}, json={})
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 1)
    assert exc_info.value.code == "github_rate_limited"
    assert len(calls) == 1
    client.close()


# ------------------------------------------------------------------
# L2: malformed upstream field types -> typed error
# ------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("additions", "many"),
    ("deletions", 1.5),
    ("changed_files", "abc"),
    ("changed_files", ""),
    ("changed_files", True),
    ("changed_files", [3]),
    ("additions", {"n": 1}),
])
def test_malformed_pr_metadata_counts_typed(field, value):
    """L2: no raw ValueError escapes PR metadata parsing."""
    def handler(request):
        return httpx.Response(200, json=pr_json(**{field: value}))
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "malformed_github_response"
    assert "ValueError" not in type(exc_info.value).__name__
    client.close()


@pytest.mark.parametrize("number", ["forty-two", 1.5, "", 0, -7])
def test_malformed_pr_number_typed(number):
    def handler(request):
        return httpx.Response(200, json=pr_json(number=number))
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "malformed_github_response"
    client.close()


@pytest.mark.parametrize("field,value", [
    ("additions", "many"),
    ("deletions", 2.5),
    ("changes", ""),
    ("changes", -1),
])
def test_malformed_file_counts_typed(field, value):
    """L2: file-level count violations are typed, not ValueError."""
    with pytest.raises(GitHubError) as exc_info:
        translate_github_files(
            [file_json("sample_mainframe/copybook/WARRCOPY.cpy",
                       **{field: value})],
            "sample_mainframe",
        )
    assert exc_info.value.code == "malformed_github_response"


def test_malformed_metadata_via_api_is_502_no_traceback(monkeypatch):
    """L2 through the API: typed 502, no stack trace, no token."""
    import backend.api.github as github_api
    from backend.github import errors as E

    def fake_analyze(request, **kwargs):
        raise E.malformed_github_response("PR #1 metadata: bad 'additions'")

    monkeypatch.setattr(github_api, "analyze_github_pull_request",
                        fake_analyze)
    from backend.api.app import app
    client = TestClient(app)
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 1})
    assert resp.status_code == 502
    body = resp.json()["detail"]
    assert body["code"] == "malformed_github_response"
    assert "Traceback" not in resp.text
    assert FAKE_TOKEN not in resp.text


# ------------------------------------------------------------------
# L3: unknown API request fields are rejected
# ------------------------------------------------------------------

@pytest.mark.parametrize("extra", [
    {"token": "secret"},
    {"api_base_url": "https://evil.example"},
    {"github_url": "https://evil.example"},
    {"authorization": "Bearer x"},
])
def test_request_model_forbids_extra_fields(extra):
    """L3: smuggled credential-ish fields fail validation loudly."""
    payload = {"owner": "x", "repo": "y", "pull_number": 1}
    payload.update(extra)
    with pytest.raises(Exception) as exc_info:
        PullRequestRequest(**payload)
    assert "extra_forbidden" in str(exc_info.value)


def test_api_rejects_extra_token_field(monkeypatch):
    """L3 through the API: 422 and the service layer is never reached.

    (The 422 body echoes the caller's own submitted input, as with every
    FastAPI validation error; the point is the field is rejected and the
    value is never used as a credential.)
    """
    import backend.api.github as github_api

    def fake_analyze(request, **kwargs):  # pragma: no cover - not reached
        raise AssertionError("must not reach the service layer")

    monkeypatch.setattr(github_api, "analyze_github_pull_request",
                        fake_analyze)
    from backend.api.app import app
    client = TestClient(app)
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 1,
        "token": "smuggled_secret_value",
    })
    assert resp.status_code == 422
    assert "extra_forbidden" in resp.text


# ------------------------------------------------------------------
# L4: source_root length bound
# ------------------------------------------------------------------

def test_source_root_length_bound():
    """L4: absurdly long source_root values are rejected."""
    with pytest.raises(GitHubError) as exc_info:
        validate_source_root("a" * (SOURCE_ROOT_MAX_LENGTH + 1))
    assert exc_info.value.code == "invalid_source_root"


def test_source_root_length_bound_is_documented_value():
    assert SOURCE_ROOT_MAX_LENGTH == 1024


def test_source_root_normal_lengths_still_work():
    assert validate_source_root(".") == "."
    assert validate_source_root("sample_mainframe") == "sample_mainframe"
    assert validate_source_root("a" * SOURCE_ROOT_MAX_LENGTH) == \
        "a" * SOURCE_ROOT_MAX_LENGTH


def test_source_root_too_long_via_api_422(monkeypatch):
    import backend.api.github as github_api

    def fake_analyze(request, **kwargs):  # pragma: no cover - not reached
        raise AssertionError("must not reach the service layer")

    monkeypatch.setattr(github_api, "analyze_github_pull_request",
                        fake_analyze)
    from backend.api.app import app
    client = TestClient(app)
    resp = client.post("/api/github/pull-request/analyze", json={
        "owner": "o", "repo": "r", "pull_number": 1,
        "source_root": "a" * 2000,
    })
    assert resp.status_code == 422


# ------------------------------------------------------------------
# L6: negative changed_files
# ------------------------------------------------------------------

def test_negative_changed_files_rejected():
    """L6: changed_files < 0 is malformed metadata, not zero files."""
    def handler(request):
        return httpx.Response(200, json=pr_json(changed_files=-1))
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "malformed_github_response"
    client.close()


@pytest.mark.parametrize("count", [0, 1])
def test_zero_and_one_changed_files_accepted(count):
    def handler(request):
        return httpx.Response(200, json=pr_json(changed_files=count))
    client = make_client(handler)
    meta, _ = client.get_pull_request("o", "r", 42)
    assert meta.changed_files == count
    client.close()
