import type { Dependency } from "../api";
import type { EvidenceEdgeInfo } from "./EvidencePanel";

interface Props {
  title: string;
  edges: Dependency[];
  emptyText: string;
  onShowEvidence: (edge: EvidenceEdgeInfo) => void;
  /** Render a component id; used to highlight the selected one. */
  highlightId?: string;
}

export function formatCompId(id: string): string {
  return id;
}

/** Renders a list of dependency edges with relationship labels and an
 *  evidence button per edge. */
export default function EdgeList({
  title,
  edges,
  emptyText,
  onShowEvidence,
  highlightId,
}: Props) {
  return (
    <section className="card">
      <h3>
        {title} <span className="count-badge">{edges.length}</span>
      </h3>
      {edges.length === 0 ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <ul className="edge-list">
          {edges.map((e, i) => (
            <li
              key={`${e.source}|${e.target}|${e.relationship}|${i}`}
              className="edge-row"
            >
              <span className="edge-endpoints">
                <code
                  className={e.source === highlightId ? "hl" : undefined}
                >
                  {formatCompId(e.source)}
                </code>
                <span className="rel-badge" title="relationship">
                  {e.relationship}
                </span>
                <code
                  className={e.target === highlightId ? "hl" : undefined}
                >
                  {formatCompId(e.target)}
                </code>
              </span>
              <button
                className="btn btn-small"
                onClick={() => onShowEvidence(e)}
              >
                Show evidence
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
