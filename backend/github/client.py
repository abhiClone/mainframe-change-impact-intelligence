"""Phase 3B GitHub REST client (read-only).

Thin HTTP layer over the GitHub REST API. It knows nothing about
Mainframe components, impact, tests, risks, or incidents — it only
fetches deterministic PR metadata/files and repository snapshots.

API version: ``X-GitHub-Api-Version: 2026-03-10`` (verified against the
official GitHub docs at implementation time; never rely on unversioned
defaults).

Security properties (all covered by tests):

- The token comes only from the ``GITHUB_TOKEN`` environment variable
  (constructor argument in tests); it is never accepted from request
  bodies, query parameters, URLs, or CLI arguments.
- The token is never written to logs, tracebacks, exceptions, or
  responses — error messages carry status codes only.
- Archive downloads follow GitHub's redirect manually: the redirect
  target must be HTTPS on an approved GitHub-controlled host (exact
  hostname match, default HTTPS port only, no URL userinfo of any
  kind, trailing-dot hosts rejected), and the ``Authorization`` header
  is never forwarded to it — verified against the final request as
  received by the transport.
- Upstream schema violations (non-integer or negative counts,
  non-integer PR numbers) become the typed ``malformed_github_response``
  error, never a raw ``ValueError``.
- Secondary GitHub rate limits (403 with ``Retry-After``) are classified
  as ``github_rate_limited``; ordinary authorization 403s are not.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

from . import errors as E
from .models import (
    GITHUB_ACCEPT,
    GITHUB_API_BASE,
    GITHUB_API_VERSION,
    GITHUB_ARCHIVE_HOST,
    GITHUB_PR_FILES_HARD_LIMIT,
    GITHUB_USER_AGENT,
    GitHubRateLimit,
    PullRequestMetadata,
    parse_commit_sha,
    parse_github_count,
    parse_git_ref,
    parse_repo_full_name,
    parse_strict_count,
)

_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")
_TRUSTED_REDIRECT_HOSTS = {"api.github.com", GITHUB_ARCHIVE_HOST}

_RETRYABLE_STATUSES = {500, 502, 503, 504}
_NO_RETRY_STATUSES = {401, 403, 404, 422, 429}


class GitHubClient:
    """Read-only GitHub REST client.

    ``token`` is the server-side ``GITHUB_TOKEN`` (or ``None`` for public
    repositories). ``transport`` accepts an ``httpx.MockTransport`` for
    deterministic tests — no test may touch the live GitHub API.
    """

    def __init__(
        self,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._token = token
        self._max_retries = max(0, max_retries)
        headers = {
            "Accept": GITHUB_ACCEPT,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": GITHUB_USER_AGENT,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # API calls may follow same-origin redirects (httpx strips
        # Authorization cross-origin); the archive download below handles
        # its redirect manually so the token is provably never forwarded.
        # trust_env=False: the client never inherits proxy configuration
        # from the environment (explicit headers/proxy only). This keeps
        # behavior deterministic in tests and avoids leaking ambient proxy
        # credentials into GitHub-bound requests.
        self._http = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers=headers,
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
        )
        self._rate_limit: GitHubRateLimit | None = None

    # -- public ------------------------------------------------------
    @property
    def auth_configured(self) -> bool:
        """Whether a server-side token is configured (no token details)."""
        return self._token is not None

    @property
    def rate_limit(self) -> GitHubRateLimit | None:
        return self._rate_limit

    @staticmethod
    def token_from_env() -> str | None:
        """The only supported token source: the GITHUB_TOKEN env var."""
        return os.environ.get("GITHUB_TOKEN") or None

    def get_pull_request(
        self, owner: str, repo: str, pull_number: int
    ) -> tuple[PullRequestMetadata, GitHubRateLimit | None]:
        """Fetch ``GET /repos/{owner}/{repo}/pulls/{pull_number}``.

        The GitHub response is externally supplied data: every field
        that controls snapshot identity or repository selection
        (``base``/``head`` SHAs, refs, and repository full names, plus
        ``changed_files``) is strictly typed-validated here. Upstream
        schema violations become the typed ``malformed_github_response``
        error — never a raw ``KeyError``/``ValueError``, never a silent
        fallback to a branch ref, merge SHA, or current HEAD.
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}"
        data = self._get_json(path, not_found=E.pull_request_not_found(
            f"{owner}/{repo}", pull_number
        ))
        what = f"PR #{pull_number} metadata"
        number = parse_github_count(
            data.get("number", pull_number), field="number", what=what
        )
        if number <= 0:
            raise E.malformed_github_response(
                f"{what}: field 'number' must be > 0, got {number}"
            )
        base = data.get("base")
        if not isinstance(base, dict):
            raise E.malformed_github_response(
                f"{what}: field 'base' is missing or not an object"
            )
        head = data.get("head")
        if not isinstance(head, dict):
            raise E.malformed_github_response(
                f"{what}: field 'head' is missing or not an object"
            )
        base_repo = base.get("repo")
        if not isinstance(base_repo, dict):
            raise E.malformed_github_response(
                f"{what}: field 'base.repo' is missing or not an object"
            )
        base_repo_full_name = parse_repo_full_name(
            base_repo.get("full_name"),
            field="base.repo.full_name",
            what=what,
        )
        # head.repo == null is the legitimate GitHub case for a
        # deleted/inaccessible fork: it is preserved as None and the
        # service applies its deterministic base-repo fallback.
        head_repo = head.get("repo")
        if head_repo is None:
            head_repo_full_name: str | None = None
        elif not isinstance(head_repo, dict):
            raise E.malformed_github_response(
                f"{what}: field 'head.repo' is not an object"
            )
        else:
            head_repo_full_name = parse_repo_full_name(
                head_repo.get("full_name"),
                field="head.repo.full_name",
                what=what,
            )
        if "changed_files" not in data:
            raise E.malformed_github_response(
                f"{what}: field 'changed_files' is missing"
            )
        meta = PullRequestMetadata(
            number=number,
            title=data.get("title") or "",
            state=data.get("state") or "",
            draft=bool(data.get("draft")),
            html_url=data.get("html_url") or "",
            author_login=((data.get("user") or {}).get("login")) or "",
            base_ref=parse_git_ref(
                base.get("ref"), field="base.ref", what=what
            ),
            base_sha=parse_commit_sha(
                base.get("sha"), field="base.sha", what=what
            ),
            base_repo_full_name=base_repo_full_name,
            head_ref=parse_git_ref(
                head.get("ref"), field="head.ref", what=what
            ),
            head_sha=parse_commit_sha(
                head.get("sha"), field="head.sha", what=what
            ),
            head_repo_full_name=head_repo_full_name,
            changed_files=parse_strict_count(
                data.get("changed_files"),
                field="changed_files",
                what=what,
            ),
            additions=parse_github_count(
                data.get("additions"), field="additions", what=what
            ),
            deletions=parse_github_count(
                data.get("deletions"), field="deletions", what=what
            ),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )
        return meta, self._rate_limit

    def list_pull_request_files(
        self, owner: str, repo: str, pull_number: int, expected_total: int
    ) -> tuple[list[dict[str, Any]], GitHubRateLimit | None]:
        """Fetch all PR files via ``GET .../pulls/{n}/files`` (per_page=100).

        Fails closed when GitHub's 3000-file API limit is exceeded or when
        pagination ends before the advertised file count.
        """
        if expected_total > GITHUB_PR_FILES_HARD_LIMIT:
            raise E.incomplete_change_set(
                "GitHub file-list API limit exceeded: the pull request "
                f"reports {expected_total} changed files, but the GitHub "
                f"REST API returns at most {GITHUB_PR_FILES_HARD_LIMIT}. "
                "Refusing to analyze a partial change set."
            )
        files: list[dict[str, Any]] = []
        url: str | None = (
            f"/repos/{owner}/{repo}/pulls/{pull_number}/files?per_page=100"
        )
        not_found = E.pull_request_not_found(f"{owner}/{repo}", pull_number)
        while url is not None:
            resp = self._request("GET", url, not_found=not_found)
            page = resp.json()
            if not isinstance(page, list):
                raise E.github_unavailable(
                    f"unexpected file-list response for PR #{pull_number}"
                )
            files.extend(page)
            if len(files) > GITHUB_PR_FILES_HARD_LIMIT:
                raise E.incomplete_change_set(
                    "GitHub file-list API limit exceeded while paginating "
                    f"({len(files)} files seen); refusing a partial change set."
                )
            url = self._next_link(resp.headers.get("link"))
        if len(files) < expected_total:
            raise E.incomplete_change_set(
                f"Pagination ended after {len(files)} files but the pull "
                f"request reports {expected_total} changed files; refusing "
                "to analyze a possibly incomplete change set."
            )
        return files, self._rate_limit

    def download_repository_snapshot(
        self, owner: str, repo: str, sha: str, max_archive_bytes: int
    ) -> bytes:
        """Download the repository archive at an exact SHA.

        Flow: authenticated request to the trusted GitHub API -> 302 ->
        validate HTTPS + approved GitHub-controlled host -> fetch WITHOUT
        the Authorization header -> stream with a size limit.
        """
        if not _SHA_RE.match(sha or ""):
            raise E.snapshot_download_failed(
                "refusing to request an archive for a malformed SHA"
            )
        path = f"/repos/{owner}/{repo}/tarball/{sha}"

        def _attempt() -> bytes:
            resp = self._request_raw(
                "GET",
                path,
                not_found=E.repository_not_found_or_not_authorized(
                    f"{owner}/{repo}"
                ),
                # Handle the 302 manually below: the redirect target must
                # be validated and the token must not be forwarded.
                follow_redirects=False,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                archive_url = self._validate_archive_redirect(location)
                return self._fetch_archive_no_auth(archive_url, max_archive_bytes)
            if resp.status_code == 200:
                return self._read_limited(resp, max_archive_bytes)
            raise E.snapshot_download_failed(
                f"unexpected archive response status {resp.status_code}"
            )

        return self._with_retries(
            _attempt, f"snapshot download for {owner}/{repo}@{sha[:7]}"
        )

    def close(self) -> None:
        self._http.close()

    # -- internals ---------------------------------------------------
    def _record_rate_limit(self, headers: httpx.Headers) -> None:
        def _int(name: str) -> int | None:
            try:
                return int(headers[name])
            except (KeyError, TypeError, ValueError):
                return None

        if any(n in headers for n in (
            "x-ratelimit-limit", "x-ratelimit-remaining",
            "x-ratelimit-reset", "x-ratelimit-resource",
        )):
            self._rate_limit = GitHubRateLimit(
                limit=_int("x-ratelimit-limit"),
                remaining=_int("x-ratelimit-remaining"),
                reset=_int("x-ratelimit-reset"),
                resource=headers.get("x-ratelimit-resource"),
            )

    def _raise_for_status(
        self, resp: httpx.Response, *, not_found: E.GitHubError, what: str
    ) -> None:
        status = resp.status_code
        if status == 401:
            raise E.github_authentication_failed()
        if status == 404:
            raise not_found
        if status == 422:
            raise E.GitHubError(
                "github_unavailable",
                f"GitHub API returned status 422 for {what}.",
            )
        if status == 429:
            raise E.github_rate_limited(self._reset_time(resp.headers))
        if status == 403:
            # 403 is ambiguous on GitHub: it signals primary rate limits
            # (x-ratelimit-remaining: 0), secondary/abuse rate limits
            # (documented signal: a Retry-After header), and insufficient
            # token permissions. Only the rate-limit cases classify as
            # github_rate_limited; permission 403s stay
            # repository_not_found_or_not_authorized. 403/429 are never
            # retried by _with_retries, so there is no retry storm.
            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining == "0" or "retry-after" in resp.headers:
                raise E.github_rate_limited(self._reset_time(resp.headers))
            raise E.repository_not_found_or_not_authorized(what)
        if status in _RETRYABLE_STATUSES:
            raise _Retryable(f"status {status} for {what}")
        raise E.github_unavailable(f"unexpected status {status} for {what}")

    @staticmethod
    def _reset_time(headers: httpx.Headers) -> str | None:
        try:
            reset = int(headers["x-ratelimit-reset"])
        except (KeyError, TypeError, ValueError):
            return None
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset))

    def _with_retries(self, fn, what: str):
        """Bounded retries for transient 5xx / network failures only.

        Never retries 401/403/404/422/429. Backoff is bounded exponential.
        """
        attempt = 0
        while True:
            try:
                return fn()
            except _Retryable as exc:
                if attempt >= self._max_retries:
                    raise E.github_unavailable(str(exc)) from exc
                time.sleep(0.5 * (2**attempt))
                attempt += 1
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt >= self._max_retries:
                    raise E.github_unavailable(
                        f"network failure for {what}"
                    ) from exc
                time.sleep(0.5 * (2**attempt))
                attempt += 1

    def _request_raw(
        self,
        method: str,
        url: str,
        *,
        not_found: E.GitHubError,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        def _attempt() -> httpx.Response:
            # The archive endpoint's 302 is handled manually (token must
            # never be forwarded), so redirect following is per-request.
            resp = self._http.request(
                method, url, follow_redirects=follow_redirects
            )
            self._record_rate_limit(resp.headers)
            if resp.status_code >= 400:
                self._raise_for_status(resp, not_found=not_found, what=url)
            return resp

        return self._with_retries(_attempt, url)

    def _request(
        self, method: str, url: str, *, not_found: E.GitHubError
    ) -> httpx.Response:
        return self._request_raw(method, url, not_found=not_found)

    def _get_json(
        self, path: str, *, not_found: E.GitHubError
    ) -> dict[str, Any]:
        resp = self._request("GET", path, not_found=not_found)
        data = resp.json()
        if not isinstance(data, dict):
            raise E.github_unavailable(f"unexpected JSON shape for {path}")
        return data

    @staticmethod
    def _next_link(link_header: str | None) -> str | None:
        """Extract the ``rel="next"`` URL from a GitHub Link header."""
        if not link_header:
            return None
        for part in link_header.split(","):
            segments = part.split(";")
            if len(segments) < 2:
                continue
            url = segments[0].strip().strip("<>")
            rel = "".join(segments[1:]).strip()
            if 'rel="next"' in rel:
                return url
        return None

    def _validate_archive_redirect(self, location: str) -> str:
        """Validate the archive redirect target.

        Must be HTTPS on an approved GitHub-controlled host. Never a
        user-supplied URL (the Location comes from GitHub's API response,
        but it is still validated, not trusted blindly).

        Host policy (fail-closed): the only accepted archive destination
        is the explicitly audited ``codeload.github.com`` (``api.github.com``
        is accepted for same-origin API redirects). GitHub does not
        document a fixed archive redirect host, so this is Phase 3B's own
        explicit allowlist — if GitHub changes archive delivery hosts in
        the future, analysis fails closed until the new host is reviewed
        and added. The allowlist is never broadened for theoretical
        compatibility.

        Rejected: any URL userinfo (username/password — httpx would
        otherwise synthesize an ``Authorization: Basic`` header from it
        at send time, defeating the no-auth archive guarantee), any
        non-default port, and trailing-dot hosts. The hostname is
        compared exactly after case normalization — no ``endswith``
        matching.
        """
        if not location:
            raise E.snapshot_download_failed(
                "archive endpoint redirected without a Location"
            )
        url = httpx.URL(location)
        if not url.is_absolute_url:
            # Resolve relative redirects against the trusted API base.
            url = httpx.URL(GITHUB_API_BASE).join(location)
        # Exact explicit host allowlist: the hostname is lowercased
        # (ordinary DNS case normalization) and compared exactly against
        # the approved set. Trailing-dot hosts are REJECTED — the policy
        # is an explicit allowlist, not DNS-equivalence normalization.
        # No endswith() matching, no suffix confusion.
        host = (url.host or "").lower()
        # Note: httpx returns "" (not None) for absent username/password.
        if (
            url.scheme != "https"
            or host not in _TRUSTED_REDIRECT_HOSTS
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise E.snapshot_download_failed(
                "archive redirect target is not an approved GitHub "
                "download host; refusing to follow it"
            )
        return str(url)

    def _fetch_archive_no_auth(self, url: str, max_bytes: int) -> bytes:
        """Fetch the archive WITHOUT the Authorization header."""
        safe_headers = {
            "Accept": "application/octet-stream",
            "User-Agent": GITHUB_USER_AGENT,
        }

        def _attempt() -> bytes:
            # A fresh request built from safe headers only: the token is
            # provably absent even if httpx ever changed redirect behavior.
            req = httpx.Request("GET", url, headers=safe_headers)
            assert "authorization" not in req.headers
            # No redirect following here either: the validated target is
            # fetched exactly as approved above.
            resp = self._http.send(req, stream=True, follow_redirects=False)
            self._record_rate_limit(resp.headers)
            if resp.status_code >= 400:
                self._raise_for_status(
                    resp,
                    not_found=E.repository_not_found_or_not_authorized(url),
                    what="archive download",
                )
            return self._read_limited(resp, max_bytes)

        return self._with_retries(_attempt, "archive download")

    @staticmethod
    def _read_limited(resp: httpx.Response, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_bytes(chunk_size=65536):
            total += len(chunk)
            if total > max_bytes:
                resp.close()
                raise E.snapshot_too_large(
                    f"archive exceeds the {max_bytes}-byte download limit"
                )
            chunks.append(chunk)
        resp.close()
        return b"".join(chunks)


class _Retryable(Exception):
    """Internal: a failure the bounded retry policy may retry."""
