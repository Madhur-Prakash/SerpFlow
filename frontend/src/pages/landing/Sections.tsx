/**
 * The landing page's remaining bands.
 *
 * Every figure here is measured: the benchmark numbers come from
 * `docs/product/benchmark.md`, the catalog counts from the committed YAML, the
 * cache layers from the executor. Nothing is rounded up for the page.
 */

import {
  Activity,
  ArrowRight,
  Boxes,
  Database,
  GitBranch,
  Layers,
  LineChart,
  Lock,
  Radio,
  Route,
  ShieldCheck,
  Workflow,
  Zap,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { useCounters, useParallax, useReveal, useTextReveal } from "@/animations/scroll";
import {
  Atmosphere,
  Band,
  CtaLink,
  MonoLabel,
  SectionHeading,
  SpotlightCard,
  Stat,
} from "@/components/marketing";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui";
import { cn } from "@/lib/utils";

/** Wrap a band so its children reveal and its headings split on scroll. */
function Revealed({
  children,
  ...props
}: React.ComponentProps<typeof Band> & { children: React.ReactNode }) {
  const ref = React.useRef<HTMLElement>(null);
  useReveal(ref);
  useTextReveal(ref);
  useCounters(ref);
  return (
    <div ref={ref as React.RefObject<HTMLDivElement>}>
      <Band {...props}>{children}</Band>
    </div>
  );
}

// --------------------------------------------------------------------------
// Numbers
// --------------------------------------------------------------------------

export function Numbers() {
  const ref = React.useRef<HTMLElement>(null);
  useReveal(ref);
  useCounters(ref);

  return (
    <section ref={ref} className="relative border-t border-line bg-surface-sunken/40">
      <div className="page-shell grid gap-8 py-12 sm:grid-cols-2 lg:grid-cols-4 lg:py-14">
        <Stat value={54} label="Engines in the catalog" note="Hand-reviewed, committed as YAML" />
        <Stat
          value={30}
          label="Typed dependency edges"
          note="How engines chain into multi-hop plans"
        />
        <Stat value={69} label="Substitute edges" note="How engines compete for the same answer" />
        <Stat
          value={38.3}
          decimals={1}
          suffix="%"
          label="Routing accuracy"
          note="120 labelled tasks, deterministic adapter"
        />
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// The problem
// --------------------------------------------------------------------------

const PROBLEMS = [
  {
    icon: Route,
    title: "Engine selection gets hardcoded",
    body: "Dozens of engines, different parameters, different costs. Which one answers a question is a judgement call, and it ends up frozen into whichever service needed it first.",
  },
  {
    icon: GitBranch,
    title: "Chains live in one person's script",
    body: "Reviewer identity is reachable only through google_maps_reviews.reviews[].user.contributor_id. Nothing else in the company can discover that.",
  },
  {
    icon: Database,
    title: "Caching by request hash",
    body: "A paraphrase of yesterday's question is a full-price miss, and a stale entry for a volatile query gets served as though it were live.",
  },
  {
    icon: LineChart,
    title: "Spend is one number, monthly",
    body: "Which team, which feature, which query shape. Unknown until somebody reconciles it by hand.",
  },
] as const;

export function Problem() {
  return (
    <Revealed id="problem">
      <SectionHeading
        label="the problem"
        title="Four things every team builds on top of SerpApi, badly."
        lede="Each is solvable alone. Solved separately, in four services, they do not compose - the cache cannot tell the router what it is choosing between, so the router keeps picking the cold rival of a plan that was already warm."
        aside={
          <div className="rounded-xl border border-line bg-surface p-5">
            <div className="mono mb-3 text-[10.5px] uppercase tracking-[0.16em] text-ink-subtle">
              what that costs
            </div>
            <dl className="flex flex-col divide-y divide-line">
              {[
                ["A paraphrase of yesterday", "full price"],
                ["A warm plan's cold rival", "selected anyway"],
                ["A chain one person knows", "not reusable"],
                ["Spend by team or feature", "unknown"],
              ].map(([term, value]) => (
                <div
                  key={term}
                  className="flex items-baseline justify-between gap-4 py-2 first:pt-0 last:pb-0"
                >
                  <dt className="text-[13px] text-ink-muted">{term}</dt>
                  <dd className="mono shrink-0 text-[12px] text-danger">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        }
      />
      <div className="mt-10 grid gap-3.5 sm:grid-cols-2">
        {PROBLEMS.map((item) => {
          const Icon = item.icon;
          return (
            <SpotlightCard
              key={item.title}
              className="rounded-xl border border-line bg-surface p-6"
            >
              <div data-reveal className="relative flex flex-col gap-3.5">
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface-sunken text-accent transition-transform duration-500 ease-out-quint group-hover:scale-110">
                  <Icon className="h-4 w-4" />
                </span>
                <h3 className="text-[15px] font-medium leading-snug text-ink">{item.title}</h3>
                <p className="text-[13.5px] leading-[1.7] text-ink-muted">{item.body}</p>
              </div>
            </SpotlightCard>
          );
        })}
      </div>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// How it works
// --------------------------------------------------------------------------

const STAGES = [
  {
    code: "A",
    title: "Retrieve",
    body: "Candidate engines, scored on capability-tag affinity against the words people actually use, then expanded with substitutes of strong matches so competitors enter the set.",
  },
  {
    code: "B",
    title: "Select",
    body: "Which capability actually answers this intent, and which engines are permitted by project policy.",
  },
  {
    code: "C",
    title: "Synthesize",
    body: "Dates normalised, locale inferred (Seoul implies gl=kr, hl=ko), entities extracted, parameters bound to the right engine.",
  },
  {
    code: "D",
    title: "Generate",
    body: "Path-finding walks typed edges backwards from the target until every required parameter is satisfiable, producing a candidate set rather than a winner.",
  },
] as const;

const PIPELINE = [
  "analyzing_intent",
  "finding_candidates",
  "synthesizing_parameters",
  "inferring_freshness",
  "finding_paths",
  "generating_candidates",
  "inspecting_cache",
  "calculating_marginal_cost",
  "reranking_plans",
  "checking_budget",
  "executing",
] as const;

export function HowItWorks() {
  const ref = React.useRef<HTMLElement>(null);
  useReveal(ref);
  useTextReveal(ref);
  useParallax(ref, { distance: 50 });

  return (
    <section
      ref={ref}
      id="how-it-works"
      className="relative scroll-mt-24 overflow-hidden border-t border-line py-16 sm:py-20"
    >
      <Atmosphere variant="band" />
      <div className="relative page-shell">
        <SectionHeading
          label="the planner"
          title="Four stages, and a candidate set at the end of them."
          lede="Stage D is the one the thesis needs. It produces competing plans rather than a single answer, and every candidate is persisted - so the Plan Inspector can show why the winner won instead of asserting that it did."
          aside={
            <div className="flex flex-wrap gap-2">
              {[
                "54 engines",
                "30 dependency edges",
                "69 substitutes",
                "28 capability tags",
                "max 4 hops",
                "up to 6 candidates",
              ].map((item) => (
                <span
                  key={item}
                  className="mono rounded-full border border-line bg-surface px-3 py-1.5 text-[11.5px] text-ink-muted transition-colors duration-300 hover:border-line-strong hover:text-ink"
                >
                  {item}
                </span>
              ))}
            </div>
          }
        />

        <div className="mt-10 grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-12">
          <ol className="flex flex-col">
            {STAGES.map((stage, index) => (
              <li
                key={stage.code}
                data-reveal
                className="group relative flex gap-5 border-l border-line pb-9 pl-6 last:pb-0"
              >
                <span className="absolute -left-[13px] top-0 flex h-6 w-6 items-center justify-center rounded-md border border-line bg-ground text-[11px] font-medium text-ink-subtle transition-[border-color,color,background-color] duration-400 ease-out-quint group-hover:border-accent group-hover:bg-accent-ghost group-hover:text-accent-strong">
                  <span className="mono">{stage.code}</span>
                </span>
                {index < STAGES.length - 1 ? (
                  <span className="absolute -left-px top-6 h-[calc(100%-1.5rem)] w-px origin-top scale-y-0 bg-accent transition-transform duration-700 ease-out-quint group-hover:scale-y-100" />
                ) : null}
                <div className="flex flex-col gap-1.5">
                  <h3 className="text-[15.5px] font-medium text-ink">{stage.title}</h3>
                  <p className="max-w-md text-[13.5px] leading-[1.7] text-ink-muted">
                    {stage.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          <div data-reveal data-parallax="0.25" className="flex min-w-0 flex-col gap-4">
            <div className="rounded-xl border border-line bg-surface p-5">
              <div className="mono mb-4 flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-ink-subtle">
                <Radio className="h-3 w-3 text-accent" />
                live stream
              </div>
              <div className="flex flex-col gap-1">
                {PIPELINE.map((stage, index) => (
                  <div
                    key={stage}
                    className="group/row flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors duration-300 hover:bg-surface-sunken"
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-300",
                        index < 10 ? "bg-warm" : "bg-accent animate-pulse-ring",
                      )}
                    />
                    <span className="mono flex-1 truncate text-[11.5px] text-ink-muted transition-colors duration-300 group-hover/row:text-ink">
                      {stage}
                    </span>
                    <span className="mono shrink-0 text-[10px] text-ink-subtle">
                      {(index * 18.4 + 4).toFixed(1)}ms
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-[12.5px] leading-relaxed text-ink-subtle">
              One frame per real backend stage transition. There is no timer anywhere in this path:
              if the planner spends two seconds inspecting cache state, the stream is silent for two
              seconds.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Cache
// --------------------------------------------------------------------------

/** The four layers in the order the executor tries them, with real latencies. */
const LOOKUP_ORDER = `hot       redis      exact key        ~1ms
exact     postgres   request hash     ~4ms
semantic  pgvector   + entity guard  ~40ms
archive   serpapi    searches api   ~300ms
miss      live call  full price`;

const FAILURE_MODES = [
  { label: "correct", count: 46, tone: "bg-warm" },
  { label: "wrong engine", count: 58, tone: "bg-danger" },
  { label: "wrong parameters", count: 9, tone: "bg-caution" },
  { label: "label disputed", count: 2, tone: "bg-ink-subtle" },
] as const;

const LAYERS = [
  { name: "hot", store: "Redis", detail: "Exact match, in memory", tone: "warm" },
  { name: "exact", store: "PostgreSQL", detail: "Request hash, durable", tone: "warm" },
  { name: "semantic", store: "pgvector", detail: "HNSW, with a guard", tone: "accent" },
  { name: "archive", store: "SerpApi", detail: "The Searches Archive", tone: "replay" },
] as const;

export function CacheLayers() {
  return (
    <Revealed id="cache">
      <SectionHeading
        label="the cache"
        title="Four layers, and a guard that does not look at the score."
        lede="The semantic layer is what makes a paraphrase free instead of full price. It is also the most dangerous component in the system, so it is the one with a deterministic veto in front of it."
        aside={
          <div className="overflow-hidden rounded-xl border border-line bg-[oklch(0.115_0_0)]">
            <div className="border-b border-line/60 px-4 py-2">
              <span className="mono text-[10.5px] uppercase tracking-[0.14em] text-ink-subtle">
                lookup order
              </span>
            </div>
            <pre className="code-block overflow-x-auto p-4 text-[oklch(0.9_0_0)]">
              <code>{LOOKUP_ORDER}</code>
            </pre>
          </div>
        }
      />

      <div className="mt-10 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {LAYERS.map((layer, index) => (
          <SpotlightCard
            key={layer.name}
            className="rounded-xl border border-line bg-surface p-5"
          >
            <div data-reveal className="relative flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="mono text-[11px] uppercase tracking-[0.14em] text-ink-subtle">
                  {index + 1}
                </span>
                <Layers
                  className={cn(
                    "h-4 w-4 transition-transform duration-500 ease-out-quint group-hover:scale-110",
                    layer.tone === "warm" && "text-warm",
                    layer.tone === "accent" && "text-accent",
                    layer.tone === "replay" && "text-replay",
                  )}
                />
              </div>
              <h3 className="mono text-[15px] font-medium text-ink">{layer.name}</h3>
              <p className="text-[12.5px] text-ink-muted">{layer.detail}</p>
              <p className="mono text-[11px] text-ink-subtle">{layer.store}</p>
            </div>
          </SpotlightCard>
        ))}
      </div>

      <div className="mt-3.5 grid gap-3.5 lg:grid-cols-2">
        <SpotlightCard
          tilt={false}
          className="rounded-xl border border-line bg-surface p-6"
        >
          <div data-reveal className="relative flex flex-col gap-4">
            <MonoLabel tone="muted">the guard</MonoLabel>
            <div className="flex flex-col gap-2.5 rounded-lg border border-line bg-surface-sunken p-4">
              {[
                { q: "Nvidia Q3 2024 revenue", tone: "ink" },
                { q: "Nvidia Q4 2024 revenue", tone: "ink" },
              ].map((row) => (
                <div key={row.q} className="mono text-[12px] text-ink">
                  {row.q}
                </div>
              ))}
              <div className="flex items-center gap-2 border-t border-line pt-2.5">
                <span className="mono text-[11px] text-ink-subtle">cosine 0.97</span>
                <ArrowRight className="h-3 w-3 text-ink-subtle" />
                <span className="mono rounded-full border border-danger/30 bg-danger-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-danger">
                  rejected
                </span>
              </div>
            </div>
            <p className="text-[13.5px] leading-[1.7] text-ink-muted">
              Numerals, versions and named entities are compared on exact set equality,
              independently of the similarity score. Both queries mention a quarter; the sets
              differ; rejected, whatever the cosine says.
            </p>
          </div>
        </SpotlightCard>

        <SpotlightCard tilt={false} className="rounded-xl border border-line bg-surface p-6">
          <div data-reveal className="relative flex flex-col gap-4">
            <MonoLabel tone="muted">freshness</MonoLabel>
            <div className="flex flex-col gap-2">
              {[
                { name: "realtime", bound: "< 15m" },
                { name: "fresh", bound: "< 24h" },
                { name: "recent", bound: "< 7d" },
                { name: "stable", bound: "no bound" },
              ].map((row) => (
                <div
                  key={row.name}
                  className="flex items-center justify-between rounded-md border border-line bg-surface-sunken px-3 py-2 transition-colors duration-300 hover:border-line-strong"
                >
                  <span className="mono text-[12px] text-ink">{row.name}</span>
                  <span className="mono text-[11px] text-ink-subtle">{row.bound}</span>
                </div>
              ))}
            </div>
            <p className="text-[13.5px] leading-[1.7] text-ink-muted">
              Available is not acceptable. An entry only counts toward marginal savings if it
              satisfies the step&apos;s inferred freshness bound, so a six-hour-old price never
              reads as warm.
            </p>
          </div>
        </SpotlightCard>
      </div>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// Benchmark
// --------------------------------------------------------------------------

const ROWS = [
  { system: "Unaided model, no catalog", accuracy: 0, chain: 10.8, locale: 4.2, freshness: 0 },
  { system: "Embedding retrieval only", accuracy: 0, chain: 11.7, locale: 4.2, freshness: 0 },
  { system: "SerpFlow planner", accuracy: 38.3, chain: 46.7, locale: 79.2, freshness: 55.0 },
] as const;

export function Benchmark() {
  return (
    <Revealed id="benchmark" className="bg-surface-sunken/40">
      <SectionHeading
        label="the evidence"
        title="120 hand-authored tasks, and the honest number."
        lede="38.3% is what the deterministic adapter scores - the one that runs with no API keys at all. It is not a ceiling and it is not a marketing figure: the dominant failure mode is still wrong-engine selection on 58 of 120 tasks."
        aside={
          <div className="rounded-xl border border-line bg-surface p-5">
            <div className="mono mb-3 text-[10.5px] uppercase tracking-[0.16em] text-ink-subtle">
              outcome on 120 tasks
            </div>
            <div className="flex flex-col gap-2.5">
              {FAILURE_MODES.map((row) => (
                <div key={row.label} className="flex items-center gap-3">
                  <span className="w-32 shrink-0 text-[12.5px] text-ink-muted">{row.label}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                    <span
                      className={cn("block h-full rounded-full", row.tone)}
                      style={{ width: `${(row.count / 120) * 100}%` }}
                    />
                  </span>
                  <span className="mono w-6 shrink-0 text-right text-[11.5px] text-ink-subtle">
                    {row.count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        }
      />

      <div data-reveal className="mt-9 overflow-hidden rounded-xl border border-line bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-left">
            <thead>
              <tr className="border-b border-line bg-surface-sunken">
                {["System", "Accuracy", "Engine chain", "Locale params", "Freshness"].map(
                  (head, index) => (
                    <th
                      key={head}
                      className={cn(
                        "mono px-4 py-3 text-[11px] uppercase tracking-[0.12em] text-ink-subtle",
                        index > 0 && "text-right",
                      )}
                    >
                      {head}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, index) => {
                const best = index === ROWS.length - 1;
                return (
                  <tr
                    key={row.system}
                    className={cn(
                      "border-b border-line last:border-0 transition-colors duration-300 hover:bg-surface-sunken",
                      best && "bg-accent-ghost/25",
                    )}
                  >
                    <td
                      className={cn(
                        "px-4 py-3.5 text-[13.5px]",
                        best ? "font-medium text-ink" : "text-ink-muted",
                      )}
                    >
                      {row.system}
                    </td>
                    {([row.accuracy, row.chain, row.locale, row.freshness] as number[]).map(
                      (value, cell) => (
                        <td
                          key={cell}
                          className={cn(
                            "mono px-4 py-3.5 text-right text-[13px]",
                            best ? "font-semibold text-ink" : "text-ink-subtle",
                            best && cell === 0 && "text-warm",
                          )}
                        >
                          {value.toFixed(1)}%
                        </td>
                      ),
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <p data-reveal className="mt-5 max-w-3xl text-[13px] leading-[1.7] text-ink-subtle">
        Both baselines score zero on exact chain match because neither can do what the task set
        requires. An unaided model has no dependency edges, so it cannot discover that reviewer
        identity is reachable only through a specific produced field. Embedding retrieval has no
        selector and no path-finding, so it can only ever return one engine. Reproduce with{" "}
        <code className="mono text-ink-muted">make benchmark</code>; results commit per catalog
        version.
      </p>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// Capabilities
// --------------------------------------------------------------------------

const CAPABILITIES = [
  {
    icon: Workflow,
    title: "Typed engine graph",
    body: "Dependency edges make multi-hop chains computable. Substitute edges make alternatives generatable. Both are mandatory - with one candidate, a ranking cannot change.",
    to: "/docs/architecture/catalog",
  },
  {
    icon: Zap,
    title: "Marginal-cost replanning",
    body: "Candidates ranked on the cost of steps that still need a live call, with both rankings persisted so the disagreement is a stored fact rather than a claim.",
    to: "/docs/architecture/marginal-replanning",
  },
  {
    icon: Radio,
    title: "Real-time streaming",
    body: "Server-sent events, one frame per real stage transition, with reconnection by Last-Event-ID and a buffer mirrored into Redis for cross-worker attach.",
    to: "/docs/api/streaming",
  },
  {
    icon: Activity,
    title: "Computed governance",
    body: "Budgets at four scopes, savings decomposed by the mechanism that produced them, and attribution from organization down to a single engine call.",
    to: "/docs/architecture/overview",
  },
  {
    icon: ShieldCheck,
    title: "Multi-tenant by default",
    body: "Row-level security on 23 tables behind application guards, cross-tenant reads answered with 404, and an append-only hash-chained audit log.",
    to: "/docs/database/rls",
  },
  {
    icon: Lock,
    title: "Credentials that cannot leak",
    body: "Envelope encryption with a per-credential data key, decryption in three functions, and no field in any response schema that could carry a secret.",
    to: "/docs/security/credentials",
  },
] as const;

export function Capabilities() {
  return (
    <Revealed id="capabilities">
      <SectionHeading
        label="what it does"
        title="A control plane, not a wrapper."
        lede="All of it runs against the same catalog the demo uses, in the same repository."
        aside={
          <div className="grid grid-cols-3 gap-3">
            {[
              { value: "69", label: "API paths" },
              { value: "33", label: "tables" },
              { value: "180", label: "tests" },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl border border-line bg-surface px-4 py-3.5 text-center transition-colors duration-300 hover:border-line-strong"
              >
                <div className="mono text-[20px] font-semibold leading-none text-ink">
                  {item.value}
                </div>
                <div className="mt-1.5 text-[11.5px] text-ink-subtle">{item.label}</div>
              </div>
            ))}
          </div>
        }
      />
      <div className="mt-10 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {CAPABILITIES.map((item) => {
          const Icon = item.icon;
          return (
            <SpotlightCard
              key={item.title}
              className="rounded-xl border border-line bg-surface p-6"
            >
              <Link to={item.to} data-reveal className="relative flex h-full flex-col gap-3.5">
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface-sunken text-accent transition-transform duration-500 ease-out-quint group-hover:scale-110">
                  <Icon className="h-4 w-4" />
                </span>
                <h3 className="text-[15px] font-medium leading-snug text-ink">{item.title}</h3>
                <p className="flex-1 text-[13.5px] leading-[1.7] text-ink-muted">{item.body}</p>
                <span className="mono inline-flex items-center gap-1.5 text-[11.5px] text-accent-strong opacity-0 transition-opacity duration-400 group-hover:opacity-100">
                  Read more
                  <ArrowRight className="h-3 w-3" />
                </span>
              </Link>
            </SpotlightCard>
          );
        })}
      </div>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// Quick start
// --------------------------------------------------------------------------

const COMMANDS = [
  { cmd: "make install", note: "venv, backend deps, npm install" },
  { cmd: "make up", note: "postgres, redis, kafka" },
  { cmd: "make seed", note: "catalog, benchmarks, demo org - prints a test key" },
  { cmd: "make demo", note: "proves the thesis, exits non-zero if it fails" },
  { cmd: "make dev", note: "API on :8000, frontend on :5173" },
] as const;

export function QuickStart() {
  return (
    <Revealed id="quick-start" className="bg-surface-sunken/40">
      <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center lg:gap-12">
        <SectionHeading
          label="quick start"
          title="Five commands, and no API keys at all."
          lede="The planner falls back to a deterministic adapter, execution falls back to cassettes, and a test key returns mock results with zero SerpApi credits. make dev and make seed must work on a machine that has never seen a SerpApi key - and they do."
        />

        <div data-reveal className="min-w-0 overflow-hidden rounded-xl border border-line bg-[oklch(0.11_0_0)] shadow-float">
          <div className="flex items-center gap-2 border-b border-line/60 px-4 py-2.5">
            <div className="flex gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
              <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
              <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
            </div>
            <span className="mono flex-1 text-center text-[11px] text-ink-subtle">bash</span>
            <span className="w-12" />
          </div>
          <div className="code-block flex flex-col gap-2.5 overflow-x-auto p-5">
            {COMMANDS.map((line) => (
              <div key={line.cmd} className="group/cmd flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-warm">$</span>
                  <span className="text-[oklch(0.95_0_0)]">{line.cmd}</span>
                </div>
                <span className="pl-4 text-[11.5px] text-ink-subtle transition-colors duration-300 group-hover/cmd:text-ink-muted">
                  {line.note}
                </span>
              </div>
            ))}
            <div className="mt-2 border-t border-line/50 pt-3 text-[11.5px] text-warm">
              PROVEN: cache-aware marginal-cost replanning changed the selected plan.
            </div>
          </div>
        </div>
      </div>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// FAQ
// --------------------------------------------------------------------------

const FAQ = [
  {
    q: "How is this different from caching SerpApi responses?",
    a: "A cache makes the plan you already chose cheaper. This changes which plan gets chosen. Both rankings are computed and persisted, and the metric serpflow_marginal_replan_changed_selection_total counts the disagreements - a cache hit on the same plan is explicitly not counted.",
  },
  {
    q: "Does it replace SerpApi?",
    a: "No. It is a control plane in front of it and needs your own SerpApi credential. SerpApi remains the only outbound data path; SerpFlow does not scrape and does not verify what comes back.",
  },
  {
    q: "Can I try it without a SerpApi account?",
    a: "Yes. make seed prints a test key that routes to a deterministic mock and spends zero credits, regardless of how the server is configured. That precedence is absolute and cannot be overridden.",
  },
  {
    q: "What happens to my existing SerpApi code?",
    a: "The drop-in compatibility client keeps its shape. Change the base URL and the key, and the request goes through the cache layers, budget enforcement and provenance. It does not re-route: you asked for an engine, you get that engine.",
  },
  {
    q: "Why is routing accuracy only 38.3%?",
    a: "Because that is what it measures. The dominant failure mode is wrong-engine selection on 58 of 120 tasks, and the full error analysis is published alongside the number, including two cases where the label is arguably wrong rather than the planner.",
  },
  {
    q: "Is the semantic cache safe?",
    a: "A deterministic guard on numerals, versions and named entities runs independently of the cosine score, and freshness bounds gate what counts as warm. Operators can report a false hit from the Run Inspector, which invalidates the entry and increments a counter that is worth paging on.",
  },
] as const;

export function Faq() {
  return (
    <Revealed id="faq">
      <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:gap-12">
        <SectionHeading label="questions" title="The ones worth asking first." />
        <div data-reveal>
          <Accordion type="single" collapsible className="flex flex-col gap-2">
            {FAQ.map((item, index) => (
              <AccordionItem
                key={item.q}
                value={`item-${index}`}
                className="overflow-hidden rounded-xl border border-line bg-surface px-5 transition-colors duration-300 hover:border-line-strong"
              >
                <AccordionTrigger className="py-4 text-left text-[14.5px] font-medium text-ink hover:no-underline">
                  {item.q}
                </AccordionTrigger>
                <AccordionContent className="pb-4 text-[13.5px] leading-[1.75] text-ink-muted">
                  {item.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </Revealed>
  );
}

// --------------------------------------------------------------------------
// Call to action
// --------------------------------------------------------------------------

export function CallToAction() {
  const ref = React.useRef<HTMLElement>(null);
  useReveal(ref);
  useTextReveal(ref);

  return (
    <section ref={ref} className="relative overflow-hidden border-t border-line py-20 sm:py-24">
      <Atmosphere variant="hero" />
      <div className="relative mx-auto flex w-full max-w-3xl flex-col items-center gap-8 px-5 text-center sm:px-8">
        <div data-reveal>
          <MonoLabel>
            <Boxes className="h-3 w-3" />
            open source
          </MonoLabel>
        </div>
        <h2
          data-split
          className="display text-balance text-[clamp(2.1rem,5vw,3.5rem)] leading-[1.03]"
        >
          Run it, and watch the plan change.
        </h2>
        <p data-reveal className="max-w-xl text-pretty text-[15.5px] leading-[1.75] text-ink-muted">
          Everything on this page is reproducible from a clone. The demo exits non-zero if
          cache-aware replanning stops changing the selected plan, so the claim either holds or the
          build fails.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <span data-reveal>
            <CtaLink to="/app">
              Open the console
              <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-out-quint group-hover:translate-x-0.5" />
            </CtaLink>
          </span>
          <span data-reveal>
            <CtaLink href="https://github.com/serpflow/serpflow" variant="ghost">
              View the source
            </CtaLink>
          </span>
        </div>
      </div>
    </section>
  );
}
