/* API client for the local FastAPI backend (Phase 1 Change Impact engine).
 * All dependency data shown in the UI comes from these endpoints; nothing is
 * invented client-side. Every dependency carries source evidence.
 */

const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";

export type ComponentType =
  | "COBOL_PROGRAM"
  | "COPYBOOK"
  | "JCL_JOB"
  | "JCL_PROC"
  | "DB2_TABLE";

export interface Component {
  id: string;
  name: string;
  type: ComponentType;
  source_file: string;
}

export interface Evidence {
  file: string;
  line: number;
  text: string;
}

export interface Dependency {
  source: string; // the dependent: source DEPENDS ON target
  target: string; // the thing depended on
  relationship: string; // CALLS | USES_COPYBOOK | READS_TABLE | WRITES_TABLE | EXECUTES_PROGRAM | USES_PROC
  evidence: Evidence;
}

export interface Summary {
  COBOL_PROGRAM: number;
  COPYBOOK: number;
  JCL_JOB: number;
  JCL_PROC: number;
  DB2_TABLE: number;
  DEPENDENCIES: number;
}

export interface GraphData {
  nodes: Component[];
  edges: Dependency[];
}

export interface ComponentDetail {
  component: Component;
  upstream: Dependency[]; // edges this component depends on (source == this component)
  downstream: Dependency[]; // edges of components depending on this one (target == this component)
}

export interface ImpactPathStep {
  from: string; // the depended-on side (closer to the changed component)
  to: string; // the dependent side ("to" depends on "from")
  relationship: string;
  evidence: Evidence;
}

export interface ImpactPath {
  impacted: string;
  path: ImpactPathStep[];
}

export interface ImpactEvidenceEdge {
  source: string;
  target: string;
  relationship: string;
  evidence: Evidence;
}

export interface ImpactResult {
  changed_component: string;
  direct_impact: string[];
  transitive_impact: string[];
  dependency_paths: ImpactPath[];
  evidence: ImpactEvidenceEdge[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/* ------------------------------------------------------------------ */
/* Phase 2A — Release Intelligence (deterministic impact context +      */
/* optional grounded AI explanation). All numbers, tests, signals,     */
/* checklist items and explanation text come from the API; the client  */
/* invents nothing.                                                    */
/* ------------------------------------------------------------------ */

export interface IntelligencePathStep {
  source: string; // the dependent: source DEPENDS ON target
  target: string; // the thing depended on
  relationship: string;
  evidence: Evidence;
}

export interface IntelligencePath {
  impacted: string;
  path: IntelligencePathStep[];
}

export interface IntelligenceEdge {
  source: string;
  target: string;
  relationship: string;
  evidence: Evidence;
}

export interface InvolvedResource {
  table: string;
  access: "read" | "write"; // mirrors READS_TABLE / WRITES_TABLE
  used_by: string[]; // impacted program ids holding this edge
  evidence: Evidence[];
}

export interface IntelligenceImpact {
  changed_component: string;
  changed_component_type: ComponentType;
  direct_impacts: string[];
  transitive_impacts: string[];
  dependency_paths: IntelligencePath[];
  relationships: string[];
  evidence: IntelligenceEdge[];
  affected_programs: string[];
  affected_copybooks: string[];
  affected_jobs: string[];
  affected_procs: string[];
  affected_tables: string[];
  // Involved (not impacted) DB2 resources: tables used by impacted programs
  // via existing Phase 1 edges. A table here does NOT depend on the change.
  read_tables: string[];
  write_tables: string[];
  involved_resources: InvolvedResource[];
  maximum_impact_depth: number;
  total_impacted_components: number;
}

export type TestImpactLevel = "MUST_RUN" | "SHOULD_RUN";

export interface RecommendedTest {
  test_id: string;
  test_name: string;
  test_type: string;
  matched_components: string[];
  impact_level: TestImpactLevel;
  dependency_paths: IntelligencePath[];
  rationale: string; // machine-generated from matched components + paths
  evidence: Evidence[];
}

export type RiskSeverity = "low" | "medium" | "high";

export interface RiskSignal {
  id: string;
  severity: RiskSeverity;
  title: string;
  explanation: string;
  triggered_by: string[];
  supporting_components: string[];
  evidence: Evidence[];
}

export interface ReleaseChecklistItem {
  id: string;
  title: string;
  detail: string;
  rule: string; // deterministic rule that produced this item
  related_components: string[];
}

export type ExplanationSource = "deterministic" | "ai";

export interface AiExplanation {
  subject_component: string;
  explanation_source: ExplanationSource;
  executive_summary: string;
  technical_summary: string;
  testing_summary: string;
  release_considerations: string;
  // Phase 2B: incident sections — summarize ONLY deterministically
  // selected relevant incidents; never new selection.
  incident_summary: string;
  historical_patterns: string;
  release_history_considerations: string;
}

export interface HistoricalIncident {
  id: string;
  title: string;
  occurred_at: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "open" | "investigating" | "resolved";
  summary: string;
  symptoms: string[];
  linked_components: string[];
  failure_mode: string;
  root_cause_category: string;
  root_cause_summary: string;
  resolution_summary: string;
}

export type RelevanceReasonType =
  | "CHANGED_COMPONENT_MATCH"
  | "DIRECT_IMPACT_MATCH"
  | "TRANSITIVE_IMPACT_MATCH"
  | "INVOLVED_WRITE_RESOURCE_MATCH"
  | "INVOLVED_READ_RESOURCE_MATCH";

export interface RelevanceReason {
  reason: RelevanceReasonType;
  matched_component: string;
  explanation: string; // deterministic template prose
  supporting_paths: IntelligencePath[];
  evidence: Evidence[];
}

export interface RelevantIncident {
  incident: HistoricalIncident;
  primary_reason: RelevanceReasonType;
  relevance_reasons: RelevanceReason[]; // all reasons, precedence order
  matched_components: string[];
  supporting_resources: InvolvedResource[];
}

export interface IncidentIntelligence {
  changed_component: string;
  relevant_incidents: RelevantIncident[];
  total_relevant_incidents: number;
  // Incidents counted by PRIMARY relevance tier; sums to the total.
  primary_tier_counts: Record<string, number>;
  // Every valid relevance reason counted; may exceed the total because
  // one incident can carry several reasons.
  reason_counts: Record<string, number>;
}

export interface IntelligenceResult {
  changed_component: string;
  impact: IntelligenceImpact;
  recommended_tests: RecommendedTest[];
  risk_signals: RiskSignal[];
  release_checklist: ReleaseChecklistItem[];
  incident_intelligence: IncidentIntelligence; // Phase 2B additive layer
  ai_explanation: AiExplanation;
}

export interface TestCatalogEntry {
  id: string;
  name: string;
  type: string;
  covers: string[];
  execution: Record<string, string>;
  description: string;
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new Error(
      `Cannot reach the API at ${API_BASE}. Start the backend with: ` +
        `.venv/bin/python -m uvicorn backend.api.app:app --port 8000`
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? "";
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const api = {
  summary: () => get<Summary>("/api/summary"),
  components: () => get<Component[]>("/api/components"),
  dependencies: () => get<Dependency[]>("/api/dependencies"),
  graph: () => get<GraphData>("/api/graph"),
  component: (id: string) =>
    get<ComponentDetail>(`/api/component/${encodeURIComponent(id)}`),
  impact: (id: string) =>
    get<ImpactResult>(`/api/impact/${encodeURIComponent(id)}`),
  intelligence: (id: string) =>
    get<IntelligenceResult>(`/api/intelligence/${encodeURIComponent(id)}`),
  testCatalog: () => get<TestCatalogEntry[]>("/api/test-catalog"),
  incidents: () => get<HistoricalIncident[]>("/api/incidents"),
  incident: (id: string) =>
    get<HistoricalIncident>(`/api/incidents/${encodeURIComponent(id)}`),
  incidentIntelligence: (id: string) =>
    get<IncidentIntelligence>(
      `/api/incident-intelligence/${encodeURIComponent(id)}`
    ),
};

export { API_BASE };
