/**
 * App header tests — product subtitle must describe the shipped product,
 * not a stale phase label.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "../App";

vi.mock("../api", () => ({
  api: {
    summary: vi.fn().mockResolvedValue({}),
    components: vi.fn().mockResolvedValue([]),
    component: vi.fn().mockResolvedValue(null),
    graph: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
    impact: vi.fn().mockResolvedValue(null),
    intelligence: vi.fn().mockResolvedValue(null),
  },
  API_BASE: "http://localhost:8000",
}));

describe("app header", () => {
  it("shows the product subtitle, not the stale Phase 1 wording", () => {
    render(<App />);
    expect(
      screen.getByText(
        "Deterministic Mainframe Change Impact & Release Intelligence"
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/Phase 1 —/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Phase 1/)).not.toBeInTheDocument();
  });
});
