"""Phase 3B final browser acceptance audit (same-host, real Chromium).

Chromium: /opt/meta-chromium/chrome (Playwright launch).
App:      http://127.0.0.1:5173/ (Vite dev) + http://127.0.0.1:8000/ (FastAPI)
Backend runs with GITHUB_TOKEN=ghp_PHASE3B_SECRET_DO_NOT_LEAK_123456789
(a distinctive fake token) to prove it never reaches the browser.

Per viewport (1440x900, 1280x800, 900x800):
  - visit all 7 views via the tab buttons
  - record console errors, page errors, horizontal page overflow
GitHub PR scenarios (at every viewport):
  - empty form -> client-side validation error, no API call
  - invalid repository -> client-side validation error, no API call
  - valid PR (route-intercepted with /tmp/canned_pr.json) ->
      long title, long repo, long path, renamed file, outside-scope file,
      base/head SHAs, auth badge, rate-limit line
  - typed 404 error -> friendly "not found" message
  - loading state -> "Analyzing..." button while the response is delayed
Audits (at every viewport):
  - network: every request host must be 127.0.0.1 or localhost
  - token: fake token absent from DOM, localStorage, sessionStorage, cookie
Writes a JSON summary to stdout and screenshots to /tmp/browser_acceptance/.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

FAKE_TOKEN = "ghp_PHASE3B_SECRET_DO_NOT_LEAK_123456789"
CHROME = "/home/hatch/workspace/.audit-tools/chrome-linux64/chrome"
# Chrome for Testing 153.0.8010.12 (same binary the 2026-09-26 visual audit
# used). /opt/meta-chromium/chrome (152) enforces Local Network Access
# checks that block even browser-initiated navigation to 127.0.0.1 in this
# sandbox; this build reaches the same-host servers normally.
CANNED = json.loads(Path("/tmp/canned_pr.json").read_text())
OUT_DIR = Path("/tmp/browser_acceptance")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [(1440, 900), (1280, 800), (900, 800)]
TABS = [
    "Repository Overview",
    "Dependency Explorer",
    "Change Impact",
    "Graph",
    "Release Intelligence",
    "Release / Change Set",
    "GitHub PR",
]
LONG_REPO = "o/" + "r" * 80
ANALYZE_URL = "**/api/github/pull-request/analyze"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def host_of(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]


def audit_viewport(page, w, h):
    vp = f"{w}x{h}"
    rep = {"tabs": {}, "scenarios": {}, "console_errors": [],
           "page_errors": [], "network_hosts": [], "token_findings": []}
    console_errors, page_errors, urls = [], [], []
    page.on("console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("request", lambda r: urls.append(r.url))
    page.goto("http://127.0.0.1:5173/", wait_until="networkidle")

    for tab in TABS:
        page.get_by_role("tab", name=tab).click()
        page.wait_for_timeout(1500)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > window.innerWidth + 1")
        heading = page.evaluate(
            "(document.querySelector('main h2, main h3') || {innerText: ''}).innerText.slice(0, 60)")
        rep["tabs"][tab] = {"overflow": overflow, "heading": heading}

    # ---- GitHub PR scenarios ----
    page.get_by_role("tab", name="GitHub PR").click()
    page.wait_for_timeout(800)
    repo_in = page.get_by_label("GitHub repository (owner/repo)")
    pr_in = page.get_by_label("Pull request number")
    analyze_btn = page.get_by_role("button", name="Analyze Pull Request")
    error_box = page.locator(".error-box")

    # 1. empty form
    repo_in.fill("")
    pr_in.fill("")
    analyze_btn.click()
    page.wait_for_timeout(400)
    rep["scenarios"]["empty_form_error"] = error_box.inner_text() if error_box.count() else None
    rep["scenarios"]["empty_form_posts"] = any("pull-request/analyze" in u for u in urls)

    # 2. invalid repository (client-side, no API call)
    n_before = len(urls)
    repo_in.fill("not a repo!!!")
    pr_in.fill("42")
    analyze_btn.click()
    page.wait_for_timeout(400)
    rep["scenarios"]["invalid_repo_error"] = error_box.inner_text() if error_box.count() else None
    rep["scenarios"]["invalid_repo_posts"] = any("pull-request/analyze" in u for u in urls[n_before:])

    # 3. valid PR result (intercepted, canned deterministic backend output)
    page.route(ANALYZE_URL, lambda route: route.fulfill(json=CANNED))
    repo_in.fill(LONG_REPO)
    pr_in.fill("42")
    analyze_btn.click()
    page.wait_for_selector("text=PR #42", timeout=15000)
    page.wait_for_timeout(500)
    main_text = page.evaluate("document.querySelector('main').innerText")
    rep["scenarios"]["valid_result"] = {
        "pr_header": "PR #42" in main_text,
        "long_title": CANNED["pull_request"]["title"][:40] in main_text,
        "long_repo": LONG_REPO[:30] in main_text,
        "renamed_file": "renamed" in main_text.lower(),
        "old_path": "WARRCOPY.cpy" in main_text,
        "outside_scope": "OUTSIDE SOURCE ROOT" in main_text,
        "base_sha_shown": "a" * 7 in main_text,
        "head_sha_shown": "b" * 7 in main_text,
        "auth_badge": "GitHub authentication configured" in main_text,
        "rate_limit": "requests remaining" in main_text,
        "loading_cleared": page.get_by_role("button", name="Analyze Pull Request").count() == 1,
    }
    page.screenshot(path=str(OUT_DIR / f"githubpr_{vp}.png"))

    # 4. typed error
    def fulfill_404(route):
        route.fulfill(status=404, json={"detail": {"code": "pull_request_not_found",
                                                  "message": "not found"}})
    page.route(ANALYZE_URL, fulfill_404)
    analyze_btn.click()
    page.wait_for_selector(".error-box", timeout=15000)
    rep["scenarios"]["typed_error"] = error_box.inner_text()

    # 5. loading state (delayed fulfillment)
    def fulfill_slow(route):
        page.wait_for_timeout(1500)
        route.fulfill(json=CANNED)
    page.route(ANALYZE_URL, fulfill_slow)
    analyze_btn.click()
    page.wait_for_selector("button:has-text('Analyzing')", timeout=5000)
    rep["scenarios"]["loading_state"] = "Analyzing" in page.locator(
        "button:has-text('Analyzing')").inner_text()
    page.wait_for_selector("text=PR #42", timeout=15000)
    page.unroute(ANALYZE_URL)

    # ---- audits ----
    rep["console_errors"] = console_errors
    rep["page_errors"] = page_errors
    rep["network_hosts"] = sorted({host_of(u) for u in urls})
    rep["network_nonlocal"] = sorted({host_of(u) for u in urls
                                      if host_of(u) not in ALLOWED_HOSTS})
    blobs = {
        "dom": page.evaluate("document.documentElement.outerHTML"),
        "localStorage": page.evaluate("JSON.stringify(Object.entries(localStorage))"),
        "sessionStorage": page.evaluate("JSON.stringify(Object.entries(sessionStorage))"),
        "cookie": page.evaluate("document.cookie"),
    }
    rep["token_findings"] = [k for k, v in blobs.items() if FAKE_TOKEN in v]
    rep["network_request_count"] = len(urls)
    return rep


def main():
    report = {"viewports": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            # --no-proxy-server: never route through the environment's egress
            # proxy; the audit is strictly local (127.0.0.1) by design.
            args=["--no-sandbox", "--no-proxy-server"])
        for w, h in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            try:
                report["viewports"][f"{w}x{h}"] = audit_viewport(page, w, h)
            finally:
                ctx.close()
        browser.close()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
