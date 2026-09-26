/**
 * Release Intelligence view tests — trust semantics only.
 *
 * These tests protect the user-facing distinctions the product promises:
 * deterministic vs AI provenance, historical severity vs change relevance,
 * and involved vs impacted DB2 resources. They do not test CSS, layout,
 * or implementation trivia.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  HistoricalIncident,
  IntelligenceResult,
  RelevantIncident,
} from "../../api";
import IntelligenceView from "../IntelligenceView";

vi.mock("../../api", () => ({
  api: {
    components: vi.fn().mockResolvedValue([]),
    intelligence: vi.fn(),
  },
}));

import { api } from "../../api";

const intelligence = vi.mocked(api.intelligence);

const incident: HistoricalIncident = {
  id: "INC-1042",
  title: "Duplicate WARRANTY row created",
  occurred_at: "2026-02-11",
  severity: "high",
  status: "resolved",
  summary: "A rerun created a duplicate WARRANTY row.",
  symptoms: ["SQLCODE -803"],
  linked_components: ["program:WARR001", "table:WARRANTY"],
  failure_mode: "duplicate_database_record",
  root_cause_category: "application_logic",
  root_cause_summary: "Missing duplicate guard.",
  resolution_summary: "Added the guard.",
};

const relevantIncident: RelevantIncident = {
  incident,
  primary_reason: "DIRECT_IMPACT_MATCH",
  relevance_reasons: [
    {
      reason: "DIRECT_IMPACT_MATCH",
      matched_component: "program:WARR001",
      explanation:
        "linked component program:WARR001 is directly impacted by the change",
      supporting_paths: [],
      evidence: [],
    },
  ],
  matched_components: ["program:WARR001", "table:WARRANTY"],
  supporting_resources: [],
};

function makeResult(
  overrides: Partial<IntelligenceResult["ai_explanation"]> = {}
): IntelligenceResult {
  return {
    changed_component: "copybook:WARRCOPY",
    impact: {
      changed_component: "copybook:WARRCOPY",
      changed_component_type: "COPYBOOK",
      direct_impacts: ["program:WARR001"],
      transitive_impacts: [],
      dependency_paths: [],
      relationships: ["USES_COPYBOOK"],
      evidence: [],
      affected_programs: ["program:WARR001"],
      affected_copybooks: [],
      affected_jobs: [],
      affected_procs: [],
      affected_tables: [],
      read_tables: ["table:WARRANTY"],
      write_tables: [],
      involved_resources: [
        {
          table: "table:WARRANTY",
          access: "read",
          used_by: ["program:WARR001"],
          evidence: [
            {
              file: "cobol/WARR001.cbl",
              line: 27,
              text: "FROM WARRANTY",
            },
          ],
        },
      ],
      maximum_impact_depth: 1,
      total_impacted_components: 1,
    },
    recommended_tests: [],
    risk_signals: [],
    release_checklist: [],
    incident_intelligence: {
      changed_component: "copybook:WARRCOPY",
      relevant_incidents: [relevantIncident],
      total_relevant_incidents: 1,
      primary_tier_counts: { DIRECT_IMPACT_MATCH: 1 },
      reason_counts: { DIRECT_IMPACT_MATCH: 1 },
    },
    ai_explanation: {
      subject_component: "copybook:WARRCOPY",
      explanation_source: "deterministic",
      executive_summary: "Change to copybook:WARRCOPY impacts 1 component.",
      technical_summary: "",
      testing_summary: "",
      release_considerations: "",
      incident_summary: "",
      historical_patterns: "",
      release_history_considerations: "",
      ...overrides,
    },
  };
}

beforeEach(() => {
  intelligence.mockReset();
});

describe("explanation provenance", () => {
  it("renders DETERMINISTIC SUMMARY for deterministic explanations", async () => {
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
  });

  it("never labels a deterministic explanation as AI", async () => {
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
    expect(screen.queryByText("AI EXPLANATION")).not.toBeInTheDocument();
    expect(
      screen.getByText(/no LLM was involved/)
    ).toBeInTheDocument();
  });

  it("renders AI EXPLANATION for AI-generated explanations", async () => {
    intelligence.mockResolvedValue(
      makeResult({
        explanation_source: "ai",
        executive_summary: "An LLM wrote this summary.",
      })
    );
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(screen.getByText("AI EXPLANATION")).toBeInTheDocument()
    );
    expect(
      screen.queryByText("DETERMINISTIC SUMMARY")
    ).not.toBeInTheDocument();
  });
});

describe("historical incidents", () => {
  it("keeps historical severity visually distinct from change relevance", async () => {
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(screen.getByText("historical severity: high")).toBeInTheDocument()
    );
    const severityBadge = screen.getByText("historical severity: high");
    const relevanceBadge = screen.getByText(/change relevance:/);
    // Two separate badges: severity must not masquerade as relevance.
    expect(severityBadge).not.toBe(relevanceBadge);
    expect(severityBadge.textContent).not.toMatch(/relevance/);
    expect(relevanceBadge.textContent).toMatch(/DIRECT IMPACT MATCH/);
  });

  it("states that historical severity is not current-change risk", async () => {
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(
        screen.getByText(/Historical severity describes the past incident/)
      ).toBeInTheDocument()
    );
  });
});

describe("involved DB2 resources", () => {
  it("presents involved tables as involved, not impacted", async () => {
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(screen.getByText("Involved DB2 Resources")).toBeInTheDocument()
    );
    // The explicit involved≠impacted disclaimer must be present.
    expect(
      screen.getByText(/involved in the change, not impacted by it/)
    ).toBeInTheDocument();
    // The involved table is rendered in its own section, not under
    // "Impacted Components".
    const impactedSection = screen
      .getByText("Impacted Components")
      .closest("section")!;
    expect(impactedSection.textContent).not.toMatch(/table:WARRANTY/);
  });
});

describe("loading and error states", () => {
  it("shows a loading state during analysis", async () => {
    let resolve!: (v: IntelligenceResult) => void;
    const pending = new Promise<IntelligenceResult>((r) => {
      resolve = r;
    });
    intelligence.mockReturnValue(pending);
    render(<IntelligenceView />);
    expect(screen.getAllByText("Analyzing…").length).toBeGreaterThan(0);
    resolve(makeResult());
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
  });

  it("shows the API error to the user", async () => {
    intelligence.mockRejectedValue(
      new Error("unknown component: copybook:DOES_NOT_EXIST")
    );
    render(<IntelligenceView />);
    await waitFor(() =>
      expect(
        screen.getByText("unknown component: copybook:DOES_NOT_EXIST")
      ).toBeInTheDocument()
    );
  });
});

describe("empty input", () => {
  it("asks for a component ID and does not call the API", async () => {
    const user = userEvent.setup();
    intelligence.mockResolvedValue(makeResult());
    render(<IntelligenceView />);
    // Wait for the initial (default-id) analysis to complete.
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
    expect(intelligence).toHaveBeenCalledTimes(1);

    await user.clear(screen.getByLabelText("Component id"));
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(
      screen.getByText("Enter or select a component ID.")
    ).toBeInTheDocument();
    // No additional API call for empty input.
    expect(intelligence).toHaveBeenCalledTimes(1);
  });
});
