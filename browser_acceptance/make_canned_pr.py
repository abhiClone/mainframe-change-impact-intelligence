"""Generate a canned GitHub PR analysis JSON for the browser acceptance pass.

Runs the real deterministic backend (`analyze_github_pull_request`) with a
mocked GitHub transport — no live network — and writes the serialized
`GitHubPullRequestAnalysis` to /tmp/canned_pr.json. The browser intercepts
POST /api/github/pull-request/analyze and fulfills it with this file.

Scenario coverage baked into the canned payload:
  - long repository name (80-char repo)
  - long PR title (200 chars)
  - long file path within scope
  - renamed file within scope
  - outside-source-root file
  - base/head SHAs, base/head repositories
  - rate-limit metadata
"""
import io
import json
import sys
import tarfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.github import (
    GitHubClient,
    PullRequestRequest,
    analyze_github_pull_request,
)

REPO = Path(__file__).resolve().parents[1] / "sample_mainframe"
OUT = Path("/tmp/canned_pr.json")

OWNER = "o"
LONG_REPO = "r" * 80
FULL_NAME = f"{OWNER}/{LONG_REPO}"
BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
LONG_TITLE = "Warranty copybook overhaul across reporting programs " + "x" * 147
LONG_PATH = "sample_mainframe/" + "d" * 40 + "/" + "f" * 60 + ".cpy"


def build_tree_tarball(top: str) -> bytes:
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


BASE_TARBALL = build_tree_tarball(f"{OWNER}-{LONG_REPO}-{BASE_SHA}")
HEAD_TARBALL = build_tree_tarball(f"{OWNER}-{LONG_REPO}-{HEAD_SHA}")


def pr_payload():
    return {
        "number": 42,
        "title": LONG_TITLE,
        "state": "open",
        "draft": False,
        "html_url": f"https://github.com/{FULL_NAME}/pull/42",
        "user": {"login": "dev1"},
        "base": {"ref": "main", "sha": BASE_SHA,
                 "repo": {"full_name": FULL_NAME}},
        "head": {"ref": "feature/warranty", "sha": HEAD_SHA,
                 "repo": {"full_name": FULL_NAME}},
        "changed_files": 3,
        "additions": 30,
        "deletions": 8,
        "created_at": "2026-09-30T10:00:00Z",
        "updated_at": "2026-10-01T08:00:00Z",
    }


def files_payload():
    return [
        {"filename": "sample_mainframe/copybook/WARRCPY2.cpy",
         "previous_filename": "sample_mainframe/copybook/WARRCOPY.cpy",
         "status": "renamed", "additions": 5, "deletions": 1,
         "changes": 6, "sha": "1" * 40},
        {"filename": LONG_PATH, "previous_filename": None,
         "status": "modified", "additions": 20, "deletions": 5,
         "changes": 25, "sha": "2" * 40},
        {"filename": "docs/release-notes/CHANGELOG.md",
         "previous_filename": None, "status": "modified",
         "additions": 5, "deletions": 2, "changes": 7, "sha": "3" * 40},
    ]


def handler(request):
    host, path = request.url.host, request.url.path
    if host == "api.github.com":
        base = f"/repos/{OWNER}/{LONG_REPO}"
        if path == f"{base}/pulls/42":
            return httpx.Response(200, json=pr_payload(),
                                  headers={"x-ratelimit-limit": "5000",
                                           "x-ratelimit-remaining": "4999",
                                           "x-ratelimit-reset": "1789000000"})
        if path == f"{base}/pulls/42/files":
            return httpx.Response(200, json=files_payload(),
                                  headers={"x-ratelimit-limit": "5000",
                                           "x-ratelimit-remaining": "4998",
                                           "x-ratelimit-reset": "1789000000"})
        if path == f"{base}/tarball/{BASE_SHA}":
            loc = f"https://codeload.github.com/{FULL_NAME}/tarball/{BASE_SHA}/x"
            return httpx.Response(302, headers={"location": loc})
        if path == f"{base}/tarball/{HEAD_SHA}":
            loc = f"https://codeload.github.com/{FULL_NAME}/tarball/{HEAD_SHA}/y"
            return httpx.Response(302, headers={"location": loc})
    if host == "codeload.github.com":
        assert "authorization" not in request.headers
        if BASE_SHA in path:
            return httpx.Response(200, content=BASE_TARBALL)
        return httpx.Response(200, content=HEAD_TARBALL)
    raise AssertionError(f"unexpected request {request.url}")


def main():
    client = GitHubClient(token="browser-acceptance-fake",
                          transport=httpx.MockTransport(handler),
                          max_retries=0)
    try:
        result = analyze_github_pull_request(
            PullRequestRequest(owner=OWNER, repo=LONG_REPO, pull_number=42,
                               source_root="sample_mainframe"),
            client=client,
        )
    finally:
        client.close()
    data = result.model_dump(mode="json")
    OUT.write_text(json.dumps(data, indent=1))
    print("wrote", OUT, len(OUT.read_text()), "bytes")
    print("title len:", len(data["pull_request"]["title"]))
    print("repo:", data["repository"])
    print("files:", len(data["github_files"]))
    print("rate_limit:", data["rate_limit"])
    print("base_sha:", data["base_snapshot"]["sha"])
    print("head_sha:", data["head_snapshot"]["sha"])


if __name__ == "__main__":
    main()
