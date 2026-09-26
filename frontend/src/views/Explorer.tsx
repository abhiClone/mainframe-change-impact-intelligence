import { useEffect, useMemo, useState } from "react";
import { api, type Component, type ComponentDetail } from "../api";
import EdgeList from "../components/EdgeList";
import EvidencePanel, { type EvidenceEdgeInfo } from "../components/EvidencePanel";

export default function Explorer() {
  const [components, setComponents] = useState<Component[]>([]);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ComponentDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [evidenceEdge, setEvidenceEdge] = useState<EvidenceEdgeInfo | null>(null);

  useEffect(() => {
    api
      .components()
      .then((cs) => {
        setComponents(cs);
        if (cs.length > 0 && !selectedId) setSelectedId(cs[0].id);
      })
      .catch((e: Error) => setListError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setDetailLoading(true);
    setDetailError(null);
    api
      .component(selectedId)
      .then((d) => setDetail(d))
      .catch((e: Error) => {
        setDetail(null);
        setDetailError(e.message);
      })
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return components;
    return components.filter(
      (c) =>
        c.id.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        c.type.toLowerCase().includes(q)
    );
  }, [components, query]);

  if (listError) return <div className="error-box">{listError}</div>;

  return (
    <div>
      <h2>Dependency Explorer</h2>
      <p className="muted">
        Search or select a component to see what it depends on (upstream) and
        what depends on it (downstream). Edge direction:{" "}
        <code>A —CALLS→ B</code> means A depends on B.
      </p>
      <div className="explorer-layout">
        <div className="card explorer-list">
          <input
            className="search-input"
            type="text"
            placeholder="Search components…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <ul className="comp-list">
            {filtered.map((c) => (
              <li key={c.id}>
                <button
                  className={`comp-item ${
                    c.id === selectedId ? "active" : ""
                  }`}
                  onClick={() => setSelectedId(c.id)}
                >
                  <span className="comp-name">
                    <code>{c.id}</code>
                  </span>
                  <span className="type-badge">{c.type}</span>
                </button>
              </li>
            ))}
          </ul>
          {filtered.length === 0 && (
            <p className="muted">No components match.</p>
          )}
        </div>

        <div className="explorer-detail">
          {detailLoading && <p className="muted">Loading component…</p>}
          {detailError && <div className="error-box">{detailError}</div>}
          {detail && (
            <>
              <div className="card comp-header">
                <h3>
                  <code>{detail.component.id}</code>
                </h3>
                <div className="comp-meta">
                  <span className="type-badge">{detail.component.type}</span>
                  <span className="muted small">
                    source: <code>{detail.component.source_file}</code>
                  </span>
                </div>
              </div>
              <EdgeList
                title="Upstream — this component depends on"
                edges={detail.upstream}
                emptyText="No upstream dependencies."
                onShowEvidence={setEvidenceEdge}
                highlightId={detail.component.id}
              />
              <EdgeList
                title="Downstream — components that depend on this"
                edges={detail.downstream}
                emptyText="Nothing depends on this component."
                onShowEvidence={setEvidenceEdge}
                highlightId={detail.component.id}
              />
            </>
          )}
        </div>
      </div>
      <EvidencePanel edge={evidenceEdge} onClose={() => setEvidenceEdge(null)} />
    </div>
  );
}
