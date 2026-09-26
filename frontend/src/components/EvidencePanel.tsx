import type { Evidence } from "../api";
import "./EvidencePanel.css";

export interface EvidenceEdgeInfo {
  source: string;
  target: string;
  relationship: string;
  evidence: Evidence;
}

interface Props {
  edge: EvidenceEdgeInfo | null;
  onClose: () => void;
}

/** Drawer showing the source evidence behind one dependency edge. */
export default function EvidencePanel({ edge, onClose }: Props) {
  if (!edge) return null;
  return (
    <div className="evidence-overlay" onClick={onClose}>
      <aside
        className="evidence-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Dependency evidence"
      >
        <div className="evidence-header">
          <h3>Dependency evidence</h3>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <dl className="evidence-fields">
          <div>
            <dt>Relationship</dt>
            <dd>
              <span className="rel-badge">{edge.relationship}</span>
            </dd>
          </div>
          <div>
            <dt>Dependent (source)</dt>
            <dd>
              <code>{edge.source}</code>
            </dd>
          </div>
          <div>
            <dt>Depends on (target)</dt>
            <dd>
              <code>{edge.target}</code>
            </dd>
          </div>
          <div>
            <dt>Source file</dt>
            <dd>
              <code>{edge.evidence.file}</code>
            </dd>
          </div>
          <div>
            <dt>Line</dt>
            <dd>
              <code>{edge.evidence.line}</code>
            </dd>
          </div>
          <div className="evidence-text-block">
            <dt>Evidence text</dt>
            <dd>
              <pre className="evidence-text">{edge.evidence.text}</pre>
            </dd>
          </div>
        </dl>
        <p className="evidence-note">
          Deterministically extracted by the backend parser — no inference, no
          LLM.
        </p>
      </aside>
    </div>
  );
}
