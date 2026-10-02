/**
 * SerpFlow TypeScript SDK (section 59).
 *
 *   import { SerpFlow } from "@serpflow/sdk";
 *
 *   const client = new SerpFlow({ apiKey: "sf_test_..." });
 *   const result = await client.search("review rings among Koramangala cafes");
 *   console.log(result.plan.marginalCost, "credits on the margin");
 *
 * Three verbs mirror the service layer: route (plan only, no credits), run and
 * search (plan with replanning, then execute). `SerpApiCompat` is the drop-in:
 * change only the base URL and existing SerpApi code routes through SerpFlow.
 *
 * No runtime dependencies. Uses fetch and ReadableStream, so it runs in Node 18+,
 * Deno, Bun and the browser.
 */

export interface SerpFlowOptions {
  apiKey: string;
  baseUrl?: string;
  projectId?: string;
  fetch?: typeof globalThis.fetch;
}

export interface PlanStep {
  index: number;
  engine: string;
  fan_out: number;
  freshness_requirement: string;
  warm: boolean;
  cache_state?: Record<string, unknown>;
}

export interface PlanView {
  id: string;
  intent: string;
  engines: string[];
  steps: PlanStep[];
  naiveCost: number;
  marginalCost: number;
  savings: number;
  candidateCount: number;
  confidence: number;
  catalogVersion: string;
  /** The thesis, persisted: did marginal re-ranking change the answer? */
  changedSelection: boolean;
  explanation?: string | null;
  warmSteps: Record<string, unknown>[];
  rejectedAlternatives: Record<string, unknown>[];
  budgetReduction?: Record<string, unknown> | null;
  projectedFullScaleCost?: number | null;
  raw: Record<string, unknown>;
}

export interface SearchResult {
  runId: string;
  status: string;
  /** LIVE, MOCK, REPLAY or RECORD. Never present replayed data as live. */
  mode: string;
  creditsSpent: number;
  creditsSaved: number;
  plan: PlanView;
  results: Record<string, unknown>;
  items: Record<string, unknown>[];
  raw: Record<string, unknown>;
}

export interface RunEvent {
  stage: string;
  status: string;
  elapsedMs: number;
  detail: Record<string, unknown>;
  type: "stage" | "complete" | "error" | "heartbeat";
}

export class SerpFlowError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;

  constructor(code: string, message: string, status = 0, requestId?: string) {
    super(message);
    this.name = "SerpFlowError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }

  /** What the caller should actually do about it. */
  get remedy(): string | null {
    switch (this.code) {
      case "BUDGET_EXHAUSTED":
        return "Raise the configured SerpFlow budget. This is your own cap, not the SerpApi account quota.";
      case "UPSTREAM_QUOTA_EXHAUSTED":
        return "The SerpApi account is out of searches. Add upstream capacity.";
      case "NO_UPSTREAM_CREDENTIAL":
        return "Attach a SerpApi credential, or use a test API key to run against the deterministic mock.";
      case "REPLAY_CASSETTE_MISS":
        return "No cassette was recorded for this request. Record one with SERPFLOW_MODE=record.";
      default:
        return null;
    }
  }
}

function toPlan(payload: Record<string, any>): PlanView {
  return {
    id: payload.id,
    intent: payload.intent,
    engines: (payload.steps ?? []).map((step: PlanStep) => step.engine),
    steps: payload.steps ?? [],
    naiveCost: payload.naive_cost,
    marginalCost: payload.marginal_cost,
    savings: payload.savings ?? Math.max(0, payload.naive_cost - payload.marginal_cost),
    candidateCount: payload.candidate_count ?? 0,
    confidence: payload.confidence ?? 0,
    catalogVersion: payload.catalog_version ?? "",
    changedSelection: Boolean(payload.marginal_replan_changed_selection),
    explanation: payload.replan_explanation,
    warmSteps: payload.warm_steps ?? [],
    rejectedAlternatives: payload.rejected_alternatives ?? [],
    budgetReduction: payload.budget_reduction,
    projectedFullScaleCost: payload.projected_full_scale_cost,
    raw: payload,
  };
}

function toResult(payload: Record<string, any>): SearchResult {
  return {
    runId: payload.run.id,
    status: payload.run.status,
    mode: payload.mode.label,
    creditsSpent: payload.run.credits_spent,
    creditsSaved: payload.run.credits_saved,
    plan: toPlan(payload.plan),
    results: payload.results ?? {},
    items: payload.results?.summary?.items ?? [],
    raw: payload,
  };
}

export class SerpFlow {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly projectId?: string;
  private readonly doFetch: typeof globalThis.fetch;

  constructor(options: SerpFlowOptions) {
    if (!options.apiKey) {
      throw new Error(
        "No API key. A test key routes to the deterministic mock and consumes zero SerpApi credits.",
      );
    }
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.projectId = options.projectId;
    this.doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = {
      "X-API-Key": this.apiKey,
      "content-type": "application/json",
      accept: "application/json",
    };
    if (this.projectId) headers["X-SerpFlow-Project"] = this.projectId;
    return headers;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.doFetch(this.baseUrl + path, {
      ...init,
      headers: { ...this.headers(), ...(init.headers as Record<string, string>) },
    });
    if (!response.ok) {
      let code = "HTTP_" + response.status;
      let message = response.statusText;
      let requestId: string | undefined;
      try {
        const body = await response.json();
        code = body?.error?.code ?? code;
        message = body?.error?.message ?? message;
        requestId = body?.error?.request_id;
      } catch {
        /* a non-JSON body is still an error */
      }
      throw new SerpFlowError(code, message, response.status, requestId);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  /** Plan without executing. Calls a language model, not SerpApi: zero credits. */
  async route(intent: string, budget?: number): Promise<PlanView> {
    const payload = await this.request<Record<string, any>>("/v1/plan", {
      method: "POST",
      body: JSON.stringify({ intent, budget, project_id: this.projectId }),
    });
    return toPlan(payload);
  }

  plan = this.route;

  /** Plan with cache-aware replanning, then execute. */
  async search(intent: string, budget?: number): Promise<SearchResult> {
    const payload = await this.request<Record<string, any>>("/v1/search", {
      method: "POST",
      body: JSON.stringify({ intent, budget, project_id: this.projectId }),
    });
    return toResult(payload);
  }

  run = this.search;

  /**
   * Start a search and yield each real backend stage transition.
   *
   * Every frame corresponds to a stage the planner or executor actually
   * completed; there is no timer anywhere in this path.
   */
  async *stream(intent: string, budget?: number): AsyncGenerator<RunEvent> {
    const accepted = await this.request<{ run_id: string }>("/v1/search", {
      method: "POST",
      body: JSON.stringify({ intent, budget, project_id: this.projectId, stream: true }),
    });

    const response = await this.doFetch(
      this.baseUrl + "/v1/runs/" + accepted.run_id + "/stream",
      { headers: { ...this.headers(), accept: "text/event-stream" } },
    );
    if (!response.body) return;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf("\n");
        if (!line.startsWith("data:")) continue;

        const payload = JSON.parse(line.slice(5).trim());
        if (payload.type === "heartbeat") continue;
        yield {
          stage: payload.stage,
          status: payload.status,
          elapsedMs: payload.elapsed_ms,
          detail: payload.detail ?? {},
          type: payload.type ?? "stage",
        };
        if (payload.type === "complete" || payload.type === "error") {
          await reader.cancel();
          return;
        }
      }
    }
  }

  async getRun(runId: string): Promise<Record<string, unknown>> {
    return this.request("/v1/runs/" + runId);
  }

  /** Which plans were considered, and why the selected one won. */
  async explain(runId: string): Promise<Record<string, unknown>> {
    const run = (await this.getRun(runId)) as Record<string, any>;
    const plan = run.plan ?? {};
    return {
      runId,
      intent: run.intent,
      selected: (plan.steps ?? []).map((step: PlanStep) => step.engine),
      naiveCost: plan.naive_cost,
      marginalCost: plan.marginal_cost,
      changedSelection: plan.marginal_replan_changed_selection,
      explanation: plan.replan_explanation,
      candidates: plan.candidates ?? [],
      rejectedAlternatives: plan.rejected_alternatives ?? [],
    };
  }

  async replay(runId: string): Promise<SearchResult> {
    const payload = await this.request<Record<string, any>>(
      "/v1/runs/" + runId + "/replay",
      { method: "POST" },
    );
    return toResult(payload);
  }

  async runs(limit = 25): Promise<Record<string, unknown>[]> {
    const page = await this.request<{ items: Record<string, unknown>[] }>(
      "/v1/runs?limit=" + limit,
    );
    return page.items;
  }

  async catalog(engine?: string): Promise<Record<string, unknown>> {
    return this.request("/v1/catalog" + (engine ? "/engines/" + engine : ""));
  }

  async budgets(): Promise<Record<string, unknown>> {
    return this.request("/v1/budgets");
  }

  async health(): Promise<Record<string, unknown>> {
    return this.request("/readyz");
  }
}

/**
 * SerpApi-compatible drop-in.
 *
 *   const search = new SerpApiCompat({ engine: "google", q: "coffee", api_key: "sf_test_..." });
 *   const results = await search.getJson();
 *
 * Existing SerpApi code keeps its shape; the request now goes through
 * SerpFlow's cache layers and budget enforcement. It does not re-route: you
 * asked for an engine, you get that engine. Adopt `SerpFlow.search` when you
 * want routing as well.
 */
export class SerpApiCompat {
  private readonly params: Record<string, unknown>;
  private readonly client: SerpFlow;
  private readonly engine: string;

  constructor(params: Record<string, unknown> & { api_key?: string }, baseUrl?: string) {
    const { api_key: apiKey, ...rest } = params;
    this.params = rest;
    this.engine = String(rest.engine ?? "google");
    this.client = new SerpFlow({ apiKey: String(apiKey ?? ""), baseUrl });
  }

  async getJson(): Promise<Record<string, unknown>> {
    const query = String(this.params.q ?? this.params.query ?? "");
    const result = await this.client.search(query);
    return {
      ...result.results,
      search_metadata: {
        id: result.runId,
        status: result.status === "succeeded" ? "Success" : "Error",
        engine: this.engine,
        serpflow_mode: result.mode,
        serpflow_credits_spent: result.creditsSpent,
        serpflow_credits_saved: result.creditsSaved,
      },
      search_parameters: { engine: this.engine, ...this.params },
    };
  }
}

export default SerpFlow;
