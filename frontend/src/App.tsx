import { useState } from "react";
import Overview from "./views/Overview";
import Explorer from "./views/Explorer";
import ImpactView from "./views/ImpactView";
import GraphView from "./views/GraphView";
import IntelligenceView from "./views/IntelligenceView";
import { API_BASE } from "./api";
import "./App.css";

const TABS = [
  { id: "overview", label: "Repository Overview" },
  { id: "explorer", label: "Dependency Explorer" },
  { id: "impact", label: "Change Impact" },
  { id: "graph", label: "Graph" },
  { id: "intelligence", label: "Release Intelligence" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="app">
      <header className="app-header">
        <h1>Mainframe Change Impact &amp; Release Intelligence</h1>
        <p className="subtitle">
          Deterministic Mainframe Change Impact &amp; Release Intelligence
        </p>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="tab-content">
        {tab === "overview" && <Overview />}
        {tab === "explorer" && <Explorer />}
        {tab === "impact" && <ImpactView />}
        {tab === "graph" && <GraphView key="graph" />}
        {tab === "intelligence" && <IntelligenceView />}
      </main>

      <footer className="app-footer">
        <span className="muted small">
          API: <code>{API_BASE}</code> · All relationships come from the local
          backend with source evidence. No LLM, no external services.
        </span>
      </footer>
    </div>
  );
}
