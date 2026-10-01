/**
 * GitHub PR view tests — Phase 3B frontend.
 *
 * Protects: input form (no token field anywhere), analyze request shape,
 * loading state, PR metadata header, changed-files list with source-scope
 * badges, rename old/new paths, outside-scope visibility, ChangeSetResults
 * reuse, backend error-code mapping (no stack traces), rate-limit display,
 * and the auth-configured badge. The api module is mocked; no network.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ChangeSetIntelligence,
  GitHubChangedFile,
  GitHubPullRequestAnalysis,
} from "../../api";
import GitHubPRView from "../GitHubPRView";

vi.mock("../../api", () => {
  class MockApiError extends Error {
    status: number;
    code: string | null;
    constructor(status: number, message: string, code: string | null = null) {
      super(message);
      this.status = status;
      this.code = code;
    }
  }
  return {
    api: {
      analyzeGitHubPR: vi.fn(),
      getGitHubStatus: vi.fn(),
    },
    ApiError: MockApiError,
  };
});

import { ApiError, api } from "../../api";

const analyzeGitHubPR = vi.mocked(api.analyzeGitHubPR);
const getGitHubStatus = vi.mocked(api.getGitHubStatus);

function makeIntel(): ChangeSetIntelligence {
  const tests = Array.from({ length: 7 }, (_, i) => ({
    test_id: `TC-WARR-00${i + 1}`,
    test_name: `Test ${i + 1}`,
    test_type: "batch",
    impact_level: (i < 6 ? "MUST_RUN" : "SHOULD_RUN") as "MUST_RUN" | "SHOULD_RUN",
    rationale: "covers job:WARRBTCH",
    evidence: [],
    recommended_because_of: [
      { change_root: "copybook:WARRCOPY", snapshot: "head" as const },
    ],
    per_root: [],
  }));
  return {
    change_set: { files: [], source: "github", base_ref: "main", head_ref: "x" },
    mapped_changes: [],
    ambiguous_changes: [],
    unmapped_changes: [],
    unresolved_changes: [],
    per_change_analysis: [],
    changed_components: [
      {
        component_id: "copybook:WARRCOPY",
        originating_files: ["copybook/WARRCOPY.cpy"],
        snapshot: "head",
        previous_component_ids: [],
        also_impacted_by: [],
      },
      {
        component_id: "program:WARR002",
        originating_files: ["cobol/WARR002.cbl"],
        snapshot: "head",
        previous_component_ids: [],
        also_impacted_by: [
          { change_root: "copybook:WARRCOPY", snapshot: "head" },
        ],
      },
    ],
    unique_impacted_components: [
      {
        component_id: "job:WARRBTCH",
        impacted_by: ["copybook:WARRCOPY"],
        impacted_by_count: 1,
        per_root: [],
      },
    ],
    impacted_by_one_change: ["job:WARRBTCH"],
    impacted_by_multiple_changes: [],
    involved_resources: [
      {
        table: "WARRANTY",
        access: "read",
        used_by: ["program:WARR002"],
        associated_change_roots: [],
        evidence: [],
      },
      {
        table: "CLAIM",
        access: "write",
        used_by: ["program:WARR002"],
        associated_change_roots: [],
        evidence: [],
      },
    ],
    recommended_tests: tests,
    risk_signals: Array.from({ length: 7 }, (_, i) => ({
      id: `RS-${i + 1}`,
      severity: "medium" as const,
      title: `Risk ${i + 1}`,
      explanation: "",
      triggered_by: [],
      supporting_components: [],
      change_roots: [],
      evidence: [],
    })),
    release_checklist: Array.from({ length: 7 }, (_, i) => ({
      id: `RC-${i + 1}`,
      title: `Check ${i + 1}`,
      detail: "",
      rule: "rule",
      related_components: [],
      applicable_change_roots: [],
    })),
    relevant_incidents: Array.from({ length: 11 }, (_, i) => ({
      incident: {
        id: `INC-${1000 + i}`,
        title: `Incident ${i}`,
        occurred_at: "2024-01-01",
        severity: "medium" as const,
        status: "resolved" as const,
        summary: "",
        symptoms: [],
        linked_components: [],
        failure_mode: "",
        root_cause_category: "",
        root_cause_summary: "",
        resolution_summary: "",
      },
      relevant_to_changes: [],
      per_change: [],
      primary_reason: "CHANGED_COMPONENT_MATCH" as const,
    })),
    mixed_snapshot_analysis: false,
    summary: {
      changed_files: 2,
      changed_components: 2,
      cross_impacted_changed_components: 1,
      ambiguous_files: 0,
      unmapped_files: 0,
      unresolved_files: 0,
      direct_impact_union: 3,
      transitive_impact_union: 3,
      unique_impacted_components: 4,
      overlap_impacted_components: 3,
      unique_recommended_tests: 7,
      must_run_tests: 6,
      should_run_tests: 1,
      involved_db2_reads: 1,
      involved_db2_writes: 2,
      risk_signals: 7,
      checklist_items: 7,
      relevant_incidents: 11,
    },
    deterministic_summary: "Change set: 2 file(s) -> 2 changed component(s).",
    ai_explanation: {
      subject: "github-pr:42",
      explanation_source: "deterministic",
      scope_summary: "PR change set summary.",
      impact_summary: "Impact summary.",
      testing_summary: "Testing summary.",
      release_considerations: "Considerations.",
      incident_summary: "Incident summary.",
      overlap_notes: "Overlap notes.",
    },
  };
}

function makeFile(partial: Partial<GitHubChangedFile>): GitHubChangedFile {
  return {
    filename: "sample_mainframe/copybook/WARRCOPY.cpy",
    previous_filename: null,
    status: "modified",
    additions: 5,
    deletions: 1,
    changes: 6,
    sha: "aaa111",
    source_scope: "in_source_scope",
    effective_status: "modified",
    source_relative_path: "copybook/WARRCOPY.cpy",
    source_relative_old_path: null,
    mapping_status: "mapped",
    mapped_components: ["copybook:WARRCOPY"],
    phase3a_snapshot: "head",
    ...partial,
  };
}

function makeResult(): GitHubPullRequestAnalysis {
  const files = [
    makeFile({}),
    makeFile({
      filename: "sample_mainframe/cobol/NEW.cbl",
      previous_filename: "sample_mainframe/cobol/OLD.cbl",
      status: "renamed",
      additions: 0,
      deletions: 0,
      sha: "bbb222",
      source_relative_path: "cobol/NEW.cbl",
      source_relative_old_path: "cobol/OLD.cbl",
      mapped_components: ["program:NEW"],
    }),
    makeFile({
      filename: "README.md",
      status: "modified",
      sha: "ccc333",
      source_scope: "outside_source_scope",
      effective_status: null,
      source_relative_path: null,
      mapping_status: null,
      mapped_components: [],
      phase3a_snapshot: null,
    }),
  ];
  return {
    provider: "github",
    repository: "abhiClone/mainframe-change-impact-intelligence",
    pull_request: {
      number: 42,
      title: "Fix warranty copybook layout",
      state: "open",
      draft: false,
      html_url:
        "https://github.com/abhiClone/mainframe-change-impact-intelligence/pull/42",
      author_login: "abhiClone",
      base_ref: "main",
      base_sha: "abc1234567890",
      base_repo_full_name: "abhiClone/mainframe-change-impact-intelligence",
      head_ref: "feature/warrcopy",
      head_sha: "def9876543210",
      head_repo_full_name: "abhiClone/mainframe-change-impact-intelligence",
      changed_files: 3,
      additions: 10,
      deletions: 2,
      created_at: "2026-09-26T10:00:00Z",
      updated_at: "2026-09-26T11:00:00Z",
    },
    source_root: "sample_mainframe",
    github_files: files,
    in_scope_files: files.slice(0, 2),
    outside_scope_files: files.slice(2),
    base_snapshot: {
      label: "base",
      repository_full_name: "abhiClone/mainframe-change-impact-intelligence",
      sha: "abc1234567890",
      file_count: 120,
      extracted_bytes: 4096,
    },
    head_snapshot: {
      label: "head",
      repository_full_name: "abhiClone/mainframe-change-impact-intelligence",
      sha: "def9876543210",
      file_count: 121,
      extracted_bytes: 4100,
    },
    change_set_intelligence: makeIntel(),
    rate_limit: {
      limit: 60,
      remaining: 59,
      reset: 1790000000,
      resource: "core",
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  analyzeGitHubPR.mockResolvedValue(makeResult());
  getGitHubStatus.mockResolvedValue({
    provider: "github",
    auth_configured: false,
  });
});

describe("GitHubPRView", () => {
  async function fillAndAnalyze(user: ReturnType<typeof userEvent.setup>) {
    await user.clear(screen.getByLabelText("GitHub repository (owner/repo)"));
    await user.type(
      screen.getByLabelText("GitHub repository (owner/repo)"),
      "abhiClone/mainframe-change-impact-intelligence"
    );
    await user.clear(screen.getByLabelText("Pull request number"));
    await user.type(screen.getByLabelText("Pull request number"), "42");
    await user.click(screen.getByText("Analyze Pull Request"));
  }

  it("renders repository, PR number and source-root inputs with no token field", () => {
    render(<GitHubPRView />);
    expect(
      screen.getByLabelText("GitHub repository (owner/repo)")
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Pull request number")).toBeInTheDocument();
    const root = screen.getByLabelText("Mainframe source root");
    expect(root).toBeInTheDocument();
    expect(root).toHaveValue("sample_mainframe");
    expect(screen.getByText("Analyze Pull Request")).toBeInTheDocument();
    // No credential input anywhere.
    expect(screen.queryByLabelText(/token/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("GITHUB_TOKEN");
  });

  it("shows the neutral auth-configured badge when the status endpoint answers", async () => {
    getGitHubStatus.mockResolvedValue({
      provider: "github",
      auth_configured: true,
    });
    render(<GitHubPRView />);
    await waitFor(() =>
      expect(
        screen.getByText("GitHub authentication configured")
      ).toBeInTheDocument()
    );
  });

  it("fires the analyze request with the parsed owner/repo/PR/source_root body", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() => expect(analyzeGitHubPR).toHaveBeenCalledTimes(1));
    expect(analyzeGitHubPR).toHaveBeenCalledWith({
      owner: "abhiClone",
      repo: "mainframe-change-impact-intelligence",
      pull_number: 42,
      source_root: "sample_mainframe",
    });
  });

  it("shows a loading state while analyzing", async () => {
    const user = userEvent.setup();
    let resolve!: (v: GitHubPullRequestAnalysis) => void;
    analyzeGitHubPR.mockImplementationOnce(
      () => new Promise<GitHubPullRequestAnalysis>((r) => (resolve = r))
    );
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    expect(screen.getByText("Analyzing…")).toBeInTheDocument();
    resolve(makeResult());
    await waitFor(() =>
      expect(screen.getByText(/PR #42/)).toBeInTheDocument()
    );
  });

  it("renders the PR metadata header with abbreviated SHAs and a safe external link", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(screen.getByText(/PR #42/)).toBeInTheDocument()
    );
    expect(screen.getByText(/Fix warranty copybook layout/)).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByText("abhiClone")).toBeInTheDocument();
    // Abbreviated 7-char SHAs (rendered as branch@sha), not full SHAs.
    expect(screen.getAllByText(/abc1234/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/def9876/).length).toBeGreaterThan(0);
    const link = screen.getByRole("link", { name: "View on GitHub" });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/abhiClone/mainframe-change-impact-intelligence/pull/42"
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // Trust label for the deterministic PR change set.
    expect(screen.getByText("VERIFIED PR CHANGE SET")).toBeInTheDocument();
  });

  it("lists changed files with GitHub status and source-scope badges", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(
        screen.getByText("sample_mainframe/copybook/WARRCOPY.cpy")
      ).toBeInTheDocument()
    );
    expect(screen.getAllByText("modified").length).toBeGreaterThan(0);
    expect(screen.getByText("renamed")).toBeInTheDocument();
    expect(screen.getAllByText("IN SCOPE").length).toBe(2);
    expect(screen.getByText("OUTSIDE SOURCE ROOT")).toBeInTheDocument();
  });

  it("shows rename old/new paths and mapped components, keeping GitHub status distinct", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(
        screen.getByText("sample_mainframe/cobol/NEW.cbl")
      ).toBeInTheDocument()
    );
    expect(
      screen.getByText("sample_mainframe/cobol/OLD.cbl")
    ).toBeInTheDocument();
    // GitHub status badge (uppercase rename) is distinct from mapping status.
    expect(screen.getByText("renamed")).toBeInTheDocument();
    expect(screen.getAllByText("mapped").length).toBeGreaterThan(0);
    expect(screen.getAllByText("copybook:WARRCOPY").length).toBeGreaterThan(0);
  });

  it("shows outside-scope files but marks them as outside the analysis", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(screen.getByText("README.md")).toBeInTheDocument()
    );
    expect(screen.getByText(/outside source scope/i)).toBeInTheDocument();
    expect(screen.getByText(/1 outside source root/i)).toBeInTheDocument();
  });

  it("reuses ChangeSetResults for the deterministic intelligence", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
    expect(
      screen.getByText("Change set: 2 file(s) -> 2 changed component(s).")
    ).toBeInTheDocument();
    // Deterministic Phase 3A intelligence renders through ChangeSetResults.
    expect(screen.getAllByText("copybook:WARRCOPY").length).toBeGreaterThan(0);
    expect(screen.getByText("Recommended Tests")).toBeInTheDocument();
  });

  it("displays the rate-limit line as operational metadata", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(screen.getByText(/59 requests remaining/)).toBeInTheDocument()
    );
    expect(
      screen.getByText(/operational metadata only/i)
    ).toBeInTheDocument();
  });

  it("maps the >3000-file incomplete state to a human message, no stack trace", async () => {
    const user = userEvent.setup();
    analyzeGitHubPR.mockRejectedValueOnce(
      new ApiError(422, "backend detail", "incomplete_change_set")
    );
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(
        screen.getByText(/more than 3000 files/i)
      ).toBeInTheDocument()
    );
    expect(screen.queryByText("Release Summary")).not.toBeInTheDocument();
  });

  it("maps the rate-limited error to a human message", async () => {
    const user = userEvent.setup();
    analyzeGitHubPR.mockRejectedValueOnce(
      new ApiError(429, "backend detail", "github_rate_limited")
    );
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(
        screen.getByText(/rate limit exceeded/i)
      ).toBeInTheDocument()
    );
  });

  it("maps not-found/not-authorized to the safe access wording", async () => {
    const user = userEvent.setup();
    analyzeGitHubPR.mockRejectedValueOnce(
      new ApiError(
        404,
        "backend detail",
        "repository_not_found_or_not_authorized"
      )
    );
    render(<GitHubPRView />);
    await fillAndAnalyze(user);
    await waitFor(() =>
      expect(
        screen.getByText(
          /was not found, or the configured GitHub credentials do not have access/i
        )
      ).toBeInTheDocument()
    );
  });

  it("rejects a malformed repository input without calling the API", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await user.type(
      screen.getByLabelText("GitHub repository (owner/repo)"),
      "https://github.com/owner/repo"
    );
    await user.type(screen.getByLabelText("Pull request number"), "42");
    await user.click(screen.getByText("Analyze Pull Request"));
    expect(
      await screen.findByText(/must look like owner\/repo/i)
    ).toBeInTheDocument();
    expect(analyzeGitHubPR).not.toHaveBeenCalled();
  });

  it("rejects a non-positive pull request number without calling the API", async () => {
    const user = userEvent.setup();
    render(<GitHubPRView />);
    await user.type(
      screen.getByLabelText("GitHub repository (owner/repo)"),
      "owner/repo"
    );
    await user.type(screen.getByLabelText("Pull request number"), "0");
    await user.click(screen.getByText("Analyze Pull Request"));
    expect(
      await screen.findByText(/positive integer/i)
    ).toBeInTheDocument();
    expect(analyzeGitHubPR).not.toHaveBeenCalled();
  });
});
