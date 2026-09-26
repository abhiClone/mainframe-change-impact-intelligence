import { useEffect, useState } from "react";
import { api, type Summary } from "../api";

const CARDS: {
  key: keyof Omit<Summary, "DEPENDENCIES">;
  label: string;
  color: string;
}[] = [
  { key: "COBOL_PROGRAM", label: "COBOL programs", color: "#3b82f6" },
  { key: "COPYBOOK", label: "Copybooks", color: "#22c55e" },
  { key: "JCL_JOB", label: "JCL jobs", color: "#f59e0b" },
  { key: "JCL_PROC", label: "JCL PROCs", color: "#a855f7" },
  { key: "DB2_TABLE", label: "DB2 tables", color: "#ef4444" },
];

export default function Overview() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .summary()
      .then((s) => setSummary(s))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="muted">Loading repository summary…</p>;
  if (error) return <div className="error-box">{error}</div>;
  if (!summary) return <p className="muted">No data.</p>;

  return (
    <div>
      <h2>Repository Overview</h2>
      <p className="muted">
        Deterministic scan of <code>sample_mainframe/</code> — counts of
        discovered components and dependency edges.
      </p>
      <div className="stat-grid">
        {CARDS.map((c) => (
          <div className="stat-card" key={c.key}>
            <div
              className="stat-dot"
              style={{ backgroundColor: c.color }}
            />
            <div className="stat-number">{summary[c.key]}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
        <div className="stat-card stat-total">
          <div className="stat-number">{summary.DEPENDENCIES}</div>
          <div className="stat-label">Dependency edges</div>
        </div>
      </div>
      <p className="muted small">
        Every dependency edge carries source evidence (file, line, text)
        extracted by the backend parsers.
      </p>
    </div>
  );
}
