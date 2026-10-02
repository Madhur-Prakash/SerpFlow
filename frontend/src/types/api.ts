/**
 * Types mirroring the FastAPI schemas in backend/app/schemas.
 *
 * Note what is absent: there is no field anywhere below that could carry an
 * upstream SerpApi secret, because no response model on the server has one.
 */

export type Role = "owner" | "admin" | "developer" | "analyst" | "service";
export type KeyEnvironment = "live" | "test";
export type Freshness = "realtime" | "fresh" | "recent" | "stable";
export type CacheLayer =
  | "exact"
  | "semantic"
  | "archive"
  | "live"
  | "mock"
  | "replay"
  | "miss"
  | "skipped";
export type Coverage = "full" | "partial" | "narrow";
export type ExecutionMode = "LIVE" | "MOCK" | "REPLAY" | "RECORD";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ModeInfo {
  mode: string;
  label: ExecutionMode;
  reason: string;
  credited: boolean;
}

// -------------------------------------------------------------- identity
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  expires_at: string;
  session_id: string;
  org_id: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  last_login_at?: string | null;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan_tier: string;
  cache_scope: "project" | "organization";
  default_credential_id?: string | null;
  created_at: string;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  description: string;
  key_prefix: string;
  credential_id?: string | null;
  engine_allowlist: string[];
  engine_denylist: string[];
  semantic_threshold?: number | null;
  ttl_overrides: Record<string, number>;
  retention_days?: number | null;
  retention_high_pii_days?: number | null;
  shared_cache_enabled: boolean;
  created_at: string;
}

export interface Me {
  user?: User | null;
  principal_type: string;
  org_id: string;
  project_id?: string | null;
  role: Role;
  permissions: string[];
  organization?: Organization | null;
  projects: Project[];
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  accepted_at?: string | null;
  created_at: string;
}

export interface ApiKey {
  id: string;
  project_id: string;
  name: string;
  environment: KeyEnvironment;
  project_prefix: string;
  display: string;
  role: Role;
  is_service_principal: boolean;
  session_cap?: number | null;
  last_used_at?: string | null;
  last_used_ip?: string | null;
  use_count: number;
  expires_at?: string | null;
  revoked_at?: string | null;
  rotation_grace_until?: string | null;
  created_at: string;
}

export interface ApiKeyCreated {
  key: ApiKey;
  plaintext: string;
  warning: string;
}

/** The secret is structurally absent. See backend section 25. */
export interface Credential {
  id: string;
  name: string;
  provider: string;
  project_id?: string | null;
  fingerprint: string;
  display: string;
  kek_id: string;
  algo: string;
  validation_status: string;
  validation_error?: string | null;
  last_validated_at?: string | null;
  created_at: string;
  rotated_at?: string | null;
  revoked_at?: string | null;
  upstream_plan?: string | null;
  upstream_searches_left?: number | null;
  upstream_checked_at?: string | null;
}

// -------------------------------------------------------------- planning
export interface Binding {
  param: string;
  source: "root" | "chain";
  from_engine?: string | null;
  from_step?: number | null;
  from_field?: string | null;
}

export interface CacheState {
  layer: string;
  available: boolean;
  acceptable: boolean;
  warm: boolean;
  freshness_requirement: string;
  age_seconds?: number | null;
  ttl_remaining?: number | null;
  ttl_source?: string | null;
  similarity?: number | null;
  matched_query?: string | null;
  reason: string;
  guard_rejections: number;
  step?: number;
  engine?: string;
}

export interface PlanStep {
  index: number;
  engine: string;
  label: string;
  depends_on: number[];
  fan_out: number;
  cost: number;
  pii_risk: string;
  bindings: Binding[];
  parameters: Record<string, unknown>;
  freshness_requirement: Freshness;
  warm: boolean;
  cache_state: CacheState;
}

export interface WarmStep {
  index: number;
  engine: string;
  layer?: string | null;
  age_seconds?: number | null;
  credits_avoided: number;
  reason?: string | null;
}

export interface BudgetReductionItem {
  type: "sampling" | "fan_out_cap" | "omitted_step";
  step: number;
  engine: string;
  original: number;
  reduced: number;
  impact_note: string;
}

export interface BudgetReduction {
  applied: boolean;
  reductions: BudgetReductionItem[];
  full_plan_cost: number;
  selected_plan_cost: number;
  note: string;
}

export interface RejectedAlternative {
  plan: string;
  label: string;
  strategy: string;
  engines: string[];
  coverage: Coverage;
  naive_cost: number;
  marginal_cost: number;
  naive_rank: number;
  marginal_rank: number;
  warm_steps: number[];
  reason?: string | null;
  trade_off_note?: string | null;
  feasible_within_budget: boolean;
  role?: string;
  uncapped_naive_cost?: number;
  reductions?: BudgetReductionItem[];
}

export interface RejectedEngine {
  engine: string;
  reason: string;
  score?: number | null;
  hallucinated?: boolean;
}

export interface PlanCandidate {
  id: string;
  label: string;
  strategy: string;
  engines: string[];
  hops: number;
  naive_cost: number;
  marginal_cost: number;
  warm_step_indices: number[];
  cache_state: CacheState[];
  coverage: Coverage;
  confidence: number;
  naive_rank: number;
  marginal_rank: number;
  selected: boolean;
  feasible_within_budget: boolean;
  rejection_reason?: string | null;
  trade_off_note?: string | null;
  steps: Record<string, unknown>[];
}

export interface FreshnessRequirement {
  engine: string;
  step: number;
  requirement: Freshness;
  signals: string[];
}

export interface StageTraceEvent {
  stage: string;
  status: string;
  elapsed_ms: number;
  detail: Record<string, unknown>;
}

export interface Plan {
  id: string;
  org_id: string;
  project_id: string;
  intent: string;
  normalized_intent: string;
  steps: PlanStep[];
  parameter_bindings: Record<string, unknown>;
  naive_cost: number;
  marginal_cost: number;
  projected_full_scale_cost?: number | null;
  savings: number;
  warm_steps: WarmStep[];
  freshness_requirements: FreshnessRequirement[];
  budget_reduction?: BudgetReduction | null;
  confidence: number;
  catalog_version: string;
  candidate_count: number;
  single_candidate_reason?: string | null;
  rejected_alternatives: RejectedAlternative[];
  rejected_engines: RejectedEngine[];
  candidates: PlanCandidate[];
  cold_winner_candidate_id?: string | null;
  /** The thesis, persisted. */
  marginal_replan_changed_selection: boolean;
  replan_explanation?: string | null;
  budget_limit?: number | null;
  planner_latency_ms: number;
  mode: string;
  stage_trace: StageTraceEvent[];
  created_at: string;
}

export interface Step {
  id: string;
  index: number;
  engine: string;
  label: string;
  parameters: Record<string, unknown>;
  depends_on: number[];
  fan_out: number;
  status: string;
  cache_layer?: CacheLayer | null;
  matched_query?: string | null;
  similarity?: number | null;
  age_seconds?: number | null;
  ttl_source?: string | null;
  freshness_requirement: Freshness;
  credits: number;
  latency_ms: number;
  confidence: number;
  payload_ref?: string | null;
  payload_bytes?: number | null;
  serpapi_search_id?: string | null;
  http_status?: number | null;
  mode: string;
  pii_risk: string;
  error_code?: string | null;
  error_message?: string | null;
  extracted: Record<string, unknown>;
}

export interface RunSummary {
  id: string;
  project_id: string;
  plan_id?: string | null;
  intent: string;
  status: string;
  trigger: string;
  credits_spent: number;
  credits_saved: number;
  naive_cost: number;
  marginal_cost: number;
  mode: string;
  duration_ms: number;
  error_code?: string | null;
  created_at: string;
}

export interface Run extends RunSummary {
  principal_id?: string | null;
  principal_type: string;
  cache_summary: Record<string, number>;
  provenance: Record<string, unknown>;
  result_summary: ResultSummary;
  results_ref?: string | null;
  error_message?: string | null;
  trace_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  replay_of_run_id?: string | null;
  expires_at?: string | null;
  max_pii_risk: string;
  steps: Step[];
  plan?: Plan | null;
}

export interface ResultItem {
  title?: string | null;
  link?: string | null;
  rating?: number | null;
  price?: string | null;
  snippet?: string | null;
  date?: string | null;
  source?: string | null;
}

export interface ResultSummary {
  result_key?: string | null;
  count: number;
  items: ResultItem[];
}

export interface SearchResponse {
  run: Run;
  plan: Plan;
  results: { summary?: ResultSummary; [key: string]: unknown };
  mode: ModeInfo;
  provenance: Record<string, unknown>;
}

export interface SearchAccepted {
  run_id: string;
  stream_url: string;
  mode: ModeInfo;
  status: string;
}

export interface PayloadResponse {
  step_id: string;
  engine: string;
  payload_ref: string;
  payload: Record<string, unknown>;
  pii_risk: string;
  mode: string;
}

// -------------------------------------------------------------- catalog
export interface Substitute {
  engine: string;
  coverage: Coverage;
  note: string;
  shared_tags: string[];
}

export interface CatalogEngine {
  engine: string;
  purpose: string;
  capability_tags: string[];
  substitutes: Substitute[];
  single_source_note: string;
  requires: Record<string, { type: string; description?: string; satisfied_by: string[] }>;
  optional: string[];
  produces: Record<string, { type: string; feeds: string[]; fan_out_hint: number }>;
  cost: number;
  latency_class: string;
  volatility_prior: string;
  locale_sensitive: string[];
  pii_risk: string;
  docs_url: string;
  depends_on: string[];
  dependents: string[];
}

export interface CatalogEdge {
  from_engine: string;
  to_engine: string;
  produces_field: string;
  satisfies_param: string;
  param_type: string;
  fan_out_hint: number;
}

export interface Catalog {
  version: string;
  released: string;
  source: string;
  notes: string;
  engine_count: number;
  edge_count: number;
  substitute_count: number;
  capability_tags: Record<string, string>;
  engines: CatalogEngine[];
  edges: CatalogEdge[];
  substitute_edges: {
    engine: string;
    substitute_engine: string;
    coverage: Coverage;
    note: string;
    shared_tags: string[];
  }[];
}

export interface CatalogGraph {
  catalog_version: string;
  nodes: {
    id: string;
    purpose: string;
    tags: string[];
    cost: number;
    pii_risk: string;
    volatility_prior: string;
    latency_class: string;
    in_degree: number;
    out_degree: number;
  }[];
  dependency_edges: {
    source: string;
    target: string;
    param: string;
    field: string;
    fan_out_hint: number;
    kind: "dependency";
  }[];
  substitute_edges: {
    source: string;
    target: string;
    coverage: Coverage;
    note: string;
    kind: "substitute";
  }[];
}

// -------------------------------------------------------------- governance
export interface Budget {
  id: string;
  org_id: string;
  scope: "organization" | "project" | "api_key" | "session";
  scope_id: string;
  name: string;
  limit_credits: number;
  current_usage: number;
  remaining: number;
  utilization: number;
  period: "daily" | "weekly" | "monthly" | "total";
  period_started_at?: string | null;
  period_ends_at?: string | null;
  alert_at: number;
  on_exhausted: "stale" | "error" | "queue";
  enabled: boolean;
  created_at: string;
}

export interface UpstreamQuota {
  credential_id: string;
  name: string;
  fingerprint: string;
  upstream_plan?: string | null;
  upstream_searches_left?: number | null;
  upstream_checked_at?: string | null;
  divergence?: number | null;
  internal_spend_since_last?: number | null;
  upstream_spend_since_last?: number | null;
}

export interface BudgetOverview {
  budgets: Budget[];
  credits_spent_total: number;
  credits_saved_total: number;
  projected_exhaustion?: {
    budget_id: string;
    scope: string;
    remaining: number;
    burn_rate_per_hour: number;
    exhausts_at?: string | null;
    hours_remaining?: number;
    period_ends_at?: string | null;
    note?: string;
  } | null;
  upstream_quota: UpstreamQuota[];
}

export interface Dashboard {
  window_days: number;
  credits_spent: number;
  credits_saved: number;
  savings_ratio: number;
  cache_hit_rate: number;
  cache_layers: Record<string, number>;
  runs: Record<string, number>;
  spend_by_project: {
    project_id: string;
    project_name: string;
    spent: number;
    saved: number;
  }[];
  recent_runs: RunSummary[];
  active_alerts: Alert[];
  upstream_quota: UpstreamQuota[];
  projected_exhaustion?: BudgetOverview["projected_exhaustion"];
  cross_project_benefit: {
    total_credits: number;
    flows: {
      fetching_project_id: string;
      fetching_project_name: string;
      beneficiary_project_id: string;
      beneficiary_project_name: string;
      credits: number;
    }[];
  };
  marginal_replanning: {
    plans_total: number;
    selection_changed: number;
    selection_changed_ratio: number;
  };
}

export interface SavingsDecomposition {
  window_days: number;
  naive_execution: number;
  actual_spend: number;
  total_saved: number;
  by_source: Record<string, number>;
  waterfall: { label: string; value: number; kind: string }[];
}

export interface CacheEntry {
  id: string;
  project_id: string;
  partition_key: string;
  engine: string;
  gl: string;
  hl: string;
  location: string;
  query_text: string;
  request_hash: string;
  numerals: string[];
  entities: string[];
  versions: string[];
  result_count: number;
  payload_bytes: number;
  credits_cost: number;
  ttl_seconds: number;
  ttl_source: string;
  expires_at: string;
  hit_count: number;
  refresh_count: number;
  last_hit_at?: string | null;
  pii_risk: string;
  mode: string;
  invalidated_at?: string | null;
  created_at: string;
}

export interface GuardRejection {
  id: string;
  engine: string;
  incoming_query: string;
  candidate_query: string;
  similarity: number;
  reason: string;
  incoming_tokens: string[];
  candidate_tokens: string[];
  created_at: string;
}

export interface CacheDashboard {
  window_days: number;
  layers: Record<string, number>;
  hit_rate: number;
  entries: number;
  bytes_stored: number;
  partitions: { partition_key: string; entries: number }[];
  guard_rejections: { total: number; by_reason: Record<string, number> };
  false_hit_reports: number;
  by_engine: { engine: string; entries: number; hits: number; mean_ttl_seconds: number }[];
  redis: Record<string, unknown>;
}

export interface BenchmarkRun {
  id: string;
  suite_version: string;
  catalog_version: string;
  system: string;
  llm_model: string;
  task_count: number;
  correct_count: number;
  accuracy: number;
  engine_accuracy: number;
  param_accuracy: number;
  freshness_accuracy: number;
  mean_confidence: number;
  mean_latency_ms: number;
  by_category: Record<string, { total: number; correct: number; accuracy: number }>;
  failure_modes: Record<string, number>;
  notes: string;
  created_at: string;
  finished_at?: string | null;
}

export interface BenchmarkTask {
  id: string;
  task_key: string;
  suite_version: string;
  intent: string;
  expected_engines: string[];
  acceptable_alternatives: string[][];
  expected_params: Record<string, string>;
  expected_freshness?: string | null;
  category: string;
  difficulty: string;
  notes: string;
}

export interface AuditEntry {
  id: string;
  sequence: number;
  actor_id?: string | null;
  actor_type: string;
  actor_label: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  project_id?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  ip: string;
  request_id?: string | null;
  prev_hash: string;
  entry_hash: string;
  created_at: string;
}

export interface AuditVerify {
  valid: boolean;
  entries_checked: number;
  break_at_sequence?: number | null;
  reason?: string | null;
  head?: string | null;
}

export interface Alert {
  id: string;
  project_id?: string | null;
  kind: string;
  severity: string;
  title: string;
  message: string;
  status: string;
  context: Record<string, unknown>;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface Health {
  status: "ok" | "degraded" | "error";
  service: string;
  version: string;
  environment: string;
  mode: string;
  catalog_version: string;
  checks: Record<string, unknown>;
  timestamp: string;
}

// -------------------------------------------------------------- streaming
/** One SSE frame from GET /v1/runs/{id}/stream. */
export interface RunEvent {
  stage: string;
  status: string;
  elapsed_ms: number;
  detail: Record<string, unknown>;
  sequence: number;
  run_id: string;
  type: "stage" | "complete" | "error" | "heartbeat";
}


// --------------------------------------------------------------- roles
/** A role an owner defined, with the permission set they chose. */
export type CustomRole = {
  id: string;
  name: string;
  slug: string;
  description: string;
  permissions: string[];
  assigned_count: number;
  created_at: string;
  updated_at: string;
};

export type PermissionView = {
  value: string;
  /** What this permission lets someone do, in plain words. */
  label: string;
  group: string;
};

export type RoleCatalogue = {
  permissions: PermissionView[];
  groups: string[];
  builtin: { slug: string; name: string; permissions: string[]; builtin: boolean }[];
};
