import { useEffect, useState } from "react";
import {
  api,
  type Evidence,
  type IncidentIntelligence,
  type IntelligenceImpact,
  type IntelligenceResult,
  type IntelligencePath,
  type RecommendedTest,
  type RelevantIncident,
  type RelevanceReasonType,
  type ReleaseChecklistItem,
  type RiskSignal,
} from "../api";
import EvidencePanel, { type EvidenceEdgeInfo } from "../components/EvidencePanel";

const DEFAULT_ID = "copybook:WARRCOPY";
const AI_UNAVAILABLE_PREFIX = "AI explanation unavailable.";

function ProvenanceBadge({ ai }: { ai?: boolean }) {
  return ai ? (
    <span className="prov-badge prov-ai">AI EXPLANATION</span>
  ) : (
    <span className="prov-badge prov-verified">VERIFIED IMPACT</span>
  );
}

function DeterministicSummaryBadge() {
  return <span className="prov-badge prov-det">DETERMINISTIC SUMMARY</span>;
}

function SectionHeader({ title, ai, hint }: { title: string; ai?: boolean; hint?: string }) {
  return (
    <div className="intel-section-head">
      <h3>
        {title} <ProvenanceBadge ai={ai} />
      </h3>
      {hint && <p className="muted small intel-hint">{hint}</p>}
    </div>
  );
}

function EvidenceRef({ evidence }: { evidence: Evidence }) {
  return (
    <code className="ev-ref" title={evidence.text}>
      {evidence.file}:{evidence.line}
    </code>
  );
}

function PathChain({
  path,
  onShowEvidence,
}: {
  path: IntelligencePath;
  onShowEvidence: (e: EvidenceEdgeInfo) => void;
}) {
  const steps = path.path;
  if (steps.length === 0) return null;
  return (
    <div className="path-chain">
      <code className="path-node">{steps[0].target}</code>
      {steps.map((s, i) => (
        <span key={i} className="path-hop">
          <button
            className="path-arrow"
            title={`Evidence: ${s.relationship} ${s.source} -> ${s.target}`}
            onClick={() =>
              onShowEvidence({
                source: s.source,
                target: s.target,
                relationship: s.relationship,
                evidence: s.evidence,
              })
            }
          >
            ←<span className="rel-badge">{s.relationship}</span>
          </button>
          <code className="path-node">{s.source}</code>
        </span>
      ))}
    </div>
  );
}

function ImpactedGroups({ impact }: { impact: IntelligenceImpact }) {
  const groups: { label: string; ids: string[] }[] = [
    { label: "Programs", ids: impact.affected_programs },
    { label: "Copybooks", ids: impact.affected_copybooks },
    { label: "Jobs", ids: impact.affected_jobs },
    { label: "Procs", ids: impact.affected_procs },
    { label: "Tables", ids: impact.affected_tables },
  ];
  return (
    <div className="impact-columns">
      {groups.map((g) => (
        <section className="card" key={g.label}>
          <h3>
            {g.label} <span className="count-badge">{g.ids.length}</span>
          </h3>
          {g.ids.length === 0 ? (
            <p className="muted small">None.</p>
          ) : (
            <ul className="id-list">
              {g.ids.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

function InvolvedResources({ impact }: { impact: IntelligenceImpact }) {
  if (impact.involved_resources.length === 0) return null;
  return (
    <div className="impact-columns">
      {impact.involved_resources.map((r) => (
        <section className="card" key={`${r.table}:${r.access}`}>
          <h3>
            <code>{r.table}</code>{" "}
            <span className={`rel-badge ${r.access}`}>{r.access}</span>
          </h3>
          <div className="muted small">
            Used by:{" "}
            {r.used_by.map((p, i) => (
              <span key={p}>
                <code>{p}</code>
                {i < r.used_by.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
          <div className="muted small">
            Evidence:{" "}
            {r.evidence.map((e, i) => (
              <span key={i} className="ev-gap">
                <EvidenceRef evidence={e} />
              </span>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function TestCard({
  test,
  onShowEvidence,
}: {
  test: RecommendedTest;
  onShowEvidence: (e: EvidenceEdgeInfo) => void;
}) {
  return (
    <li className="intel-item">
      <div className="intel-item-head">
        <span
          className={`priority-badge ${
            test.impact_level === "MUST_RUN" ? "must-run" : "should-run"
          }`}
        >
          {test.impact_level}
        </span>
        <strong>{test.test_name}</strong>
        <code className="small">{test.test_id}</code>
        <span className="type-badge">{test.test_type}</span>
      </div>
      <div className="muted small">
        Matched components:{" "}
        {test.matched_components.map((c, i) => (
          <span key={c}>
            <code>{c}</code>
            {i < test.matched_components.length - 1 ? ", " : ""}
          </span>
        ))}
      </div>
      <p className="intel-rationale">{test.rationale}</p>
      {test.dependency_paths.length > 0 && (
        <ul className="path-list">
          {test.dependency_paths.map((p, i) => (
            <li key={i} className="path-item">
              <div className="muted small">
                Path to: <code>{p.impacted}</code>
              </div>
              <PathChain path={p} onShowEvidence={onShowEvidence} />
            </li>
          ))}
        </ul>
      )}
      {test.evidence.length > 0 && (
        <div className="muted small">
          Evidence:{" "}
          {test.evidence.map((e, i) => (
            <span key={i} className="ev-gap">
              <EvidenceRef evidence={e} />
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function SignalCard({ signal }: { signal: RiskSignal }) {
  return (
    <li className="intel-item">
      <div className="intel-item-head">
        <span className={`severity-badge sev-${signal.severity}`}>
          {signal.severity}
        </span>
        <strong>{signal.title}</strong>
        <code className="small">{signal.id}</code>
      </div>
      <p>{signal.explanation}</p>
      <div className="muted small">
        Triggered by:{" "}
        {signal.triggered_by.map((c, i) => (
          <span key={c}>
            <code>{c}</code>
            {i < signal.triggered_by.length - 1 ? ", " : ""}
          </span>
        ))}
      </div>
      {signal.supporting_components.length > 0 && (
        <div className="muted small">
          Supporting components:{" "}
          {signal.supporting_components.map((c, i) => (
            <span key={c}>
              <code>{c}</code>
              {i < signal.supporting_components.length - 1 ? ", " : ""}
            </span>
          ))}
        </div>
      )}
      {signal.evidence.length > 0 && (
        <div className="muted small">
          Evidence:{" "}
          {signal.evidence.map((e, i) => (
            <span key={i} className="ev-gap">
              <EvidenceRef evidence={e} />
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function ChecklistCard({ item }: { item: ReleaseChecklistItem }) {
  return (
    <li className="intel-item">
      <div className="intel-item-head">
        <strong>{item.title}</strong>
        <code className="small">{item.id}</code>
        <span className="type-badge">rule: {item.rule}</span>
      </div>
      <p>{item.detail}</p>
      {item.related_components.length > 0 && (
        <div className="muted small">
          Related:{" "}
          {item.related_components.map((c, i) => (
            <span key={c}>
              <code>{c}</code>
              {i < item.related_components.length - 1 ? ", " : ""}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function AiExplanationSection({ ai }: { ai: IntelligenceResult["ai_explanation"] }) {
  const isAi = ai.explanation_source === "ai";
  const fallback = ai.executive_summary.startsWith(AI_UNAVAILABLE_PREFIX);
  const executive = fallback
    ? ai.executive_summary.slice(AI_UNAVAILABLE_PREFIX.length).trim()
    : ai.executive_summary;
  const summaries = [
    { label: "Technical summary", text: ai.technical_summary },
    { label: "Testing summary", text: ai.testing_summary },
    { label: "Release considerations", text: ai.release_considerations },
    { label: "Incident summary", text: ai.incident_summary },
    { label: "Historical patterns", text: ai.historical_patterns },
    { label: "Release history considerations", text: ai.release_history_considerations },
  ];
  return (
    <section className="card intel-ai">
      <div className="intel-section-head">
        <h3>
          {isAi ? "AI Explanation" : "Deterministic Summary"}{" "}
          {isAi ? <ProvenanceBadge ai /> : <DeterministicSummaryBadge />}
        </h3>
        <p className="muted small intel-hint">
          {isAi
            ? "Generated by an LLM and validated against deterministic evidence. AI prose is non-authoritative: deterministic evidence remains the source of truth."
            : fallback
              ? "The AI explanation layer was unavailable or failed validation, so a deterministic summary was generated instead. Deterministic evidence remains the source of truth."
              : "Generated from deterministic impact analysis — no LLM was involved. Deterministic evidence remains the source of truth."}
        </p>
      </div>
      {fallback && (
        <div className="graph-note">
          The AI explanation layer was unavailable for this change — showing the
          deterministic fallback summary instead.
        </div>
      )}
      {executive && (
        <div className="ai-block">
          <h4>Executive summary</h4>
          <p>{executive}</p>
        </div>
      )}
      {summaries.map((s) =>
        s.text ? (
          <div className="ai-block" key={s.label}>
            <h4>{s.label}</h4>
            <p>{s.text}</p>
          </div>
        ) : null
      )}
      {!executive && summaries.every((s) => !s.text) && (
        <p className="muted">No explanation available.</p>
      )}
    </section>
  );
}

function ReasonLabel({ reason }: { reason: RelevanceReasonType }) {
  return (
    <span className="prov-badge prov-reason">
      {reason.replace(/_/g, " ")}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`severity-badge sev-${severity}`}>
      historical severity: {severity}
    </span>
  );
}

function IncidentCard({
  item,
  onShowEvidence,
}: {
  item: RelevantIncident;
  onShowEvidence: (e: EvidenceEdgeInfo) => void;
}) {
  const inc = item.incident;
  return (
    <li className="intel-item">
      <div className="intel-item-head">
        <strong>
          <code>{inc.id}</code> — {inc.title}
        </strong>
      </div>
      <div className="muted small">
        {inc.occurred_at} · {inc.status} · failure mode: {inc.failure_mode}
      </div>
      <div className="badge-row">
        <SeverityBadge severity={inc.severity} />
        <span className="prov-badge prov-relevance">
          change relevance: {item.primary_reason.replace(/_/g, " ")}
        </span>
      </div>
      <p className="muted small intel-hint">
        Historical severity describes the past incident, not the risk of the
        current change. Relevance is decided deterministically from impact
        data — a critical historical incident with no deterministic link is
        never selected.
      </p>
      {item.relevance_reasons.map((r, i) => (
        <div key={i} className="reason-block">
          <div>
            <ReasonLabel reason={r.reason} />{" "}
            <span className="muted small">
              matched: <code>{r.matched_component}</code>
            </span>
          </div>
          <p className="small reason-expl">{r.explanation}</p>
          {r.supporting_paths.length > 0 && (
            <div className="muted small">Deterministic path(s):</div>
          )}
          {r.supporting_paths.map((p, j) => (
            <PathChain key={j} path={p} onShowEvidence={onShowEvidence} />
          ))}
          {r.evidence.length > 0 && (
            <div className="muted small">
              Evidence:{" "}
              {r.evidence.map((e, k) => (
                <span key={k}>
                  <EvidenceRef evidence={e} />
                  {k < r.evidence.length - 1 ? " " : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      <div className="incident-detail">
        <div className="muted small">
          <strong>Symptoms:</strong> {inc.symptoms.join("; ") || "—"}
        </div>
        <div className="muted small">
          <strong>Root cause:</strong> {inc.root_cause_summary || "—"}
        </div>
        <div className="muted small">
          <strong>Resolution:</strong> {inc.resolution_summary || "—"}
        </div>
      </div>
    </li>
  );
}

function IncidentIntelligenceSection({
  intel,
  onShowEvidence,
}: {
  intel: IncidentIntelligence;
  onShowEvidence: (e: EvidenceEdgeInfo) => void;
}) {
  const primary = intel.primary_tier_counts;
  const allReasons = intel.reason_counts;
  const tierLabels: Record<string, string> = {
    CHANGED_COMPONENT_MATCH: "changed-component",
    DIRECT_IMPACT_MATCH: "direct-impact",
    TRANSITIVE_IMPACT_MATCH: "transitive-impact",
    INVOLVED_WRITE_RESOURCE_MATCH: "involved-write",
    INVOLVED_READ_RESOURCE_MATCH: "involved-read",
  };
  return (
    <section className="card">
      <SectionHeader
        title="Historical Incident Intelligence"
        hint="Deterministic historical correlation: incidents whose structured component links intersect the change, its impact set, or its involved DB2 resources. Selection is deterministic — no LLM decides which incidents are relevant."
      />
      {intel.total_relevant_incidents === 0 ? (
        <p className="muted">
          No historical incidents are deterministically relevant to this
          change.
        </p>
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-number">
                {intel.total_relevant_incidents}
              </div>
              <div className="stat-label">relevant incidents</div>
            </div>
            {Object.entries(tierLabels).map(([key, label]) => (
              <div className="stat-card" key={key}>
                <div className="stat-number">{primary[key] ?? 0}</div>
                <div className="stat-label">primary tier: {label}</div>
              </div>
            ))}
          </div>
          <p className="muted">
            Primary-tier counts sum to the incident total. All-reason counts
            (one incident may carry several valid reasons):{" "}
            {Object.entries(tierLabels)
              .map(([key, label]) => `${label}: ${allReasons[key] ?? 0}`)
              .join(" · ")}
          </p>
          <ul className="intel-list">
            {intel.relevant_incidents.map((r) => (
              <IncidentCard
                key={r.incident.id}
                item={r}
                onShowEvidence={onShowEvidence}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function IntelligenceView() {
  const [inputId, setInputId] = useState(DEFAULT_ID);
  const [result, setResult] = useState<IntelligenceResult | null>(null);
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
    if (!trimmed) {
      setError("Enter or select a component ID.");
      return;
    }
    setLoading(true);
    setError(null);
    api
      .intelligence(trimmed)
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
      <h2>Release Intelligence</h2>
      <p className="muted">
        Enter a component id to get its full release-intelligence report:
        impact summary, recommended tests, release-risk signals, release
        checklist, and an AI-generated explanation grounded in the verified
        data.
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
          list="intel-component-ids"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          placeholder="component id, e.g. copybook:WARRCOPY"
          aria-label="Component id"
        />
        <datalist id="intel-component-ids">
          {knownIds.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>
        <button type="submit" className="btn" disabled={loading}>
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      {error && <div className="error-box">{error}</div>}
      {loading && <p className="muted">Analyzing…</p>}

      {result && (
        <div className="intel-results">
          <section className="card">
            <SectionHeader
              title="Change Summary"
              hint="Deterministic impact context from the Phase 1 dependency graph."
            />
            <h3>
              <code>{result.impact.changed_component}</code>{" "}
              <span className="type-badge">
                {result.impact.changed_component_type}
              </span>
            </h3>
            <div className="stat-grid">
              <div className="stat-card">
                <div className="stat-number">
                  {result.impact.direct_impacts.length}
                </div>
                <div className="stat-label">direct impacts</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.impact.transitive_impacts.length}
                </div>
                <div className="stat-label">transitive impacts</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.impact.total_impacted_components}
                </div>
                <div className="stat-label">total impacted</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.impact.maximum_impact_depth}
                </div>
                <div className="stat-label">max impact depth</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.recommended_tests.length}
                </div>
                <div className="stat-label">recommended tests</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">{result.risk_signals.length}</div>
                <div className="stat-label">risk signals</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.release_checklist.length}
                </div>
                <div className="stat-label">checklist items</div>
              </div>
              <div className="stat-card">
                <div className="stat-number">
                  {result.incident_intelligence.total_relevant_incidents}
                </div>
                <div className="stat-label">relevant incidents</div>
              </div>
            </div>
            {result.impact.total_impacted_components === 0 && (
              <p className="muted">
                No other components are impacted by this change.
              </p>
            )}
          </section>

          <section className="card">
            <SectionHeader
              title="Impacted Components"
              hint="Impacted components grouped by type. Click a relationship label on a path to see source evidence."
            />
            <ImpactedGroups impact={result.impact} />
            {result.impact.dependency_paths.length > 0 && (
              <>
                <h3>Dependency paths</h3>
                <ul className="path-list">
                  {result.impact.dependency_paths.map((p, i) => (
                    <li key={i} className="path-item">
                      <div className="muted small">
                        Impacted: <code>{p.impacted}</code>
                      </div>
                      <PathChain path={p} onShowEvidence={setEvidenceEdge} />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <section className="card">
            <SectionHeader
              title="Involved DB2 Resources"
              hint="DB2 tables used by the impacted programs via existing dependency edges. These tables are involved in the change, not impacted by it: they do not depend on the changed component."
            />
            {result.impact.involved_resources.length === 0 ? (
              <p className="muted">No DB2 resources involved in this change.</p>
            ) : (
              <InvolvedResources impact={result.impact} />
            )}
          </section>

          <section className="card">
            <SectionHeader
              title="Recommended Tests"
              hint="Deterministic test selection: tests whose catalog coverage overlaps the impact set."
            />
            {result.recommended_tests.length === 0 ? (
              <p className="muted">
                No tests recommended — the change impacts no components.
              </p>
            ) : (
              <ul className="intel-list">
                {result.recommended_tests.map((t) => (
                  <TestCard
                    key={t.test_id}
                    test={t}
                    onShowEvidence={setEvidenceEdge}
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <SectionHeader
              title="Release-Risk Signals"
              hint="Deterministic risk rules fired against the impact context."
            />
            {result.risk_signals.length === 0 ? (
              <p className="muted">No release-risk signals.</p>
            ) : (
              <ul className="intel-list">
                {result.risk_signals.map((s) => (
                  <SignalCard key={s.id} signal={s} />
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <SectionHeader
              title="Release Checklist"
              hint="Release gates generated by deterministic rules."
            />
            {result.release_checklist.length === 0 ? (
              <p className="muted">
                No checklist items — the change has no blast radius.
              </p>
            ) : (
              <ul className="intel-list">
                {result.release_checklist.map((c) => (
                  <ChecklistCard key={c.id} item={c} />
                ))}
              </ul>
            )}
          </section>

          <IncidentIntelligenceSection
            intel={result.incident_intelligence}
            onShowEvidence={setEvidenceEdge}
          />

          <AiExplanationSection ai={result.ai_explanation} />

          <section className="card">
            <SectionHeader
              title="Evidence"
              hint="Every impact path and risk signal above is grounded in these source references."
            />
            {result.impact.evidence.length === 0 ? (
              <p className="muted">No evidence references.</p>
            ) : (
              <ul className="intel-list">
                {result.impact.evidence.map((e, i) => (
                  <li key={i} className="intel-item">
                    <div className="edge-endpoints">
                      <code>{e.source}</code>
                      <span className="rel-badge">{e.relationship}</span>
                      <code>{e.target}</code>
                    </div>
                    <div className="muted small">
                      <EvidenceRef evidence={e.evidence} /> —{" "}
                      {e.evidence.text}
                    </div>
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
