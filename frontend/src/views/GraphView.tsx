import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api, type ComponentType, type GraphData } from "../api";
import EvidencePanel, { type EvidenceEdgeInfo } from "../components/EvidencePanel";

const TYPE_STYLE: Record<
  ComponentType,
  { color: string; shape: cytoscape.Css.Node["shape"] }
> = {
  COBOL_PROGRAM: { color: "#3b82f6", shape: "ellipse" },
  COPYBOOK: { color: "#22c55e", shape: "round-rectangle" },
  JCL_JOB: { color: "#f59e0b", shape: "hexagon" },
  JCL_PROC: { color: "#a855f7", shape: "diamond" },
  DB2_TABLE: { color: "#ef4444", shape: "triangle" },
};

const TYPE_LABEL: Record<ComponentType, string> = {
  COBOL_PROGRAM: "COBOL program",
  COPYBOOK: "Copybook",
  JCL_JOB: "JCL job",
  JCL_PROC: "JCL PROC",
  DB2_TABLE: "DB2 table",
};

/** Perpendicular spread between parallel-edge curve apexes (px). */
const PARALLEL_SPREAD = 60;

/**
 * Perpendicular offset for an edge's curve midpoint, so that multiple
 * independent relationships between the same node pair render as
 * distinguishable curves instead of overlapping. Single edges stay
 * straight (offset 0). The edges remain independent elements with
 * their own evidence — this only affects rendering.
 */
function parallelOffset(ele: cytoscape.EdgeSingular): number {
  const total = ele.data("parallelTotal") as number;
  if (!total || total <= 1) return 0;
  const index = ele.data("parallelIndex") as number;
  return (index - (total - 1) / 2) * PARALLEL_SPREAD;
}

export default function GraphView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const initialViewRef = useRef<{ zoom: number; pan: cytoscape.Position } | null>(
    null
  );
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceEdge, setEvidenceEdge] = useState<EvidenceEdgeInfo | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hintOpen, setHintOpen] = useState(true);

  useEffect(() => {
    api
      .graph()
      .then(setGraph)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!graph || !containerRef.current || cyRef.current) return;

    // Group edges by directed node pair so parallel relationships
    // (e.g. READS_TABLE + WRITES_TABLE between the same nodes) each
    // get their own curve offset. Semantics are unchanged: every
    // backend edge still becomes exactly one Cytoscape edge.
    const pairMembers = new Map<string, number[]>();
    graph.edges.forEach((e, i) => {
      const key = `${e.source}\u2192${e.target}`;
      const members = pairMembers.get(key);
      if (members) members.push(i);
      else pairMembers.set(key, [i]);
    });
    const parallelIndex = new Array<number>(graph.edges.length).fill(0);
    const parallelTotal = new Array<number>(graph.edges.length).fill(1);
    pairMembers.forEach((members) => {
      members.forEach((edgePos, pos) => {
        parallelIndex[edgePos] = pos;
        parallelTotal[edgePos] = members.length;
      });
    });

    const cy = cytoscape({
      container: containerRef.current,
      elements: {
        nodes: graph.nodes.map((n) => ({
          data: { id: n.id, name: n.name, type: n.type },
        })),
        edges: graph.edges.map((e, i) => ({
          data: {
            id: `e${i}`,
            source: e.source,
            target: e.target,
            relationship: e.relationship,
            file: e.evidence.file,
            line: e.evidence.line,
            text: e.evidence.text,
            parallelIndex: parallelIndex[i],
            parallelTotal: parallelTotal[i],
          },
        })),
      },
      style: [
        {
          selector: "node",
          style: {
            label: "data(name)",
            "text-valign": "center",
            "text-halign": "center",
            color: "#ffffff",
            "font-size": "10px",
            "text-outline-width": 2,
            "text-outline-color": "rgba(15,23,42,0.7)",
            width: 52,
            height: 52,
            "overlay-padding": "8px",
          },
        },
        ...(Object.keys(TYPE_STYLE) as ComponentType[]).map(
          (t): cytoscape.StylesheetStyle => ({
            selector: `node[type="${t}"]`,
            style: {
              "background-color": TYPE_STYLE[t].color,
              shape: TYPE_STYLE[t].shape,
            },
          })
        ),
        {
          selector: "edge",
          style: {
            width: 3,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "unbundled-bezier",
            "control-point-distances": parallelOffset,
            "control-point-weights": 0.5,
            label: "data(relationship)",
            "font-size": "9px",
            "font-weight": 600,
            color: "#334155",
            "text-background-color": "#f8fafc",
            "text-background-opacity": 1,
            "text-background-padding": "2px",
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "edge:selected",
          style: {
            "line-color": "#0ea5e9",
            "target-arrow-color": "#0ea5e9",
            width: 5,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 3,
            "border-color": "#0ea5e9",
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 40,
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 130,
      } as cytoscape.LayoutOptions,
    });

    // Guarantee every node is inside the visible container once the
    // layout settles, and remember the initial viewport for Reset.
    cy.one("layoutstop", () => {
      cy.fit(cy.elements(), 40);
      initialViewRef.current = { zoom: cy.zoom(), pan: { ...cy.pan() } };
    });

    cy.on("tap", "edge", (evt: cytoscape.EventObject) => {
      const d = evt.target.data();
      setEvidenceEdge({
        source: d.source as string,
        target: d.target as string,
        relationship: d.relationship as string,
        evidence: {
          file: d.file as string,
          line: d.line as number,
          text: d.text as string,
        },
      });
    });

    cy.on("tap", "node", (evt: cytoscape.EventObject) => {
      setSelectedNode(evt.target.id() as string);
    });

    cy.on("tap", (evt: cytoscape.EventObject) => {
      if (evt.target === cy) {
        setSelectedNode(null);
      }
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
      initialViewRef.current = null;
    };
  }, [graph]);

  const fitView = () => {
    const cy = cyRef.current;
    if (cy) cy.fit(cy.elements(), 40);
  };

  const resetView = () => {
    const cy = cyRef.current;
    const initial = initialViewRef.current;
    if (cy && initial) {
      cy.zoom(initial.zoom);
      cy.pan(initial.pan);
    } else if (cy) {
      cy.fit(cy.elements(), 40);
    }
  };

  if (error) return <div className="error-box">{error}</div>;

  return (
    <div>
      <h2>Dependency Graph</h2>
      <div className="graph-note">
        <button
          type="button"
          className="hint-toggle"
          aria-expanded={hintOpen}
          onClick={() => setHintOpen((o) => !o)}
        >
          {hintOpen ? "▾" : "▸"} Reading the graph
        </button>
        {hintOpen && (
          <span className="hint-body">
            {" "}an arrow <code>A → B</code> means <strong>A depends on B</strong>{" "}
            (e.g. <code>program:WARR001 → copybook:WARRCOPY</code> means WARR001
            uses copybook WARRCOPY). Click any edge to see the source evidence
            behind it; click a node to see its id and type.
          </span>
        )}
      </div>

      <div className="graph-toolbar">
        <div className="legend">
          {(Object.keys(TYPE_STYLE) as ComponentType[]).map((t) => (
            <span key={t} className="legend-item">
              <span
                className="legend-dot"
                style={{ backgroundColor: TYPE_STYLE[t].color }}
              />
              {TYPE_LABEL[t]}
            </span>
          ))}
        </div>
        <div className="graph-controls">
          <button type="button" className="btn btn-small" onClick={fitView}>
            Fit to view
          </button>
          <button
            type="button"
            className="btn btn-small btn-ghost"
            onClick={resetView}
          >
            Reset view
          </button>
        </div>
      </div>

      {!graph && !error && <p className="muted">Loading graph…</p>}
      <div className="graph-wrap">
        <div ref={containerRef} className="cy-container" />
        {selectedNode && (
          <div className="node-chip">
            <code>{selectedNode}</code>
            <button
              className="btn btn-small btn-ghost"
              onClick={() => setSelectedNode(null)}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      <EvidencePanel edge={evidenceEdge} onClose={() => setEvidenceEdge(null)} />
    </div>
  );
}
