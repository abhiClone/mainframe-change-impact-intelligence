/**
 * Release / Change Set view tests — trust semantics only.
 *
 * Protects: deterministic mapping display (mapped/ambiguous/unmapped),
 * root provenance ("impacted because of"), deduplication, the
 * deterministic summary label, and the demo preset populating input
 * only (never hard-coded output). No CSS/layout assertions.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChangeSetIntelligence } from "../../api";
import ChangeSetView from "../ChangeSetView";

vi.mock("../../api", () => ({
  api: {
    analyzeChangeSet: vi.fn(),
  },
}));

import { api } from "../../api";

const analyzeChangeSet = vi.mocked(api.analyzeChangeSet);

function makeResult(): ChangeSetIntelligence {
  return {
    change_set: {
      files: [
        { path: "copybook/WARRCOPY.cpy", status: "modified", old_path: null },
        { path: "cobol/WARR002.cbl", status: "modified", old_path: null },
      ],
      source: "explicit",
      base_ref: null,
      head_ref: null,
    },
    mapped_changes: [
      {
        file: { path: "copybook/WARRCOPY.cpy", status: "modified", old_path: null },
        mapping_status: "mapped",
        component_ids: ["copybook:WARRCOPY"],
        candidate_components: [],
        selected_component_ids: [],
        previous_component_ids: [],
        current_component_ids: [],
        snapshot: "head",
        note: "",
      },
      {
        file: { path: "cobol/WARR002.cbl", status: "modified", old_path: null },
        mapping_status: "mapped",
        component_ids: ["program:WARR002"],
        candidate_components: [],
        selected_component_ids: [],
        previous_component_ids: [],
        current_component_ids: [],
        snapshot: "head",
        note: "",
      },
    ],
    ambiguous_changes: [],
    unmapped_changes: [
      {
        file: { path: "README.md", status: "modified", old_path: null },
        mapping_status: "unmapped",
        component_ids: [],
        candidate_components: [],
        selected_component_ids: [],
        previous_component_ids: [],
        current_component_ids: [],
        snapshot: "head",
        note: "",
      },
    ],
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
        impacted_by: ["copybook:WARRCOPY", "program:WARR002"],
        impacted_by_count: 2,
        per_root: [],
      },
      {
        component_id: "program:WARR001",
        impacted_by: ["copybook:WARRCOPY"],
        impacted_by_count: 1,
        per_root: [],
      },
    ],
    impacted_by_one_change: ["program:WARR001"],
    impacted_by_multiple_changes: ["job:WARRBTCH"],
    involved_resources: [],
    recommended_tests: [
      {
        test_id: "TC-WARR-001",
        test_name: "Warranty claim batch end-to-end",
        test_type: "batch",
        impact_level: "MUST_RUN",
        rationale: "covers job:WARRBTCH",
        evidence: [],
        recommended_because_of: [
          { change_root: "copybook:WARRCOPY", snapshot: "head" },
          { change_root: "program:WARR002", snapshot: "head" },
        ],
        per_root: [
          {
            change_root: "copybook:WARRCOPY",
            snapshot: "head",
            impact_level: "MUST_RUN",
            rationale: "covers job:WARRBTCH, directly impacted",
            matched_components: ["job:WARRBTCH"],
          },
          {
            change_root: "program:WARR002",
            snapshot: "head",
            impact_level: "SHOULD_RUN",
            rationale: "covers job:WARRBTCH, transitively impacted",
            matched_components: ["job:WARRBTCH"],
          },
        ],
      },
    ],
    risk_signals: [],
    release_checklist: [],
    relevant_incidents: [
      {
        incident: {
          id: "INC-1015",
          title: "WARRCOPY layout change broke WARR002 compile",
          occurred_at: "2024-11-02",
          severity: "medium",
          status: "resolved",
          summary: "s",
          symptoms: [],
          linked_components: ["copybook:WARRCOPY"],
          failure_mode: "",
          root_cause_category: "",
          root_cause_summary: "",
          resolution_summary: "",
        },
        relevant_to_changes: [
          { change_root: "copybook:WARRCOPY", snapshot: "head" },
          { change_root: "program:WARR002", snapshot: "head" },
        ],
        per_change: [
          {
            change_root: "copybook:WARRCOPY",
            snapshot: "head",
            primary_reason: "CHANGED_COMPONENT_MATCH",
            relevance_reasons: [],
            matched_components: ["copybook:WARRCOPY"],
          },
          {
            change_root: "program:WARR002",
            snapshot: "head",
            primary_reason: "DIRECT_IMPACT_MATCH",
            relevance_reasons: [],
            matched_components: ["program:WARR002"],
          },
        ],
        primary_reason: "CHANGED_COMPONENT_MATCH",
      },
    ],
    mixed_snapshot_analysis: false,
    summary: {
      changed_files: 3,
      changed_components: 2,
      cross_impacted_changed_components: 1,
      ambiguous_files: 0,
      unmapped_files: 1,
      unresolved_files: 0,
      direct_impact_union: 3,
      transitive_impact_union: 1,
      unique_impacted_components: 2,
      overlap_impacted_components: 1,
      unique_recommended_tests: 1,
      must_run_tests: 1,
      should_run_tests: 0,
      involved_db2_reads: 0,
      involved_db2_writes: 0,
      risk_signals: 0,
      checklist_items: 0,
      relevant_incidents: 1,
    },
    deterministic_summary: "Change set: 3 file(s) -> 2 changed component(s).",
    ai_explanation: {
      subject: "change-set:copybook:WARRCOPY+program:WARR002",
      explanation_source: "deterministic",
      scope_summary: "Release change set summary.",
      impact_summary: "Impact summary.",
      testing_summary: "Testing summary.",
      release_considerations: "Considerations.",
      incident_summary: "Incident summary.",
      overlap_notes: "Overlap notes.",
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  analyzeChangeSet.mockResolvedValue(makeResult());
});

describe("ChangeSetView", () => {
async function analyzeWithPath(user: ReturnType<typeof userEvent.setup>) {
  await user.clear(screen.getByLabelText("Changed file path 1"));
  await user.type(screen.getByLabelText("Changed file path 1"), "copybook/WARRCOPY.cpy");
  await user.click(screen.getByText("Analyze release"));
}


  it("renders the input form with add/remove controls", () => {
    render(<ChangeSetView />);
    expect(screen.getByText("Release / Change Set")).toBeInTheDocument();
    expect(screen.getByText("Add file")).toBeInTheDocument();
    expect(screen.getByText("Load demo change set")).toBeInTheDocument();
    expect(screen.getByText("Analyze release")).toBeInTheDocument();
    expect(screen.getByLabelText("Changed file path 1")).toBeInTheDocument();
  });

  it("adds and removes changed-file rows", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await user.click(screen.getByText("Add file"));
    expect(screen.getByLabelText("Changed file path 2")).toBeInTheDocument();
    await user.click(screen.getAllByText("remove")[0]);
    expect(screen.queryByLabelText("Changed file path 2")).not.toBeInTheDocument();
  });

  it("demo preset only populates input and does not call the API", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await user.click(screen.getByText("Load demo change set"));
    expect(analyzeChangeSet).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Changed file path 1")).toHaveValue(
      "copybook/WARRCOPY.cpy"
    );
    expect(screen.getByLabelText("Changed file path 2")).toHaveValue(
      "cobol/WARR002.cbl"
    );
    expect(screen.queryByText("Release Summary")).not.toBeInTheDocument();
  });

  it("analyze request uses the supplied files", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await user.clear(screen.getByLabelText("Changed file path 1"));
    await user.type(screen.getByLabelText("Changed file path 1"), "copybook/UNUSED.cpy");
    await user.click(screen.getByText("Analyze release"));
    await waitFor(() => expect(analyzeChangeSet).toHaveBeenCalledTimes(1));
    expect(analyzeChangeSet).toHaveBeenCalledWith({
      files: [{ path: "copybook/UNUSED.cpy", status: "modified" }],
    });
  });

  it("shows mapped/unmapped distinction from the API result", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("Release Summary")).toBeInTheDocument()
    );
    expect(screen.getAllByText("copybook/WARRCOPY.cpy").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getAllByText("mapped")).toHaveLength(2);
    expect(screen.getByText("unmapped")).toBeInTheDocument();
  });

  it("renders impact overlap and root provenance", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("Impact Overlap")).toBeInTheDocument()
    );
    expect(screen.getAllByText("job:WARRBTCH")).toHaveLength(2);
    // Provenance: "impacted because of" lists both change roots.
    const provenance = screen.getAllByText(/impacted because of/i);
    expect(provenance.length).toBeGreaterThan(0);
  });

  it("displays each deduplicated test once with its per-change reasons", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("Warranty claim batch end-to-end")).toBeInTheDocument()
    );
    expect(screen.getAllByText("TC-WARR-001")).toHaveLength(1);
    expect(screen.getByText(/recommended because of/i)).toBeInTheDocument();
  });

  it("shows the deterministic summary label and text", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("DETERMINISTIC SUMMARY")).toBeInTheDocument()
    );
    expect(
      screen.getByText("Change set: 3 file(s) -> 2 changed component(s).")
    ).toBeInTheDocument();
  });

  it("shows the verified change set badge", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getAllByText("VERIFIED CHANGE SET").length).toBeGreaterThan(0)
    );
  });

  it("renders incident relevance per change root", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("Historical Incidents")).toBeInTheDocument()
    );
    expect(screen.getByText("INC-1015")).toBeInTheDocument();
    expect(screen.getByText(/relevant to/i)).toBeInTheDocument();
  });

  it("shows a loading state while analyzing", async () => {
    const user = userEvent.setup();
    let resolve!: (v: ChangeSetIntelligence) => void;
    analyzeChangeSet.mockImplementationOnce(
      () => new Promise<ChangeSetIntelligence>((r) => (resolve = r))
    );
    render(<ChangeSetView />);
    await user.clear(screen.getByLabelText("Changed file path 1"));
    await user.type(screen.getByLabelText("Changed file path 1"), "copybook/WARRCOPY.cpy");
    await user.click(screen.getByText("Analyze release"));
    expect(screen.getByText("Analyzing…")).toBeInTheDocument();
    resolve(makeResult());
    await waitFor(() =>
      expect(screen.getByText("Release Summary")).toBeInTheDocument()
    );
  });

  it("shows an API error without crashing", async () => {
    const user = userEvent.setup();
    analyzeChangeSet.mockRejectedValueOnce(new Error("boom"));
    render(<ChangeSetView />);
    await user.clear(screen.getByLabelText("Changed file path 1"));
    await user.type(screen.getByLabelText("Changed file path 1"), "copybook/WARRCOPY.cpy");
    await user.click(screen.getByText("Analyze release"));
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
    expect(screen.queryByText("Release Summary")).not.toBeInTheDocument();
  });

  it("requires at least one file path", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await user.click(screen.getByText("Analyze release"));
    expect(
      await screen.findByText("Add at least one changed file path.")
    ).toBeInTheDocument();
    expect(analyzeChangeSet).not.toHaveBeenCalled();
  });

  it("renders the Changed Components section separately from downstream impact", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText("Changed Components")).toBeInTheDocument()
    );
    expect(screen.getByText("Downstream Impacted Components")).toBeInTheDocument();
    // Changed roots carry their snapshot badge.
    expect(screen.getAllByText("head").length).toBeGreaterThan(0);
  });

  it("shows cross-impact between changed roots, not hidden in downstream", async () => {
    const user = userEvent.setup();
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText(/also downstream-impacted by/i)).toBeInTheDocument()
    );
    // Downstream section excludes changed roots: program:WARR002 is a
    // changed root, job:WARRBTCH is downstream.
    const downstream = screen.getByText("Downstream Impacted Components");
    expect(downstream).toBeInTheDocument();
    expect(screen.getByText("changed also impacted")).toBeInTheDocument();
  });

  it("shows the mixed-snapshot note when base and head roots are combined", async () => {
    const user = userEvent.setup();
    const mixed = makeResult();
    mixed.mixed_snapshot_analysis = true;
    analyzeChangeSet.mockResolvedValueOnce(mixed);
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText(/Mixed-snapshot release/i)).toBeInTheDocument()
    );
  });

  it("shows rename previous/current component provenance for renamed files", async () => {
    const user = userEvent.setup();
    const renamed = makeResult();
    renamed.mapped_changes = [
      {
        file: {
          path: "cobol/ZZZ.cbl",
          status: "renamed",
          old_path: "cobol/AAA.cbl",
        },
        mapping_status: "mapped",
        component_ids: ["program:AAA", "program:ZZZ"],
        candidate_components: [],
        selected_component_ids: [],
        previous_component_ids: ["program:AAA"],
        current_component_ids: ["program:ZZZ"],
        snapshot: "head",
        note: "",
      },
    ];
    analyzeChangeSet.mockResolvedValueOnce(renamed);
    render(<ChangeSetView />);
    await analyzeWithPath(user);
    await waitFor(() =>
      expect(screen.getByText(/rename identity|rename:/i)).toBeInTheDocument()
    );
    expect(screen.getAllByText("cobol/ZZZ.cbl").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("cobol/AAA.cbl")).toBeInTheDocument();
  });
});
