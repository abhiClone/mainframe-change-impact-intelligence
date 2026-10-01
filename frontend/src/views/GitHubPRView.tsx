/* Phase 3B — GitHub Pull Request view (read-only GitHub integration).
 *
 * GitHub is only a change-source provider: the backend fetches the PR's
 * changed-file list and exact base/head snapshots, then runs the frozen
 * Phase 3A change-set engine. Every impact number below comes from the
 * deterministic Phase 3A result carried intact in
 * change_set_intelligence. The browser only calls the local backend —
 * never GitHub — and there is no token field anywhere in this view.
 */
import { useEffect, useState } from "react";
import {
  ApiError,
  api,
  type GitHubChangedFile,
  type GitHubFileStatus,
  type GitHubPullRequestAnalysis,
  type GitHubRateLimit,
} from "../api";
import ChangeSetResults, {
  VerifiedChangeSetBadge,
} from "../components/ChangeSetResults";

const GITHUB_API_PREFIX = "https://github.com/";

function shortSha(sha: string): string {
  return sha.length > 7 ? sha.slice(0, 7) : sha;
}

function GitHubStatusBadge({ status }: { status: GitHubFileStatus }) {
  const cls =
    status === "added"
      ? "gh-added"
      : status === "modified"
        ? "gh-modified"
        : status === "removed"
          ? "gh-removed"
          : "gh-renamed";
  return <span className={`gh-status ${cls}`}>{status}</span>;
}

function ScopeBadge({ inScope }: { inScope: boolean }) {
  return inScope ? (
    <span className="scope-badge scope-in">IN SCOPE</span>
  ) : (
    <span className="scope-badge scope-out">OUTSIDE SOURCE ROOT</span>
  );
}

function MappingSummary({ file }: { file: GitHubChangedFile }) {
  if (file.source_scope === "outside_source_scope") {
    return <span className="muted small">— (outside source scope)</span>;
  }
  const status = file.mapping_status;
  if (status === "mapped") {
    return (
      <span>
        <span className="prov-badge prov-verified">mapped</span>{" "}
        {file.mapped_components.map((c) => (
          <code key={c}>{c}</code>
        ))}
      </span>
    );
  }
  if (status === "ambiguous") {
    return <span className="prov-badge prov-ai">ambiguous</span>;
  }
  if (status === "unmapped") {
    return <span className="prov-badge prov-det">unmapped</span>;
  }
  if (status === "requires_base_snapshot") {
    return <span className="prov-badge prov-base">requires base snapshot</span>;
  }
  return <span className="muted small">—</span>;
}

function RateLimitLine({ rateLimit }: { rateLimit: GitHubRateLimit }) {
  const parts: string[] = [];
  if (rateLimit.remaining !== null) {
    parts.push(`${rateLimit.remaining} requests remaining`);
  }
  if (rateLimit.reset !== null) {
    parts.push(
      `resets at ${new Date(rateLimit.reset * 1000).toLocaleTimeString()}`
    );
  }
  return (
    <p className="muted small prov-line">
      GitHub API{parts.length > 0 ? `: ${parts.join(" · ")}` : " rate-limit info"}
      {" "}— operational metadata only, not part of the technical analysis.
    </p>
  );
}

function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "incomplete_change_set":
        return "This pull request changes more than 3000 files. GitHub's PR file-list API cannot return the complete change set, so no impact analysis was performed.";
      case "github_rate_limited":
        return "GitHub API rate limit exceeded. Please wait until the limit resets and try again.";
      case "github_authentication_failed":
        return "GitHub authentication failed. The server-side GitHub token may be invalid or expired.";
      case "repository_not_found_or_not_authorized":
        return "Repository or pull request was not found, or the configured GitHub credentials do not have access.";
      case "pull_request_not_found":
        return "Pull request was not found in this repository.";
      case "snapshot_too_large":
        return "The repository snapshot at the PR's base or head SHA exceeds the safe download limits, so analysis was not performed.";
      case "unsafe_archive":
        return "The repository snapshot failed archive safety validation and was not extracted.";
      case "invalid_source_root":
        return "The Mainframe source root is not a safe repository-relative path.";
      case "head_snapshot_unavailable":
        return "The head snapshot could not be retrieved (the head repository may be unavailable).";
      case "github_unavailable":
        return "GitHub is currently unavailable. Please try again later.";
      case "snapshot_download_failed":
        return "The repository snapshot could not be downloaded from GitHub.";
      case "unsupported_github_status":
        return "The pull request contains a file status the analyzer does not support.";
      case "analysis_failed":
        return "The change-set analysis failed.";
      default:
        return e.message;
    }
  }
  return e instanceof Error ? e.message : String(e);
}

export default function GitHubPRView() {
  const [repoInput, setRepoInput] = useState("");
  const [prInput, setPrInput] = useState("");
  const [sourceRoot, setSourceRoot] = useState("sample_mainframe");
  const [authConfigured, setAuthConfigured] = useState<boolean | null>(null);
  const [result, setResult] = useState<GitHubPullRequestAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Neutral server-status badge; tolerate failure silently.
  useEffect(() => {
    let cancelled = false;
    api
      .getGitHubStatus()
      .then((s) => {
        if (!cancelled) setAuthConfigured(s.auth_configured);
      })
      .catch(() => {
        /* leave the badge hidden */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function analyze() {
    const repo = repoInput.trim();
    const prNumber = Number(prInput.trim());
    if (!/^[^/\s]+\/[^/\s]+$/.test(repo)) {
      setError("Repository must look like owner/repo (no URLs, no protocol).");
      return;
    }
    if (!Number.isInteger(prNumber) || prNumber <= 0) {
      setError("Pull request number must be a positive integer.");
      return;
    }
    const root = sourceRoot.trim();
    if (root.length === 0) {
      setError("Mainframe source root must not be empty.");
      return;
    }
    const [owner, name] = repo.split("/");
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const analysis = await api.analyzeGitHubPR({
        owner,
        repo: name,
        pull_number: prNumber,
        source_root: root,
      });
      setResult(analysis);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }

  const pr = result?.pull_request;

  return (
    <div>
      <section className="card">
        <div className="intel-section-head">
          <h3>
            GitHub Pull Request{" "}
            <span className="prov-badge prov-verified">
              VERIFIED PR CHANGE SET
            </span>
          </h3>
          <p className="muted small intel-hint">
            The backend reads the PR's changed-file list and exact base/head
            snapshots from GitHub (read-only), then runs the frozen Phase 3A
            change-set engine. The changed-file list came deterministically
            from GitHub PR metadata — GitHub does not verify business
            correctness.
          </p>
        </div>
        <div className="github-form">
          <label className="github-field">
            <span className="github-label">Repository</span>
            <input
              className="search-input"
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              placeholder="owner/repo"
              aria-label="GitHub repository (owner/repo)"
            />
          </label>
          <label className="github-field">
            <span className="github-label">Pull Request</span>
            <input
              className="search-input"
              value={prInput}
              onChange={(e) => setPrInput(e.target.value)}
              placeholder="#number"
              inputMode="numeric"
              aria-label="Pull request number"
            />
          </label>
          <label className="github-field">
            <span className="github-label">Mainframe Source Root</span>
            <input
              className="search-input"
              value={sourceRoot}
              onChange={(e) => setSourceRoot(e.target.value)}
              placeholder="sample_mainframe"
              aria-label="Mainframe source root"
            />
          </label>
        </div>
        <div className="changeset-actions">
          {authConfigured !== null && (
            <span
              className={`prov-badge ${authConfigured ? "prov-det" : "muted-badge"}`}
              aria-label="GitHub authentication status"
            >
              GitHub authentication{" "}
              {authConfigured ? "configured" : "not configured"}
            </span>
          )}
          <button
            type="button"
            className="btn"
            onClick={analyze}
            disabled={loading}
          >
            {loading ? "Analyzing…" : "Analyze Pull Request"}
          </button>
        </div>
        {error && <div className="error-box">{error}</div>}
      </section>

      {result && pr && (
        <>
          <section className="card">
            <div className="intel-section-head">
              <h3>
                PR #{pr.number}: {pr.title}
              </h3>
              <p className="muted small intel-hint">
                <span className={`gh-status ${pr.state === "open" ? "gh-added" : "gh-removed"}`}>
                  {pr.state}
                </span>{" "}
                {pr.draft && (
                  <span className="gh-status gh-renamed">draft</span>
                )}{" "}
                by <code>{pr.author_login}</code> · base{" "}
                <code>
                  {pr.base_ref}@{shortSha(pr.base_sha)}
                </code>{" "}
                ({pr.base_repo_full_name}) · head{" "}
                <code>
                  {pr.head_ref}@{shortSha(pr.head_sha)}
                </code>{" "}
                ({pr.head_repo_full_name ?? "unavailable"}) ·{" "}
                {pr.changed_files} files changed (+{pr.additions}/-
                {pr.deletions}){" "}
                {pr.html_url.startsWith(GITHUB_API_PREFIX) && (
                  <a
                    href={pr.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    View on GitHub
                  </a>
                )}
              </p>
            </div>
            <p className="muted small prov-line">
              Snapshots: base <code>{pr.base_repo_full_name}</code> @{" "}
              <code>{pr.base_sha}</code> ({result.base_snapshot.file_count}{" "}
              files) · head <code>{pr.head_repo_full_name ?? "unavailable"}</code>{" "}
              @ <code>{pr.head_sha}</code> ({result.head_snapshot.file_count}{" "}
              files)
            </p>
            {result.rate_limit && (
              <RateLimitLine rateLimit={result.rate_limit} />
            )}
          </section>

          <section className="card">
            <div className="intel-section-head">
              <h3>
                Changed Files{" "}
                <VerifiedChangeSetBadge />
              </h3>
              <p className="muted small intel-hint">
                {result.in_scope_files.length} in source scope ·{" "}
                {result.outside_scope_files.length} outside source root.
                Files outside the source root stay visible but never enter
                the Mainframe impact analysis.
              </p>
            </div>
            <ul className="id-list">
              {result.github_files.map((f) => (
                <li key={f.filename} className="github-file">
                  <GitHubStatusBadge status={f.status} />{" "}
                  <code className="github-path">{f.filename}</code>
                  {f.status === "renamed" && f.previous_filename && (
                    <span className="muted small">
                      {" "}
                      (renamed from <code>{f.previous_filename}</code>)
                    </span>
                  )}{" "}
                  <span className="muted small">
                    +{f.additions}/-{f.deletions}
                  </span>{" "}
                  <ScopeBadge
                    inScope={f.source_scope === "in_source_scope"}
                  />
                  <p className="muted small prov-line">
                    mapping: <MappingSummary file={f} />
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <ChangeSetResults intel={result.change_set_intelligence} />
        </>
      )}
    </div>
  );
}
