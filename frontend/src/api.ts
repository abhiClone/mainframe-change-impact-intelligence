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
};

export { API_BASE };
