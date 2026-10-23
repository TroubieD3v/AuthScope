export type Access = "public" | "authenticated" | "owner" | "tenant" | "roles";
export type Verdict = "pass" | "violation" | "needs_review" | "inconclusive" | "skipped" | "error";
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface AuthConfig {
  type: "bearer" | "header" | "cookie" | "query" | "basic" | "none";
  header_name: string; cookie_name: string; query_name: string; username: string | null;
}
export interface LoginConfig { method: string; path: string; body: Record<string, unknown>; token_path: string }
export interface Identity {
  name: string; role: string; tenant: string | null; description?: string | null;
  auth: AuthConfig; token_env: string | null;
  login?: LoginConfig | null; password_env?: string | null;
  has_secret?: boolean; secret_source?: "none" | "runtime" | "env" | "login" | "missing";
  password_source?: "runtime" | "env" | "missing" | null;
}
export interface Resource {
  type: string; id: string; owner: string | null; tenant: string | null; id_field: string; label?: string | null; parent?: string | null;
}
export interface RestrictedField { name: string; roles: string[]; owner_can_see: boolean }
export interface Endpoint {
  method: string; path: string; summary?: string | null; tags: string[]; access: Access;
  allow_roles: string[]; resource_type: string | null; path_param: string | null; list_of: string | null;
  param_types: Record<string, string>;
  restricted_fields: RestrictedField[]; params: Record<string, string>; query: Record<string, string>;
  body: unknown; enabled: boolean; source: "openapi" | "postman" | "manual"; inferred: boolean;
}
export interface Target {
  base_url: string; allowed_hosts: string[]; rate_limit_rps: number; max_requests: number; timeout_s: number;
  concurrency: number; max_redirects: number; allow_mutating: boolean; acknowledge_no_reset: boolean;
  reset: { method: string; path: string; identity: string | null } | null; verify_tls: boolean;
}
export interface Override { endpoint: string; identity: string; resource: string | null; expected: "allow" | "deny" }
export interface Project {
  id: string; name: string; target: Target; identities: Identity[]; resources: Resource[];
  endpoints: Endpoint[]; overrides: Override[]; tests: unknown[];
}
export interface ProjectSummary { id: string; name: string; base_url: string; endpoints: number; updated_at: string }

export interface RunStats {
  total: number; done: number; requests: number;
  by_verdict: Record<string, number>; by_module: Record<string, Record<string, number>>;
}
export interface Run {
  id: string; project_id: string; status: "queued" | "running" | "completed" | "cancelled" | "failed";
  modules: string[]; started_at: string; finished_at: string | null; error: string | null;
  stats: RunStats; extra: { warnings?: string[] };
}
export interface Exchange {
  label: string; identity: string | null; method: string; url: string;
  request_headers: Record<string, string>; request_body: string | null; status: number | null;
  response_headers: Record<string, string>; response_body: string | null; elapsed_ms: number; error: string | null;
}
export interface Evidence {
  baseline: Exchange | null; test: Exchange | null; diff: string[]; expected: string; observed: string;
  reproduction: string[];
}
export interface CheckResult {
  id: string; module: string; name: string; endpoint_key: string; identity: string | null;
  resource: string | null; variant: string | null; expected: "allow" | "deny" | null; observed: string;
  verdict: Verdict; severity: Severity; message: string; evidence?: Evidence | null;
}
export interface MatrixCell {
  expected: "allow" | "deny" | "conditional" | "off"; overridden: boolean;
  actual: Record<string, number>; worst: Verdict | null;
}
export interface Matrix {
  identities: { name: string; role: string; tenant: string | null }[];
  rows: { endpoint: string; method: string; path: string; access: Access; enabled: boolean; inferred: boolean; cells: Record<string, MatrixCell> }[];
  run_id: string | null;
}
export interface Dashboard {
  endpoints: number; identities: number; resources: number; latest_run: Run | null;
  verdicts: Record<string, number>; severities: Record<string, number>;
  modules: Record<string, Record<string, number>>;
  history: { id: string; status: string; started_at: string; violations: number; review: number; passed: number }[];
}
export interface ModuleInfo { name: string; title: string; description: string }

export class ApiError extends Error {}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      const d = j.detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((e: { loc: string[]; msg: string }) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ") : msg;
    } catch { /* keep default message */ }
    throw new ApiError(msg);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const p = (id: string) => `/api/projects/${id}`;
export const api = {
  projects: () => req<ProjectSummary[]>("GET", "/api/projects"),
  project: (id: string) => req<Project>("GET", p(id)),
  createProject: (cfg: unknown) => req<Project>("POST", "/api/projects", cfg),
  createDemo: (base_url: string) => req<Project>("POST", "/api/projects/demo", { base_url }),
  importYaml: (content: string) => req<Project>("POST", "/api/projects/import-yaml", { content }),
  saveProject: (id: string, cfg: Omit<Project, "id">) => req<Project>("PUT", p(id), cfg),
  deleteProject: (id: string) => req<void>("DELETE", p(id)),
  importSpec: (id: string, body: { url?: string; content?: string; replace?: boolean }) =>
    req<{ added: number; updated: number; total: number; title: string | null; format: string; warnings: string[] }>("POST", `${p(id)}/import`, body),
  putEndpoint: (id: string, ep: Endpoint) => req<Endpoint>("PUT", `${p(id)}/endpoints`, ep),
  deleteEndpoint: (id: string, key: string) => req<void>("DELETE", `${p(id)}/endpoints?key=${encodeURIComponent(key)}`),
  putIdentity: (id: string, i: Partial<Identity>) => req<Project>("PUT", `${p(id)}/identities`, i),
  deleteIdentity: (id: string, name: string) => req<void>("DELETE", `${p(id)}/identities/${encodeURIComponent(name)}`),
  setSecret: (id: string, name: string, token: string, kind: "token" | "password" = "token") =>
    req<void>("PUT", `${p(id)}/identities/${encodeURIComponent(name)}/secret?kind=${kind}`, { token }),
  clearSecret: (id: string, name: string) => req<void>("DELETE", `${p(id)}/identities/${encodeURIComponent(name)}/secret`),
  putResources: (id: string, r: Resource[]) => req<Resource[]>("PUT", `${p(id)}/resources`, r),
  putOverride: (id: string, o: Override, clear = false) => req<Override[]>("PUT", `${p(id)}/overrides?clear=${clear}`, o),
  matrix: (id: string, runId?: string) => req<Matrix>("GET", `${p(id)}/matrix${runId ? `?run_id=${runId}` : ""}`),
  dashboard: (id: string) => req<Dashboard>("GET", `${p(id)}/dashboard`),
  modules: () => req<{ modules: ModuleInfo[]; roadmap: { name: string; title: string }[] }>("GET", "/api/modules"),
  startRun: (id: string, modules: string[]) => req<Run>("POST", `${p(id)}/runs`, { modules }),
  runs: (id: string) => req<Run[]>("GET", `${p(id)}/runs`),
  run: (rid: string) => req<Run>("GET", `/api/runs/${rid}`),
  cancelRun: (rid: string) => req<{ cancelling: boolean }>("POST", `/api/runs/${rid}/cancel`),
  results: (rid: string, only: "all" | "findings" = "findings") => req<CheckResult[]>("GET", `/api/runs/${rid}/results?only=${only}`),
  result: (rid: string, resultId: string) => req<CheckResult>("GET", `/api/runs/${rid}/results/${resultId}`),
  diff: (rid: string, against: string) =>
    req<{ new: CheckResult[]; fixed: CheckResult[]; unchanged: CheckResult[] }>("GET", `/api/runs/${rid}/diff?against=${against}`),
  reportUrl: (rid: string, format: string, download = true) => `/api/runs/${rid}/report?format=${format}${download ? "&download=true" : ""}`,
  exportYamlUrl: (id: string) => `${p(id)}/export.yaml`,
};
