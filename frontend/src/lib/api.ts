/**
 * The HTTP client.
 *
 * Every screen in SerpFlow talks to the real FastAPI service through this
 * module. There is no mock layer and no fixture data in the frontend: if a
 * number appears on a chart, the server computed it.
 */

import type {
  Alert,
  ApiKey,
  ApiKeyCreated,
  AuditEntry,
  AuditVerify,
  BenchmarkRun,
  BenchmarkTask,
  Budget,
  BudgetOverview,
  CacheDashboard,
  CacheEntry,
  Catalog,
  CatalogEngine,
  CatalogGraph,
  Credential,
  CustomRole,
  Dashboard,
  GuardRejection,
  Health,
  Me,
  Member,
  Page,
  PayloadResponse,
  Plan,
  Project,
  RoleCatalogue,
  Run,
  RunSummary,
  SavingsDecomposition,
  SearchAccepted,
  SearchResponse,
  TokenResponse,
} from "@/types/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

const ACCESS_KEY = "serpflow.access_token";
const REFRESH_KEY = "serpflow.refresh_token";
const PROJECT_KEY = "serpflow.project_id";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;
  readonly details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  /** Section 74: every error is actionable, so the UI can say what to do. */
  get remedy(): string | null {
    switch (this.code) {
      case "BUDGET_EXHAUSTED":
        return "Raise the configured SerpFlow budget in Budgets. This is your own cap, not the upstream SerpApi quota.";
      case "UPSTREAM_QUOTA_EXHAUSTED":
        return "Your SerpApi account is out of searches. Add upstream capacity on serpapi.com.";
      case "NO_UPSTREAM_CREDENTIAL":
        return "Attach a SerpApi credential in Settings, or use a test API key to run against the deterministic mock at zero cost.";
      case "REPLAY_CASSETTE_MISS":
        return "No cassette was recorded for this request. Record one with SERPFLOW_MODE=record, or switch to a test key.";
      case "PERMISSION_DENIED":
        return "Your role does not permit this. An owner or admin can change it in Settings, Members.";
      case "UNAUTHENTICATED":
        return "Sign in again.";
      case "NO_VIABLE_PLAN":
        return "No valid dependency path reaches the engines this intent needs. Try naming the place, product or identifier more specifically.";
      case "RATE_LIMITED":
        return "Too many requests. Wait a moment and try again.";
      default:
        return null;
    }
  }
}

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  set(response: TokenResponse) {
    localStorage.setItem(ACCESS_KEY, response.access_token);
    localStorage.setItem(REFRESH_KEY, response.refresh_token);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const activeProject = {
  get: () => localStorage.getItem(PROJECT_KEY),
  set: (id: string | null) =>
    id ? localStorage.setItem(PROJECT_KEY, id) : localStorage.removeItem(PROJECT_KEY),
};

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const token = tokens.refresh();
  if (!token) return false;
  // One refresh in flight at a time: the server rotates refresh tokens, so two
  // concurrent attempts would invalidate each other.
  refreshing ??= (async () => {
    try {
      const response = await fetch(BASE_URL + "/v1/auth/refresh", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!response.ok) {
        tokens.clear();
        return false;
      }
      tokens.set((await response.json()) as TokenResponse);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Internal: prevents an infinite refresh loop. */
  retry?: boolean;
  /** Provenance headers from the last response, section 45. */
  onHeaders?: (headers: Headers) => void;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, query, retry, onHeaders, ...init } = options;

  let url = BASE_URL + path;
  if (query) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        search.append(key, String(value));
      }
    }
    const encoded = search.toString();
    if (encoded) url += "?" + encoded;
  }

  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (body !== undefined) headers.set("content-type", "application/json");

  const access = tokens.access();
  if (access) headers.set("authorization", "Bearer " + access);

  const project = activeProject.get();
  if (project) headers.set("x-serpflow-project", project);

  const response = await fetch(url, {
    ...init,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  onHeaders?.(response.headers);

  if (response.status === 401 && !retry && tokens.refresh()) {
    if (await refreshSession()) {
      return request<T>(path, { ...options, retry: true });
    }
  }

  if (!response.ok) {
    let code = "HTTP_" + response.status;
    let message = response.statusText || "Request failed.";
    let requestId: string | undefined;
    let details: Record<string, unknown> | undefined;
    try {
      const payload = await response.json();
      if (payload?.error) {
        code = payload.error.code ?? code;
        message = payload.error.message ?? message;
        requestId = payload.error.request_id;
        details = payload.error.details;
      }
    } catch {
      /* a non-JSON body is still an error; keep the status text */
    }
    throw new ApiError(response.status, code, message, requestId, details);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T,>(path: string, query?: RequestOptions["query"]) =>
  request<T>(path, { method: "GET", query });
const post = <T,>(path: string, body?: unknown, query?: RequestOptions["query"]) =>
  request<T>(path, { method: "POST", body, query });
const patch = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "PATCH", body });
const del = <T,>(path: string, query?: RequestOptions["query"]) =>
  request<T>(path, { method: "DELETE", query });

export const api = {
  // ---------------------------------------------------------------- auth
  register: (body: {
    email: string;
    password: string;
    full_name?: string;
    organization_name?: string;
  }) => post<TokenResponse>("/v1/auth/register", body),
  login: (body: { email: string; password: string }) =>
    post<TokenResponse>("/v1/auth/login", body),
  logout: () => post<{ ok: boolean; message: string }>("/v1/auth/logout"),
  me: () => get<Me>("/v1/auth/me"),
  sessions: () => get<{ id: string; user_agent: string; ip: string; created_at: string; expires_at: string }[]>("/v1/auth/sessions"),
  revokeSession: (id: string) => del<{ ok: boolean }>("/v1/auth/sessions/" + id),
  forgotPassword: (email: string) =>
    post<{ ok: boolean; message: string }>("/v1/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) =>
    post<{ ok: boolean; message: string }>("/v1/auth/reset-password", { token, password }),
  verifyEmail: (token: string) =>
    post<{ ok: boolean; message: string }>("/v1/auth/verify-email", { token }),

  // ------------------------------------------------------- organization
  organization: () => get<{ id: string; name: string; slug: string; cache_scope: string }>("/v1/organizations/current"),
  updateOrganization: (body: Record<string, unknown>) =>
    patch<Record<string, unknown>>("/v1/organizations/current", body),
  projects: () => get<Project[]>("/v1/projects"),
  createProject: (body: { name: string; description?: string }) =>
    post<Project>("/v1/projects", body),
  updateProject: (id: string, body: Partial<Project>) =>
    patch<Project>("/v1/projects/" + id, body),
  members: () => get<Member[]>("/v1/members"),
  inviteMember: (body: { email: string; role: string }) => post<Member>("/v1/members", body),
  updateMember: (id: string, role: string) => patch<Member>("/v1/members/" + id, { role }),
  removeMember: (id: string) => del<{ ok: boolean }>("/v1/members/" + id),

  // ------------------------------------------------------------- keys
  keys: (query?: { project_id?: string; limit?: number; offset?: number }) =>
    get<Page<ApiKey>>("/v1/keys", query),
  createKey: (
    projectId: string,
    body: {
      name: string;
      environment: string;
      role: string;
      expires_in_days?: number | null;
      is_service_principal?: boolean;
      session_cap?: number | null;
    },
  ) => post<ApiKeyCreated>("/v1/projects/" + projectId + "/keys", body),
  rotateKey: (id: string, graceMinutes = 60) =>
    post<ApiKeyCreated>("/v1/keys/" + id + "/rotate", { grace_minutes: graceMinutes }),
  revokeKey: (id: string, reason?: string) =>
    del<{ ok: boolean; message: string }>("/v1/keys/" + id, { reason }),

  // ------------------------------------------------------ credentials
  credentials: () => get<Credential[]>("/v1/credentials"),
  createCredential: (body: {
    name: string;
    api_key: string;
    project_id?: string | null;
    set_as_org_default?: boolean;
    validate_now?: boolean;
  }) => post<Credential>("/v1/credentials", body),
  validateCredential: (id: string) =>
    post<Credential>("/v1/credentials/" + id + "/validate"),
  rotateCredential: (id: string, apiKey: string, graceMinutes = 15) =>
    post<Credential>("/v1/credentials/" + id + "/rotate", {
      api_key: apiKey,
      grace_minutes: graceMinutes,
    }),
  revokeCredential: (id: string) =>
    del<{ ok: boolean; message: string }>("/v1/credentials/" + id),
  reconcileQuota: () => post<{ ok: boolean; message: string }>("/v1/credentials/reconcile-quota"),
  revalidateCredentials: () =>
    post<{ ok: boolean; message: string }>("/v1/credentials/revalidate"),

  // ------------------------------------------------- planning and runs
  plan: (body: { intent: string; budget?: number | null; project_id?: string | null }) =>
    post<Plan>("/v1/plan", body),
  search: (
    body: { intent: string; budget?: number | null; project_id?: string | null },
    onHeaders?: (headers: Headers) => void,
  ) => request<SearchResponse>("/v1/search", { method: "POST", body, onHeaders }),
  startStreamingSearch: (body: {
    intent: string;
    budget?: number | null;
    project_id?: string | null;
  }) => post<SearchAccepted>("/v1/search", { ...body, stream: true }),
  runs: (query?: {
    limit?: number;
    offset?: number;
    project_id?: string;
    status?: string;
    engine?: string;
    changed_selection?: boolean;
  }) => get<Page<RunSummary>>("/v1/runs", query),
  run: (id: string) => get<Run>("/v1/runs/" + id),
  runPlan: (id: string) => get<Plan>("/v1/runs/" + id + "/plan"),
  stepPayload: (runId: string, stepId: string) =>
    get<PayloadResponse>("/v1/runs/" + runId + "/steps/" + stepId + "/payload"),
  replay: (id: string) => post<SearchResponse>("/v1/runs/" + id + "/replay"),
  reportFalseHit: (
    id: string,
    body: { step_id?: string | null; note?: string; invalidate_entry?: boolean },
  ) => post<{ ok: boolean; message: string }>("/v1/runs/" + id + "/report-false-hit", body),

  // ---------------------------------------------------------- catalog
  catalog: (query?: { version?: string; tag?: string; search?: string }) =>
    get<Catalog>("/v1/catalog", query),
  catalogVersions: () =>
    get<{ versions: Record<string, unknown>[]; active: string }>("/v1/catalog/versions"),
  catalogEngine: (engine: string) => get<CatalogEngine>("/v1/catalog/engines/" + engine),
  catalogPaths: (engine: string, params = "q,location") =>
    get<{
      engine: string;
      catalog_version: string;
      available_params: string[];
      path_count: number;
      paths: Record<string, unknown>[];
    }>("/v1/catalog/engines/" + engine + "/paths", { params }),
  catalogTags: () =>
    get<{
      catalog_version: string;
      tags: { tag: string; description: string; engines: string[]; competing: boolean }[];
    }>("/v1/catalog/tags"),
  catalogGraph: () => get<CatalogGraph>("/v1/catalog/graph"),

  // ------------------------------------------------------------ cache
  cacheDashboard: (days = 30) => get<CacheDashboard>("/v1/cache", { days }),
  cacheEntries: (query?: {
    engine?: string;
    project_id?: string;
    limit?: number;
    offset?: number;
  }) => get<Page<CacheEntry>>("/v1/cache/entries", query),
  guardRejections: (query?: { limit?: number; offset?: number }) =>
    get<Page<GuardRejection>>("/v1/cache/guard-rejections", query),
  invalidateCache: (body: { engine?: string | null; entry_id?: string | null }) =>
    post<{ ok: boolean; message: string }>("/v1/cache/invalidate", body),

  // ---------------------------------------------------------- budgets
  budgets: () => get<BudgetOverview>("/v1/budgets"),
  createBudget: (body: Record<string, unknown>) => post<Budget>("/v1/budgets", body),
  updateBudget: (id: string, body: Record<string, unknown>) =>
    patch<Budget>("/v1/budgets/" + id, body),
  deleteBudget: (id: string) => del<{ ok: boolean }>("/v1/budgets/" + id),

  // -------------------------------------------------------- analytics
  dashboard: (days = 30) => get<Dashboard>("/v1/analytics/dashboard", { days }),
  savings: (days = 30) => get<SavingsDecomposition>("/v1/analytics/savings", { days }),
  attribution: (days = 30) =>
    get<{ window_days: number; rows: Record<string, unknown>[] }>(
      "/v1/analytics/attribution",
      { days },
    ),
  routingQuality: () =>
    get<{
      benchmarks: { catalog_version: string; systems: Record<string, BenchmarkRun> }[];
      live: {
        plans: number;
        mean_confidence: number;
        mean_candidate_count: number;
        rejected_alternatives: number;
      };
    }>("/v1/analytics/routing"),
  volatility: (days = 90) =>
    get<{
      window_days: number;
      by_engine_class: Record<string, unknown>[];
      ttl_movement: Record<string, number>;
    }>("/v1/analytics/volatility", { days }),
  engineReach: () =>
    get<{
      catalog_engines: number;
      engines_used: number;
      reach_ratio: number;
      usage: { engine: string; calls: number }[];
    }>("/v1/analytics/engine-reach"),
  crossProject: () => get<Dashboard["cross_project_benefit"]>("/v1/analytics/cross-project"),

  // ------------------------------------------------------- benchmarks
  benchmarks: (catalogVersion?: string) =>
    get<BenchmarkRun[]>("/v1/benchmarks", { catalog_version: catalogVersion }),
  benchmarkTasks: (query?: { category?: string; limit?: number; offset?: number }) =>
    get<Page<BenchmarkTask>>("/v1/benchmarks/tasks", query),
  benchmarkEvals: (runId: string) =>
    get<Record<string, unknown>[]>("/v1/benchmarks/" + runId + "/evals"),
  runBenchmark: (body: { system: string; suite_version?: string; limit?: number | null }) =>
    post<BenchmarkRun>("/v1/benchmarks/run", body),

  // ------------------------------------------------------------ audit
  audit: (query?: { limit?: number; offset?: number; action?: string; actor_id?: string }) =>
    get<Page<AuditEntry>>("/v1/audit", query),
  verifyAudit: () => get<AuditVerify>("/v1/audit/verify"),
  exportAudit: (limit = 5000) =>
    get<{ org_id: string; count: number; entries: AuditEntry[] }>("/v1/audit/export", {
      limit,
    }),

  // ----------------------------------------------------------- alerts
  alerts: (query?: { status?: string; limit?: number; offset?: number }) =>
    get<Page<Alert>>("/v1/alerts", query),
  updateAlert: (id: string, status: string) => patch<Alert>("/v1/alerts/" + id, { status }),
  channels: () => get<Record<string, unknown>[]>("/v1/notification-channels"),
  createChannel: (body: Record<string, unknown>) =>
    post<Record<string, unknown>>("/v1/notification-channels", body),
  deleteChannel: (id: string) => del<{ ok: boolean }>("/v1/notification-channels/" + id),

  // ------------------------------------------------------------ roles
  roles: () => get<{ items: CustomRole[]; total: number }>("/v1/roles"),
  rolePermissions: () => get<RoleCatalogue>("/v1/roles/permissions"),
  createRole: (body: {
    name: string;
    permissions: string[];
    description?: string;
    slug?: string;
  }) => post<CustomRole>("/v1/roles", body),
  updateRole: (
    id: string,
    body: { name?: string; description?: string; permissions?: string[] },
  ) => patch<CustomRole>("/v1/roles/" + id, body),
  deleteRole: (id: string) => del<{ ok: boolean }>("/v1/roles/" + id),

  // --------------------------------------------------- infrastructure
  health: () => get<Health>("/readyz"),
};
