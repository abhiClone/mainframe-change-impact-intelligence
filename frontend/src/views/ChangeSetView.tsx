import { useState } from "react";
import {
  api,
  type ChangeFileStatus,
  type ChangeSetFileInput,
  type ChangeSetIntelligence,
} from "../api";
import ChangeSetResults, {
  VerifiedChangeSetBadge,
} from "../components/ChangeSetResults";

const STATUSES: ChangeFileStatus[] = [
  "modified",
  "added",
  "deleted",
  "renamed",
  "unknown",
];

// Demo preset: populates the input rows ONLY. All results still come
// from the backend — no hard-coded output anywhere in this view.
const DEMO_FILES: ChangeSetFileInput[] = [
  { path: "copybook/WARRCOPY.cpy", status: "modified" },
  { path: "cobol/WARR002.cbl", status: "modified" },
];

function SectionHeader({
  title,
  badge,
  hint,
}: {
  title: string;
  badge?: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="intel-section-head">
      <h3>
        {title} {badge}
      </h3>
      {hint && <p className="muted small intel-hint">{hint}</p>}
    </div>
  );
}

export default function ChangeSetView() {
  const [rows, setRows] = useState<ChangeSetFileInput[]>([
    { path: "", status: "modified" },
  ]);
  const [result, setResult] = useState<ChangeSetIntelligence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function setRow(index: number, patch: Partial<ChangeSetFileInput>) {
    setRows((prev) =>
      prev.map((r, i) => (i === index ? { ...r, ...patch } : r))
    );
  }

  function addRow() {
    setRows((prev) => [...prev, { path: "", status: "modified" }]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  function loadDemo() {
    // Populates the input rows only; analysis still runs server-side.
    setRows(DEMO_FILES.map((f) => ({ ...f })));
    setResult(null);
    setError("");
  }

  async function analyze() {
    const files = rows
      .map((r) => ({ path: r.path.trim(), status: r.status }))
      .filter((r) => r.path.length > 0);
    if (files.length === 0) {
      setError("Add at least one changed file path.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const intel = await api.analyzeChangeSet({ files });
      setResult(intel);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <section className="card">
        <SectionHeader
          title="Release / Change Set"
          badge={<VerifiedChangeSetBadge />}
          hint="Supply changed files; the backend maps them to components deterministically and aggregates impact, tests, risks, checklist and incidents across every change root. Ambiguous files are never guessed; unmapped files create no Mainframe impact."
        />
        <div className="changeset-rows">
          {rows.map((row, i) => (
            <div key={i} className="changeset-row">
              <input
                className="search-input changeset-path"
                value={row.path}
                onChange={(e) => setRow(i, { path: e.target.value })}
                placeholder="file path, e.g. copybook/WARRCOPY.cpy"
                aria-label={`Changed file path ${i + 1}`}
              />
              <select
                className="changeset-status"
                value={row.status}
                onChange={(e) =>
                  setRow(i, { status: e.target.value as ChangeFileStatus })
                }
                aria-label={`Changed file status ${i + 1}`}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-ghost btn-small"
                onClick={() => removeRow(i)}
                aria-label={`Remove file row ${i + 1}`}
              >
                remove
              </button>
            </div>
          ))}
        </div>
        <div className="changeset-actions">
          <button type="button" className="btn-ghost" onClick={addRow}>
            Add file
          </button>
          <button type="button" className="btn-ghost" onClick={loadDemo}>
            Load demo change set
          </button>
          <button
            type="button"
            className="btn"
            onClick={analyze}
            disabled={loading}
          >
            {loading ? "Analyzing…" : "Analyze release"}
          </button>
        </div>
        {error && <div className="error-box">{error}</div>}
      </section>

      {result && <ChangeSetResults intel={result} />}
    </div>
  );
}
