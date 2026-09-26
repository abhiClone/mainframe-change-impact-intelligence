/**
 * GraphView tests — demo controls and parallel-edge rendering.
 *
 * These tests assert structure and configuration (controls exist, edges
 * stay independent with distinct curve offsets), never pixel geometry.
 * Real visual behaviour is verified in Chromium.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GraphData } from "../../api";
import GraphView from "../GraphView";

vi.mock("../../api", () => ({
  api: {
    graph: vi.fn(),
  },
}));

// Minimal cytoscape stand-in: records constructor options and exposes the
// viewport methods the view uses, without any real rendering.
const instances: Array<{ opts: any; cy: any }> = [];

vi.mock("cytoscape", () => {
  const mock = vi.fn((opts: any) => {
    const cy = {
      on: vi.fn(),
      one: vi.fn(),
      fit: vi.fn(),
      elements: vi.fn(() => []),
      zoom: vi.fn(),
      pan: vi.fn(),
      destroy: vi.fn(),
    };
    instances.push({ opts, cy });
    return cy;
  });
  return { default: mock };
});

import { api } from "../../api";

const graphMock = vi.mocked(api.graph);

const mockGraph: GraphData = {
  nodes: [
    {
      id: "program:WARR001",
      name: "WARR001",
      type: "COBOL_PROGRAM",
      source_file: "cobol/WARR001.cbl",
    },
    {
      id: "table:WARRANTY",
      name: "WARRANTY",
      type: "DB2_TABLE",
      source_file: "",
    },
    {
      id: "copybook:WARRCOPY",
      name: "WARRCOPY",
      type: "COPYBOOK",
      source_file: "copybooks/WARRCOPY.cpy",
    },
  ],
  edges: [
    {
      source: "program:WARR001",
      target: "table:WARRANTY",
      relationship: "READS_TABLE",
      evidence: { file: "cobol/WARR001.cbl", line: 27, text: "FROM WARRANTY" },
    },
    {
      source: "program:WARR001",
      target: "table:WARRANTY",
      relationship: "WRITES_TABLE",
      evidence: { file: "cobol/WARR001.cbl", line: 42, text: "INTO WARRANTY" },
    },
    {
      source: "program:WARR001",
      target: "copybook:WARRCOPY",
      relationship: "USES_COPYBOOK",
      evidence: { file: "cobol/WARR001.cbl", line: 5, text: "COPY WARRCOPY" },
    },
  ],
};

beforeEach(() => {
  instances.length = 0;
  graphMock.mockReset();
  graphMock.mockResolvedValue(mockGraph);
});

async function renderGraph() {
  render(<GraphView />);
  await waitFor(() => expect(instances.length).toBe(1));
  return instances[0];
}

describe("graph demo controls", () => {
  it("renders Fit to view and Reset view controls", async () => {
    await renderGraph();
    expect(
      screen.getByRole("button", { name: "Fit to view" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reset view" })
    ).toBeInTheDocument();
  });

  it("Fit to view fits the graph elements", async () => {
    const { cy } = await renderGraph();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Fit to view" }));
    expect(cy.fit).toHaveBeenCalled();
  });

  it("Reset view restores the viewport (falls back to fit)", async () => {
    const { cy } = await renderGraph();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reset view" }));
    // layoutstop never fires under the mock, so the view falls back to fit.
    expect(cy.fit).toHaveBeenCalled();
  });
});

describe("parallel-edge rendering", () => {
  it("keeps parallel relationships as independent edges with distinct curve offsets", async () => {
    const { opts } = await renderGraph();
    const edges = opts.elements.edges as Array<{ data: Record<string, any> }>;
    expect(edges).toHaveLength(3);

    const pair = edges.filter(
      (e) =>
        e.data.source === "program:WARR001" &&
        e.data.target === "table:WARRANTY"
    );
    expect(pair).toHaveLength(2);
    // No collapsing: both deterministic relationships survive as own edges.
    expect(pair.map((e) => e.data.relationship).sort()).toEqual([
      "READS_TABLE",
      "WRITES_TABLE",
    ]);
    expect(pair.map((e) => e.data.parallelTotal)).toEqual([2, 2]);
    expect(pair.map((e) => e.data.parallelIndex).sort()).toEqual([0, 1]);

    // The edge stylesheet separates parallel curves without manual zoom.
    const edgeStyle = (opts.style as Array<any>).find(
      (s) => s.selector === "edge"
    );
    expect(edgeStyle.style["curve-style"]).toBe("unbundled-bezier");
    const offset = edgeStyle.style["control-point-distances"] as (
      ele: any
    ) => number;
    const ele = (index: number, total: number) => ({
      data: (k: string) => (k === "parallelIndex" ? index : total),
    });
    expect(offset(ele(0, 1))).toBe(0); // single edge stays straight
    const a = offset(ele(0, 2));
    const b = offset(ele(1, 2));
    expect(a).not.toBe(b); // parallel pair curves are distinguishable
    expect(a).toBe(-b); // symmetric around the straight line
  });

  it("keeps evidence fields on every edge", async () => {
    const { opts } = await renderGraph();
    const edges = opts.elements.edges as Array<{ data: Record<string, any> }>;
    for (const e of edges) {
      expect(e.data.file).toBeTruthy();
      expect(typeof e.data.line).toBe("number");
      expect(e.data.text).toBeTruthy();
    }
  });
});

describe("reading-guide hint", () => {
  it("is collapsible but keeps the direction explanation available", async () => {
    await renderGraph();
    const user = userEvent.setup();
    const toggle = screen.getByRole("button", { name: /Reading the graph/ });
    expect(screen.getByText(/A depends on B/)).toBeInTheDocument();
    await user.click(toggle);
    expect(screen.queryByText(/A depends on B/)).not.toBeInTheDocument();
    await user.click(toggle);
    expect(screen.getByText(/A depends on B/)).toBeInTheDocument();
  });
});
