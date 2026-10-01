"""Phase 3B: GitHub REST client tests (fully mocked, no live GitHub).

Covers headers/versioning, auth behavior, PR metadata parsing (same-repo
and fork), file pagination, the 3000-file fail-closed limit, error
mapping, bounded retries, rate limits, archive redirect/token safety, and
token-leak checks.
"""
import httpx
import pytest

from backend.github import GitHubClient, GitHubError
from backend.github.models import GITHUB_API_VERSION

FAKE_TOKEN = "ghp_SUPER_SECRET_TEST_VALUE"

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40

RATE_HEADERS = {
    "x-ratelimit-limit": "5000",
    "x-ratelimit-remaining": "4999",
    "x-ratelimit-reset": "1790000000",
    "x-ratelimit-resource": "core",
}


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
        "deletions": 3,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    data.update(over)
    return data


def file_json(name, status="modified", prev=None, n=0):
    return {
        "filename": name,
        "previous_filename": prev,
        "status": status,
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "sha": f"{n:040d}",
    }


def make_client(handler, token=FAKE_TOKEN, **kwargs):
    kwargs.setdefault("max_retries", 0)
    return GitHubClient(
        token=token, transport=httpx.MockTransport(handler), **kwargs
    )


def json_response(data, status=200, headers=None):
    h = dict(RATE_HEADERS)
    h.update(headers or {})
    return httpx.Response(status, json=data, headers=h)


# ------------------------------------------------------------------
# Headers / versioning / auth
# ------------------------------------------------------------------

def test_version_headers_sent():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return json_response(pr_json())

    client = make_client(handler)
    client.get_pull_request("o", "r", 42)
    assert seen["accept"] == "application/vnd.github+json"
    assert seen["x-github-api-version"] == GITHUB_API_VERSION == "2026-03-10"
    assert seen["user-agent"] == "mainframe-change-impact-intelligence"
    assert seen["authorization"] == f"Bearer {FAKE_TOKEN}"


def test_no_auth_header_without_token():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return json_response(pr_json())

    client = make_client(handler, token=None)
    assert not client.auth_configured
    client.get_pull_request("o", "r", 42)
    assert "authorization" not in seen


def test_auth_configured_flag():
    assert make_client(lambda r: json_response({})).auth_configured
    assert not make_client(lambda r: json_response({}), token=None).auth_configured


# ------------------------------------------------------------------
# PR metadata parsing
# ------------------------------------------------------------------

def test_pr_metadata_parsing():
    client = make_client(lambda r: json_response(pr_json()))
    meta, _ = client.get_pull_request("o", "r", 42)
    assert meta.number == 42
    assert meta.title == "Update warranty copybook"
    assert meta.state == "open"
    assert meta.draft is False
    assert meta.html_url == "https://github.com/o/r/pull/42"
    assert meta.author_login == "dev1"
    assert meta.base_ref == "main" and meta.base_sha == BASE_SHA
    assert meta.base_repo_full_name == "o/r"
    assert meta.head_ref == "feature" and meta.head_sha == HEAD_SHA
    assert meta.head_repo_full_name == "o/r"
    assert meta.changed_files == 2


def test_fork_pr_metadata():
    payload = pr_json()
    payload["head"]["repo"]["full_name"] = "contributor/r"

    client = make_client(lambda r: json_response(payload))
    meta, _ = client.get_pull_request("o", "r", 42)
    assert meta.base_repo_full_name == "o/r"
    assert meta.head_repo_full_name == "contributor/r"


def test_null_head_repo():
    payload = pr_json()
    payload["head"]["repo"] = None

    client = make_client(lambda r: json_response(payload))
    meta, _ = client.get_pull_request("o", "r", 42)
    assert meta.head_repo_full_name is None
    assert meta.head_sha == HEAD_SHA  # SHA still preserved


# ------------------------------------------------------------------
# File pagination
# ------------------------------------------------------------------

def _files_handler(total, per_page=100):
    seen = {"calls": 0}

    def handler(request):
        seen["calls"] += 1
        page = int(request.url.params.get("page", "1"))
        start = (page - 1) * per_page
        end = min(start + per_page, total)
        items = [file_json(f"f{i}.cbl", n=i) for i in range(start, end)]
        headers = {}
        if end < total:
            nxt = (f"https://api.github.com/repos/o/r/pulls/42/files"
                   f"?per_page={per_page}&page={page + 1}")
            last = (f"https://api.github.com/repos/o/r/pulls/42/files"
                    f"?per_page={per_page}&page={(total + per_page - 1) // per_page}")
            headers["link"] = f'<{nxt}>; rel="next", <{last}>; rel="last"'
        return json_response(items, headers=headers)

    return handler, seen


def test_file_pagination_single_file():
    handler, seen = _files_handler(1)
    client = make_client(handler)
    files, _ = client.list_pull_request_files("o", "r", 42, expected_total=1)
    assert len(files) == 1 and seen["calls"] == 1
    assert files[0]["filename"] == "f0.cbl"


def test_file_pagination_exactly_100():
    handler, seen = _files_handler(100)
    client = make_client(handler)
    files, _ = client.list_pull_request_files("o", "r", 42, expected_total=100)
    assert len(files) == 100 and seen["calls"] == 1


def test_file_pagination_multi_page():
    handler, seen = _files_handler(250)
    client = make_client(handler)
    # First page must request per_page=100.
    files, _ = client.list_pull_request_files("o", "r", 42, expected_total=250)
    assert len(files) == 250 and seen["calls"] == 3
    assert files[0]["filename"] == "f0.cbl"
    assert files[249]["filename"] == "f249.cbl"


def test_over_3000_files_fails_closed_without_fetch():
    def handler(request):
        raise AssertionError("files endpoint must not be called")

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.list_pull_request_files("o", "r", 42, expected_total=3001)
    assert exc_info.value.code == "incomplete_change_set"
    assert "3000" in exc_info.value.message


def test_pagination_incompleteness_fails_closed():
    # Advertised 5, only 3 delivered, no next link.
    handler, _ = _files_handler(3)
    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.list_pull_request_files("o", "r", 42, expected_total=5)
    assert exc_info.value.code == "incomplete_change_set"


# ------------------------------------------------------------------
# Error mapping
# ------------------------------------------------------------------

def test_401_maps_to_authentication_failed():
    client = make_client(lambda r: httpx.Response(401, json={"message": "x"}))
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "github_authentication_failed"


def test_403_rate_limited():
    headers = dict(RATE_HEADERS, **{"x-ratelimit-remaining": "0"})

    def handler(request):
        return httpx.Response(403, json={"message": "rate limited"},
                              headers=headers)

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "github_rate_limited"


def test_429_maps_to_rate_limited():
    client = make_client(lambda r: httpx.Response(429, headers=RATE_HEADERS))
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "github_rate_limited"


def test_403_forbidden_maps_to_not_authorized():
    client = make_client(lambda r: httpx.Response(403, headers=RATE_HEADERS))
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "repository_not_found_or_not_authorized"


def test_404_pr_maps_to_pull_request_not_found():
    client = make_client(lambda r: httpx.Response(404, json={"message": "x"}))
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 999)
    assert exc_info.value.code == "pull_request_not_found"


def test_404_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={})

    client = make_client(handler, max_retries=2)
    with pytest.raises(GitHubError):
        client.get_pull_request("o", "r", 42)
    assert calls["n"] == 1


def test_500_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={})
        return json_response(pr_json())

    client = make_client(handler, max_retries=2)
    meta, _ = client.get_pull_request("o", "r", 42)
    assert meta.number == 42 and calls["n"] == 3


def test_500_exhausts_retries():
    client = make_client(lambda r: httpx.Response(503, json={}),
                         max_retries=0)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "github_unavailable"


def test_timeout_maps_to_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = make_client(handler, max_retries=0)
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert exc_info.value.code == "github_unavailable"


def test_rate_limit_headers_captured():
    client = make_client(lambda r: json_response(pr_json()))
    _, rate = client.get_pull_request("o", "r", 42)
    assert rate is not None
    assert rate.limit == 5000 and rate.remaining == 4999
    assert rate.resource == "core"


def test_token_never_in_error_messages():
    def handler(request):
        return httpx.Response(401, json={"message": "bad credentials"})

    client = make_client(handler)  # FAKE_TOKEN configured
    with pytest.raises(GitHubError) as exc_info:
        client.get_pull_request("o", "r", 42)
    assert FAKE_TOKEN not in str(exc_info.value)
    assert FAKE_TOKEN not in repr(exc_info.value)


# ------------------------------------------------------------------
# Snapshot download / redirect safety
# ------------------------------------------------------------------

ARCHIVE_BYTES = b"fake-archive-bytes"


def _tarball_handler(request, *, redirect_host="codeload.github.com",
                     archive=ARCHIVE_BYTES, status=302):
    if request.url.host == "api.github.com":
        assert request.headers.get("authorization") == f"Bearer {FAKE_TOKEN}"
        assert request.url.path == f"/repos/o/r/tarball/{BASE_SHA}"
        location = f"https://{redirect_host}/o/r/tarball/{BASE_SHA}/x"
        return httpx.Response(status, headers={"location": location})
    # Archive host request.
    assert "authorization" not in request.headers, (
        "token forwarded to archive host!"
    )
    assert request.url.host == redirect_host
    return httpx.Response(200, content=archive)


def test_snapshot_redirect_does_not_forward_token():
    client = make_client(_tarball_handler)
    data = client.download_repository_snapshot(
        "o", "r", BASE_SHA, max_archive_bytes=1024 * 1024)
    assert data == ARCHIVE_BYTES


def test_snapshot_redirect_to_evil_host_rejected():
    def handler(request):
        return _tarball_handler(request, redirect_host="evil.example")

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.download_repository_snapshot(
            "o", "r", BASE_SHA, max_archive_bytes=1024 * 1024)
    assert exc_info.value.code == "snapshot_download_failed"


def test_snapshot_404_maps_to_not_authorized():
    def handler(request):
        return httpx.Response(404, json={})

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.download_repository_snapshot(
            "o", "r", BASE_SHA, max_archive_bytes=1024 * 1024)
    assert exc_info.value.code == "repository_not_found_or_not_authorized"


def test_malformed_sha_rejected_before_request():
    def handler(request):
        raise AssertionError("no request should be made")

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.download_repository_snapshot(
            "o", "r", "../../etc", max_archive_bytes=1024)
    assert exc_info.value.code == "snapshot_download_failed"


def test_archive_size_limit_enforced():
    def handler(request):
        return _tarball_handler(
            request, archive=b"x" * 2048)

    client = make_client(handler)
    with pytest.raises(GitHubError) as exc_info:
        client.download_repository_snapshot(
            "o", "r", BASE_SHA, max_archive_bytes=1024)
    assert exc_info.value.code == "snapshot_too_large"
