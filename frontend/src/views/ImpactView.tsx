import { useEffect, useState } from "react";
import {
  api,
  type ImpactPath,
  type ImpactResult,
} from "../api";
import EvidencePanel, { type EvidenceEdgeInfo } from "../components/EvidencePanel";

const DEFAULT_ID = "copybook:WARRCOPY";

/** Render one dependency path as a hop chain:
 *  from0 <-[rel]- to0 <-[rel]- to1 ...
 *  (each "to" depends on the node to its left) */
function PathChain({
  path,
  onShowEvidence,
}: {
  path: ImpactPath;
  onShowEvidence: (e: EvidenceEdgeInfo) => void;
}) {
  const steps = path.path;
  if (steps.length === 0) return null;
  return (
    <div className="path-chain">
      <code className="path-node">{steps[0].from}</code>
      {steps.map((s, i) => (
        <span key={i} className="path-hop">
          <button
            className="path-arrow"
            title={`Evidence: ${s.relationship} ${s.to} -> ${s.from}`}
            onClick={() =>
              onShowEvidence({
                source: s.to,
                target: s.from,
                relationship: s.relationship,
                evidence: s.evidence,
              })
            }
          >
            ←<span className="rel-badge">{s.relationship}</span>
          </button>
          <code className="path-node">{s.to}</code>
        </span>
      ))}
    </div>
  );
}

export default function ImpactView() {
  const [inputId, setInputId] = useState(DEFAULT_ID);
  const [result, setResult] = useState<ImpactResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [knownIds, setKnownIds] = useState<string[]>([]);
  const [evidenceEdge, setEvidenceEdge] = useState<EvidenceEdgeInfo | null>(null);

  useEffect(() => {
    api
      .components()
      .then((cs) => setKnownIds(cs.map((c) => c.id)))
      .catch(() => {
        /* suggestions are optional */
      });
  }, []);

  const analyze = (id: string) => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    api
      .impact(trimmed)
      .then((r) => {
        setResult(r);
        setError(null);
      })
      .catch((e: Error) => {
        setResult(null);
        setError(e.message);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    analyze(DEFAULT_ID);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h2>Change Impact</h2>
      <p className="muted">
        Enter a component id to see everything that would be affected by
        changing it. <code>A ← B</code> means B depends on A.
      </p>

      <form
        className="impact-form"
        onSubmit={(e) => {
          e.preventDefault();
          analyze(inputId);
        }}
      >
        <input
          className="search-input impact-input"
          list="component-ids"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          placeholder="component id, e.g. copybook:WARRCOPY"
          aria-label="Component id"
        />
        <datalist id="component-ids">
          {knownIds.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>
        <button type="submit" className="btn" disabled={loading}>
          {loading ? "Analyzing…" : "Analyze impact"}
        </button>
      </form>

      {error && <div className="error-box">{error}</div>}
      {loading && <p className="muted">Analyzing…</p>}

      {result && (
        <div className="impact-results">
          <div className="card">
            <h3>
              Changed component: <code>{result.changed_component}</code>
            </h3>
            <p className="muted small">
              {result.direct_impact.length} directly impacted ·{" "}
              {result.transitive_impact.length} transitively impacted ·{" "}
              {result.dependency_paths.length} dependency path
              {result.dependency_paths.length === 1 ? "" : "s"}
            </p>
          </div>

          <div className="impact-columns">
            <section className="card">
              <h3>
                Direct impact{" "}
                <span className="count-badge">{result.direct_impact.length}</span>
              </h3>
              {result.direct_impact.length === 0 ? (
                <p className="muted">None.</p>
              ) : (
                <ul className="id-list">
                  {result.direct_impact.map((id) => (
                    <li key={id}>
                      <code>{id}</code>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="card">
              <h3>
                Transitive impact{" "}
                <span className="count-badge">
                  {result.transitive_impact.length}
                </span>
              </h3>
              {result.transitive_impact.length === 0 ? (
                <p className="muted">None.</p>
              ) : (
                <ul className="id-list">
                  {result.transitive_impact.map((id) => (
                    <li key={id}>
                      <code>{id}</code>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="card">
            <h3>
              Dependency paths{" "}
              <span className="count-badge">
                {result.dependency_paths.length}
              </span>
            </h3>
            <p className="muted small">
              Click a relationship label on a hop to see the source evidence
              for that edge.
            </p>
            {result.dependency_paths.length === 0 ? (
              <p className="muted">No impacted components.</p>
            ) : (
              <ul className="path-list">
                {result.dependency_paths.map((p, i) => (
                  <li key={i} className="path-item">
                    <div className="muted small">
                      Impacted: <code>{p.impacted}</code>
                    </div>
                    <PathChain
                      path={p}
                      onShowEvidence={setEvidenceEdge}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      <EvidencePanel edge={evidenceEdge} onClose={() => setEvidenceEdge(null)} />
    </div>
  );
}
