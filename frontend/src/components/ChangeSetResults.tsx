/* Reusable rendering of a Phase 3A ChangeSetIntelligence result.
 *
 * Extracted verbatim from ChangeSetView: the Changed Components,
 * downstream impact, overlap, resources, tests, risks, checklist,
 * incidents, deterministic summary and AI explanation sections are
 * identical wherever a change set is analyzed — including the Phase 3B
 * GitHub pull-request view, which reuses the frozen Phase 3A engine.
 * The component invents nothing; every number and label comes from the
 * backend result it receives.
 */
import {
  type AggregatedIncident,
  type AggregatedTest,
  type ChangeRootRef,
  type ChangeSetIntelligence,
  type ImpactedComponentEntry,
  type MappingStatus,
  type SnapshotKind,
} from "../api";

const AI_UNAVAILABLE_PREFIX = "AI explanation unavailable.";

export function VerifiedChangeSetBadge() {
  return <span className="prov-badge prov-verified">VERIFIED CHANGE SET</span>;
}

function DeterministicSummaryBadge() {
  return <span className="prov-badge prov-det">DETERMINISTIC SUMMARY</span>;
}

function ProvenanceBadge({ ai }: { ai?: boolean }) {
  return ai ? (
    <span className="prov-badge prov-ai">AI EXPLANATION</span>
  ) : (
    <span className="prov-badge prov-verified">VERIFIED IMPACT</span>
  );
}

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

function MappingLabel({ status }: { status: MappingStatus }) {
  const cls =
    status === "mapped"
      ? "prov-verified"
      : status === "ambiguous"
        ? "prov-ai"
        : "prov-det";
  return <span className={`prov-badge ${cls}`}>{status}</span>;
}

function RootsLine({ label, roots }: { label: string; roots: string[] }) {
  return (
    <p className="muted small prov-line">
      {label}:{" "}
      {roots.map((r, i) => (
        <span key={r}>
          {i > 0 && ", "}
          <code>{r}</code>
        </span>
      ))}
    </p>
  );
}

function SnapshotBadge({ snapshot }: { snapshot: SnapshotKind }) {
  return (
    <span className={`prov-badge ${snapshot === "base" ? "prov-base" : "prov-head"}`}>
      {snapshot}
    </span>
  );
}

function RootRefsLine({
  label,
  refs,
}: {
  label: string;
  refs: ChangeRootRef[];
}) {
  return (
    <p className="muted small prov-line">
      {label}:{" "}
      {refs.map((r, i) => (
        <span key={`${r.change_root}:${r.snapshot}`}>
          {i > 0 && ", "}
          <code>{r.change_root}</code> <SnapshotBadge snapshot={r.snapshot} />
        </span>
      ))}
    </p>
  );
}

export default function ChangeSetResults({
  intel,
}: {
  intel: ChangeSetIntelligence;
}) {
  const ai = intel.ai_explanation;
  const aiFallback = !!ai && ai.scope_summary.startsWith(AI_UNAVAILABLE_PREFIX);

  return (
    <div className="intel-results">
      <section className="card">
        <SectionHeader
          title="Release Summary"
          badge={<DeterministicSummaryBadge />}
        />
        <div className="stat-grid">
          <div className="stat-card">
            <div className="stat-number">{intel.summary.changed_files}</div>
            <div className="stat-label">changed files</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.changed_components}
            </div>
            <div className="stat-label">changed components</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.cross_impacted_changed_components}
            </div>
            <div className="stat-label">changed also impacted</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.unique_impacted_components}
            </div>
            <div className="stat-label">downstream impacted</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.overlap_impacted_components}
            </div>
            <div className="stat-label">overlap impacted</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.unique_recommended_tests}
            </div>
            <div className="stat-label">tests recommended</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">
              {intel.summary.relevant_incidents}
            </div>
            <div className="stat-label">relevant incidents</div>
          </div>
        </div>
        <p>{intel.deterministic_summary}</p>
        {intel.mixed_snapshot_analysis && (
          <p className="muted small">
            Mixed-snapshot release: some evidence comes from the base tree
            (deletions, rename-away identities) and some from the head tree.
            Per-root snapshots are shown on every section.
          </p>
        )}
      </section>

      <section className="card">
        <SectionHeader
          title="Changed Components"
          badge={<VerifiedChangeSetBadge />}
          hint="The explicit change roots: components the changed files map to. Changed roots never appear under downstream impact; when one changed root is downstream-impacted by another, that cross-impact is shown here, never hidden."
        />
        <ul className="id-list">
          {intel.changed_components.map((c) => (
            <li key={c.component_id}>
              <code>{c.component_id}</code>{" "}
              <SnapshotBadge snapshot={c.snapshot} />
              <p className="muted small prov-line">
                from:{" "}
                {c.originating_files.map((f, i) => (
                  <span key={f}>
                    {i > 0 && ", "}
                    <code>{f}</code>
                  </span>
                ))}
              </p>
              {c.previous_component_ids.length > 0 && (
                <p className="muted small prov-line">
                  rename identity — base:{" "}
                  {c.previous_component_ids.map((id, i) => (
                    <span key={id}>
                      {i > 0 && ", "}
                      <code>{id}</code>
                    </span>
                  ))}{" "}
                  → head: <code>{c.component_id}</code>
                </p>
              )}
              {c.also_impacted_by.length > 0 && (
                <RootRefsLine
                  label="also downstream-impacted by"
                  refs={c.also_impacted_by}
                />
              )}
            </li>
          ))}
          {intel.changed_components.length === 0 && (
            <li className="muted">No mapped changed components.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Changed Files & Mapping"
          badge={<VerifiedChangeSetBadge />}
          hint="Deterministic file → component mapping from Phase 1 metadata. Ambiguous files list every candidate and select nothing; unmapped files stay visible but create no impact."
        />
        <ul className="id-list">
          {intel.mapped_changes.map((m) => (
            <li key={m.file.path}>
              <code>{m.file.path}</code>{" "}
              <span className="muted small">({m.file.status})</span>{" "}
              <MappingLabel status={m.mapping_status} />{" "}
              <SnapshotBadge snapshot={m.snapshot} /> →{" "}
              {m.component_ids.map((c) => (
                <code key={c}>{c}</code>
              ))}
              {m.file.status === "renamed" &&
                m.previous_component_ids.length > 0 && (
                  <p className="muted small prov-line">
                    rename: <code>{m.file.old_path}</code> (
                    {m.previous_component_ids.join(", ")}, base) →{" "}
                    <code>{m.file.path}</code> (
                    {m.current_component_ids.join(", ")}, head)
                  </p>
                )}
            </li>
          ))}
          {intel.ambiguous_changes.map((m) => (
            <li key={m.file.path}>
              <code>{m.file.path}</code>{" "}
              <MappingLabel status={m.mapping_status} />
              <p className="muted small">
                Candidates (no component chosen automatically):
              </p>
              <ul className="id-list">
                {m.candidate_components.map((c) => (
                  <li key={c}>
                    <code>{c}</code>
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {intel.unmapped_changes.map((m) => (
            <li key={m.file.path}>
              <code>{m.file.path}</code>{" "}
              <MappingLabel status={m.mapping_status} />{" "}
              <span className="muted small">
                not a Mainframe component — no impact
              </span>
            </li>
          ))}
          {intel.unresolved_changes.map((m) => (
            <li key={m.file.path}>
              <code>{m.file.path}</code>{" "}
              <MappingLabel status={m.mapping_status} />{" "}
              <span className="muted small">{m.note}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Downstream Impacted Components"
          badge={<ProvenanceBadge />}
          hint="Deduplicated union of every change root's downstream impact. Changed roots are excluded here by definition — see Changed Components for cross-impact between changed roots. Roots stay visible — nothing is collapsed into a synthetic release component."
        />
        <ul className="id-list">
          {intel.unique_impacted_components.map(
            (e: ImpactedComponentEntry) => (
              <li key={e.component_id}>
                <code>{e.component_id}</code>
                <RootsLine label="impacted because of" roots={e.impacted_by} />
                <ul className="id-list">
                  {e.per_root.map((pr) => (
                    <li key={pr.change_root} className="muted small">
                      <code>{pr.change_root}</code>{" "}
                      <SnapshotBadge snapshot={pr.snapshot} /> — depth {pr.depth}
                    </li>
                  ))}
                </ul>
              </li>
            )
          )}
          {intel.unique_impacted_components.length === 0 && (
            <li className="muted">
              No downstream impacted components — the change set is quiet.
            </li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Impact Overlap"
          badge={<ProvenanceBadge />}
          hint="Components at the intersection of several changes. Overlap is reported, never auto-labelled high risk."
        />
        {intel.impacted_by_multiple_changes.length > 0 ? (
          <ul className="id-list">
            {intel.impacted_by_multiple_changes.map((id) => {
              const entry = intel.unique_impacted_components.find(
                (e) => e.component_id === id
              );
              return (
                <li key={id}>
                  <code>{id}</code>
                  {entry && (
                    <RootsLine
                      label="impacted because of"
                      roots={entry.impacted_by}
                    />
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted">
            No component is impacted by more than one change.
          </p>
        )}
      </section>

      <section className="card">
        <SectionHeader
          title="Involved DB2 Resources"
          badge={<ProvenanceBadge />}
          hint="Tables used by impacted programs. Involved ≠ impacted: these tables do not depend on the change. Read and write stay distinct."
        />
        <ul className="id-list">
          {intel.involved_resources.map((r) => (
            <li key={`${r.table}:${r.access}`}>
              <span className={`rel-badge ${r.access}`}>
                {r.access.toUpperCase()}
              </span>{" "}
              <code>{r.table}</code>
              <RootRefsLine
                label="associated changes"
                refs={r.associated_change_roots}
              />
            </li>
          ))}
          {intel.involved_resources.length === 0 && (
            <li className="muted">No DB2 resources involved.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Recommended Tests"
          badge={<ProvenanceBadge />}
          hint="Deduplicated by test id. Strongest deterministic priority wins (MUST_RUN > SHOULD_RUN); every original per-change reason is preserved."
        />
        <ul className="id-list">
          {intel.recommended_tests.map((t: AggregatedTest) => (
            <li key={t.test_id}>
              <span
                className={`rel-badge ${t.impact_level === "MUST_RUN" ? "write" : "read"}`}
              >
                {t.impact_level}
              </span>{" "}
              <code>{t.test_id}</code> {t.test_name}
              <RootRefsLine
                label="recommended because of"
                refs={t.recommended_because_of}
              />
              <ul className="id-list">
                {t.per_root.map((pr) => (
                  <li key={pr.change_root} className="muted small">
                    <code>{pr.change_root}</code>{" "}
                    <SnapshotBadge snapshot={pr.snapshot} /> → {pr.impact_level}
                    : {pr.rationale}
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {intel.recommended_tests.length === 0 && (
            <li className="muted">No tests recommended.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Risk Signals"
          badge={<ProvenanceBadge />}
          hint="Deduplicated by signal id with per-change provenance. Severities stay rule-based."
        />
        <ul className="id-list">
          {intel.risk_signals.map((s) => (
            <li key={s.id}>
              <span className="count-badge">{s.severity}</span>{" "}
              <strong>{s.id}</strong> — {s.title}
              <RootRefsLine label="triggered for changes" refs={s.change_roots} />
            </li>
          ))}
          {intel.risk_signals.length === 0 && (
            <li className="muted">No risk signals.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Release Checklist"
          badge={<ProvenanceBadge />}
          hint="Deduplicated by rule id; applicable change roots preserved."
        />
        <ul className="id-list">
          {intel.release_checklist.map((c) => (
            <li key={c.id}>
              <code>{c.id}</code> — {c.title}
              <RootRefsLine
                label="applies to changes"
                refs={c.applicable_change_roots}
              />
            </li>
          ))}
          {intel.release_checklist.length === 0 && (
            <li className="muted">No checklist items.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <SectionHeader
          title="Historical Incidents"
          badge={<ProvenanceBadge />}
          hint="Deduplicated by incident id. Historical severity ≠ current relevance; per-change reasons stay inspectable."
        />
        <ul className="id-list">
          {intel.relevant_incidents.map((a: AggregatedIncident) => (
            <li key={a.incident.id}>
              <code>{a.incident.id}</code>{" "}
              <span className="count-badge">{a.incident.severity}</span>{" "}
              {a.incident.title}
              <RootRefsLine label="relevant to" refs={a.relevant_to_changes} />
              <ul className="id-list">
                {a.per_change.map((pc) => (
                  <li key={pc.change_root} className="muted small">
                    <code>{pc.change_root}</code>{" "}
                    <SnapshotBadge snapshot={pc.snapshot} /> — primary reason:{" "}
                    {pc.primary_reason}; matched:{" "}
                    {pc.matched_components.join(", ") || "—"}
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {intel.relevant_incidents.length === 0 && (
            <li className="muted">
              No historical incidents deterministically relevant.
            </li>
          )}
        </ul>
      </section>

      {ai && (
        <section className="card">
          <SectionHeader
            title="AI Release Explanation"
            badge={<ProvenanceBadge ai={!aiFallback} />}
            hint={
              aiFallback
                ? "AI provider unavailable — deterministic summary shown."
                : "Grounded summary of the computed release result only. The AI cannot add components, impact, tests, risks, or incidents."
            }
          />
          <p>
            <strong>Scope.</strong> {ai.scope_summary}
          </p>
          <p>
            <strong>Impact.</strong> {ai.impact_summary}
          </p>
          <p>
            <strong>Testing.</strong> {ai.testing_summary}
          </p>
          <p>
            <strong>Release considerations.</strong> {ai.release_considerations}
          </p>
          <p>
            <strong>History.</strong> {ai.incident_summary}
          </p>
          <p>
            <strong>Overlap.</strong> {ai.overlap_notes}
          </p>
        </section>
      )}
    </div>
  );
}
