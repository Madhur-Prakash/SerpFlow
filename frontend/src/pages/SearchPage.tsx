/**
 * The central product interaction (section 69).
 *
 *   What do you want to search?
 *
 * The pipeline animates from real SSE events. The costs, warm steps and
 * rejected alternatives shown afterwards are the values the planner persisted,
 * not figures recomputed here.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  ExternalLink,
  Eye,
  Play,
  RotateCcw,
  Route,
  Search as SearchIcon,
  Shuffle,
  Wallet,
  Zap,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { itemVariants, listVariants, scaleVariants } from "@/animations";
import { PlanGraph } from "@/components/graphs/PlanGraph";
import {
  CacheLayerBadge,
  CostComparison,
  EmptyState,
  ErrorMessage,
  FreshnessBadge,
  ModeBadge,
  PageHeader,
  Section,
  WarmIndicator,
} from "@/components/shared";
import { Pipeline } from "@/components/shared/Pipeline";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
  Label,
  Skeleton,
  Textarea,
  Tooltip,
} from "@/components/ui";
import { useInvalidateRunData } from "@/hooks/useQueries";
import { usePacedRun, useRunStream } from "@/hooks/useRunStream";
import { api, ApiError } from "@/lib/api";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";
import { PERMISSIONS, useSession } from "@/stores/session";
import type { ModeInfo, Run, SearchResponse } from "@/types/api";

const EXAMPLES = [
  {
    intent: "find coordinated review rings among Koramangala cafes",
    note: "The reference demo. Reaches google_maps_contributor_reviews through typed dependency edges.",
  },
  {
    intent: "recent reviews for a ramen shop in Seoul called Ichiran",
    note: "Locale inference is the discriminator: Seoul implies gl=kr and hl=ko.",
  },
  {
    intent: "cheapest nonstop flights from Hyderabad to Da Nang in late November",
    note: "Entity resolution and date normalisation. No substitute engine exists for fares.",
  },
  {
    intent: "who is hiring senior rust engineers in Berlin",
    note: "Single-engine routing with a locale-sensitive parameter.",
  },
];

export function SearchPage() {
  const navigate = useNavigate();
  const { project, can } = useSession();
  const invalidate = useInvalidateRunData();

  const [intent, setIntent] = React.useState("");
  const [budget, setBudget] = React.useState<string>("20");
  const [runId, setRunId] = React.useState<string | null>(null);
  const [mode, setMode] = React.useState<ModeInfo | null>(null);
  const [result, setResult] = React.useState<SearchResponse | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [failedRun, setFailedRun] = React.useState<Run | null>(null);

  // The raw stream is the truth; the paced view reveals it in order.
  const stream = usePacedRun(useRunStream(runId), runId);
  const canExecute = can(PERMISSIONS.execute);

  // When the stream reports completion, fetch the persisted run. The UI reads
  // stored values rather than reconstructing them from the event payloads. A
  // failed run is fetched too: it still has a plan, spend and an error to show.
  React.useEffect(() => {
    if (!runId || !stream.finished) return;
    let cancelled = false;
    (async () => {
      try {
        const run = await api.run(runId);
        if (cancelled) return;
        if (stream.failed) {
          setFailedRun(run);
          invalidate();
          return;
        }
        setResult({
          run,
          plan: run.plan!,
          results: { summary: run.result_summary },
          mode: mode ?? {
            mode: run.mode,
            label: run.mode.toUpperCase() as ModeInfo["label"],
            reason: "",
            credited: run.mode === "live",
          },
          provenance: run.provenance,
        });
        invalidate();
      } catch (loadError) {
        if (!cancelled) setError(loadError);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, stream.finished, stream.failed, mode, invalidate]);

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const trimmed = intent.trim();
    if (trimmed.length < 3) return;

    setError(null);
    setResult(null);
    setFailedRun(null);
    setRunId(null);
    setStarting(true);

    try {
      const accepted = await api.startStreamingSearch({
        intent: trimmed,
        budget: budget ? Number(budget) : null,
        project_id: project?.id ?? null,
      });
      setMode(accepted.mode);
      setRunId(accepted.run_id);
    } catch (startError) {
      setError(startError);
      if (startError instanceof ApiError) {
        toast.error(startError.code, { description: startError.message });
      }
    } finally {
      setStarting(false);
    }
  }

  function reset() {
    setRunId(null);
    setResult(null);
    setFailedRun(null);
    setError(null);
    stream.reset();
  }

  const running = Boolean(runId) && !stream.finished;
  const showPipeline = Boolean(runId);

  return (
    <div className="space-y-7">
      <PageHeader
        title="Search"
        icon={SearchIcon}
        description="Describe what you want. SerpFlow discovers the engine or engine chain, inspects what is already warm, and executes only the steps that still need a live call."
        actions={
          result || failedRun ? (
            <>
              <Button variant="outline" size="sm" onClick={reset}>
                <RotateCcw />
                New search
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate("/app/runs/" + (result?.run.id ?? failedRun?.id))}
              >
                <Eye />
                Run Inspector
              </Button>
            </>
          ) : null
        }
      />

      {/* ------------------------------------------------------- input */}
      <Card className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 grid-field opacity-30" />
        <form onSubmit={submit} className="relative space-y-4 p-5">
          <div className="space-y-2">
            <Label htmlFor="intent">What do you want to search?</Label>
            <Textarea
              id="intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submit();
              }}
              placeholder="find coordinated review rings among Koramangala cafes"
              rows={2}
              className="min-h-16 text-[15px] leading-relaxed"
              disabled={running}
            />
          </div>

          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex items-end gap-3">
              <div className="w-32 space-y-1.5">
                <Label htmlFor="budget">Budget</Label>
                <div className="relative">
                  <Input
                    id="budget"
                    type="number"
                    min={1}
                    value={budget}
                    onChange={(event) => setBudget(event.target.value)}
                    disabled={running}
                    className="pr-9"
                  />
                  <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-ink-subtle">
                    cr
                  </span>
                </div>
              </div>
              <p className="pb-2 max-w-sm text-[12px] leading-relaxed text-ink-subtle">
                A budget makes the planner reduce fan-out rather than refuse, and every
                reduction is recorded with what it costs you.
              </p>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={running || starting || intent.trim().length < 3 || !canExecute}
            >
              {running ? (
                <>
                  <Zap className="animate-pulse" />
                  Executing
                </>
              ) : (
                <>
                  <Play />
                  Run search
                </>
              )}
            </Button>
          </div>

          {!canExecute ? (
            <Alert tone="caution" icon={AlertTriangle} title="Your role cannot execute">
              Planning calls a language model, not SerpApi, so it costs nothing and analysts
              can do it. Executing spends credits and needs the developer role or above.
            </Alert>
          ) : null}
        </form>
      </Card>

      {/* ------------------------------------------------------ examples */}
      {!showPipeline ? (
        <motion.div variants={listVariants} initial="initial" animate="animate">
          <Section
            title="Try one of these"
            description="Each one exercises a different part of the planner."
          >
            <div className="grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map((example) => (
                <motion.button
                  key={example.intent}
                  variants={itemVariants}
                  onClick={() => setIntent(example.intent)}
                  className="group rounded-[var(--radius-md)] border border-line bg-surface p-3.5 text-left transition-colors hover:border-accent-muted hover:bg-surface-raised"
                >
                  <p className="text-[13px] font-medium text-ink group-hover:text-accent-strong">
                    {example.intent}
                  </p>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                    {example.note}
                  </p>
                </motion.button>
              ))}
            </div>
          </Section>
        </motion.div>
      ) : null}

      {error ? <ErrorMessage error={error} onRetry={() => submit()} /> : null}

      {/* ------------------------------------------------------ pipeline */}
      <AnimatePresence>
        {showPipeline ? (
          <motion.div
            variants={scaleVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]"
          >
            <Card>
              <CardHeader
                title="Execution pipeline"
                icon={Route}
                description="Driven by Server-Sent Events from the planner and executor. A stage only completes when its real event arrives; fast stages are held briefly so the order stays readable."
                action={
                  mode ? <ModeBadge mode={mode.label} reason={mode.reason} /> : null
                }
              />
              <CardBody>
                <Pipeline
                  stages={stream.stages}
                  currentStage={stream.currentStage}
                  finished={stream.finished}
                  failed={stream.failed}
                />
              </CardBody>
            </Card>

            <div className="space-y-5">
              {result ? (
                <ResultPanel result={result} onReplay={reset} />
              ) : stream.failed ? (
                <FailedRunPanel
                  run={failedRun}
                  error={stream.error}
                  onInspect={() => navigate("/app/runs/" + (failedRun?.id ?? runId))}
                  onRetry={reset}
                />
              ) : (
                <Card>
                  <CardHeader title="Result" icon={CheckCircle} />
                  <CardBody className="space-y-3">
                    <Skeleton className="h-5 w-2/3" />
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-4 w-1/2" />
                    <p className="pt-1 text-[12px] text-ink-subtle">
                      Waiting for the executor. The plan appears as soon as the run finishes.
                    </p>
                  </CardBody>
                </Card>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------- failed run

/** What a failed run can still tell you: why, what it spent, where to look. */
function FailedRunPanel({
  run,
  error,
  onInspect,
  onRetry,
}: {
  run: Run | null;
  error: { code: string; message: string } | null;
  onInspect: () => void;
  onRetry: () => void;
}) {
  const message = error?.message || run?.error_message || "The run failed.";
  return (
    <Card>
      <CardHeader title="Run failed" icon={AlertTriangle} />
      <CardBody className="space-y-4">
        <Alert tone="danger" icon={AlertTriangle} title={error?.code ?? "RUN_FAILED"}>
          {message}
        </Alert>
        {run ? (
          <dl className="grid grid-cols-2 gap-3 text-[12px]">
            <div>
              <dt className="text-ink-subtle">Credits recorded</dt>
              <dd className="mono mt-0.5 text-[15px] text-ink">{run.credits_spent}</dd>
            </div>
            <div>
              <dt className="text-ink-subtle">Mode</dt>
              <dd className="mono mt-0.5 text-[15px] text-ink">{run.mode.toUpperCase()}</dd>
            </div>
          </dl>
        ) : null}
        <p className="text-[12px] leading-relaxed text-ink-subtle">
          The plan and every step that ran are in the Run Inspector. Only searches SerpApi
          actually processed are counted as spend.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onInspect}>
            <Eye />
            Run Inspector
          </Button>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCcw />
            New search
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

// --------------------------------------------------------------- result
function ResultPanel({ result, onReplay }: { result: SearchResponse; onReplay: () => void }) {
  const navigate = useNavigate();
  const { plan, run, mode } = result;
  const summary = result.results?.summary;

  return (
    <motion.div
      variants={listVariants}
      initial="initial"
      animate="animate"
      className="space-y-5"
    >
      {/* The visual proof of the product thesis (section 48). */}
      {plan.marginal_replan_changed_selection ? (
        <motion.div variants={itemVariants}>
          <Card className="border-warm/40 bg-warm-ghost/30">
            <CardBody className="space-y-2">
              <div className="flex items-center gap-2">
                <Zap className="size-4 text-warm" />
                <p className="text-[13px] font-semibold text-warm">
                  Marginal cost changed which plan was selected
                </p>
              </div>
              <p className="text-[12px] leading-relaxed text-ink-muted text-pretty">
                {plan.replan_explanation}
              </p>
            </CardBody>
          </Card>
        </motion.div>
      ) : null}

      <motion.div variants={itemVariants}>
        <Card>
          <CardHeader
            title="Selected plan"
            icon={Route}
            description={
              plan.candidate_count > 1
                ? plan.candidate_count +
                  " candidates were generated and ranked twice: once on cold cost, once on marginal cost."
                : (plan.single_candidate_reason ?? "Only one candidate exists.")
            }
            action={<ModeBadge mode={mode.label} reason={mode.reason} />}
          />
          <CardBody className="space-y-5">
            <PlanGraph plan={plan} />

            <CostComparison
              naive={plan.naive_cost}
              marginal={plan.marginal_cost}
              actual={run.credits_spent}
              projection={
                plan.projected_full_scale_cost && plan.projected_full_scale_cost > plan.naive_cost
                  ? plan.projected_full_scale_cost
                  : null
              }
            />

            <StepTable plan={plan} run={run} />

            {plan.budget_reduction?.reductions?.length ? (
              <div className="space-y-2">
                <p className="text-[12px] font-medium text-caution">
                  Budget reductions applied
                </p>
                {plan.budget_reduction.reductions.map((reduction, index) => (
                  <div
                    key={index}
                    className="rounded-[var(--radius-sm)] border border-caution/25 bg-caution-ghost px-3 py-2"
                  >
                    <p className="mono text-[12px] text-caution">
                      step {reduction.step} {reduction.engine}: {reduction.original} -{">"}{" "}
                      {reduction.reduced} calls
                    </p>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-muted text-pretty">
                      {reduction.impact_note}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate("/app/plans/" + plan.id)}
              >
                <Route />
                Plan Inspector
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/app/runs/" + run.id)}
              >
                <Eye />
                Run Inspector
              </Button>
              <Button variant="ghost" size="sm" onClick={onReplay}>
                <RotateCcw />
                New search
              </Button>
              <span className="ml-auto mono text-[11px] text-ink-subtle">
                {plan.catalog_version} - {fmt.ms(plan.planner_latency_ms)} planning
              </span>
            </div>
          </CardBody>
        </Card>
      </motion.div>

      {/* Why this plan beat the alternatives (section 48). */}
      {plan.rejected_alternatives.length ? (
        <motion.div variants={itemVariants}>
          <Card>
            <CardHeader
              title="Why this plan beat the alternatives"
              icon={Shuffle}
              description="Every candidate the planner generated, with the reason it lost. These are stored values."
            />
            <CardBody className="space-y-2">
              {plan.rejected_alternatives.slice(0, 6).map((alternative) => (
                <div
                  key={alternative.plan}
                  className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="mono text-[12px] text-ink-muted">{alternative.plan}</span>
                    <Badge tone="outline" className="mono">
                      cold {alternative.naive_cost}
                    </Badge>
                    <Badge
                      tone={
                        alternative.marginal_cost < alternative.naive_cost ? "warm" : "outline"
                      }
                      className="mono"
                    >
                      marginal {alternative.marginal_cost}
                    </Badge>
                    {alternative.role === "fallback" ? (
                      <Badge tone="outline">fallback</Badge>
                    ) : null}
                  </div>
                  {alternative.reason ? (
                    <p className="mt-1.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                      {alternative.reason}
                    </p>
                  ) : null}
                </div>
              ))}
            </CardBody>
          </Card>
        </motion.div>
      ) : null}

      {/* ---------------------------------------------------- results */}
      <motion.div variants={itemVariants}>
        <Card>
          <CardHeader
            title="Results"
            icon={SearchIcon}
            description={
              summary?.count
                ? summary.count + " " + fmt.plural(summary.count, "result") +
                  (summary.result_key ? " from " + summary.result_key : "")
                : undefined
            }
          />
          <CardBody>
            {summary?.items?.length ? (
              <ul className="divide-y divide-line">
                {summary.items.map((item, index) => (
                  <li key={index} className="flex items-start gap-3 py-2.5 first:pt-0">
                    <span className="mono mt-0.5 w-5 shrink-0 text-[11px] text-ink-subtle">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {item.title ?? "(untitled)"}
                      </p>
                      {item.snippet ? (
                        <p className="mt-0.5 line-clamp-2 text-[12px] text-ink-subtle">
                          {item.snippet}
                        </p>
                      ) : null}
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-subtle">
                        {item.rating ? <span>rating {item.rating}</span> : null}
                        {item.price ? <span className="mono">{item.price}</span> : null}
                        {item.source ? <span>{item.source}</span> : null}
                        {item.date ? <span>{item.date}</span> : null}
                      </div>
                    </div>
                    {item.link ? (
                      <a
                        href={item.link}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="mt-0.5 text-ink-subtle transition-colors hover:text-accent"
                        aria-label="Open result"
                      >
                        <ExternalLink className="size-3.5" />
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : summary?.notice ? (
              <EmptyState
                icon={SearchIcon}
                title="SerpApi found no results"
                description={
                  summary.notice +
                  " The search ran and was billed, so it is counted in your spend and cached; try rephrasing the intent."
                }
              />
            ) : (
              <EmptyState
                icon={SearchIcon}
                title="No result rows"
                description="The run finished but the terminal engine returned no list-shaped results. The raw payload is available in the Run Inspector."
              />
            )}
          </CardBody>
        </Card>
      </motion.div>

      {/* --------------------------------------------------- provenance */}
      <motion.div variants={itemVariants}>
        <Card>
          <CardHeader
            title="Provenance"
            icon={Wallet}
            description="Section 45 ships these on every response header too."
          />
          <CardBody>
            <dl className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
              <ProvenanceRow label="Run" value={run.id} mono />
              <ProvenanceRow label="Mode" value={mode.label} />
              <ProvenanceRow label="Catalog version" value={plan.catalog_version} mono />
              <ProvenanceRow
                label="Cache layers"
                value={Object.entries(run.cache_summary)
                  .filter(([, count]) => count > 0)
                  .map(([layer, count]) => layer + " " + count)
                  .join(", ") || "none"}
                mono
              />
              <ProvenanceRow label="Credits spent" value={fmt.credits(run.credits_spent)} mono />
              <ProvenanceRow label="Credits saved" value={fmt.credits(run.credits_saved)} mono />
              <ProvenanceRow label="Duration" value={fmt.ms(run.duration_ms)} mono />
              <ProvenanceRow
                label="Retention"
                value={
                  run.max_pii_risk === "high"
                    ? "7 days (high PII risk)"
                    : "30 days (standard)"
                }
              />
            </dl>
          </CardBody>
        </Card>
      </motion.div>
    </motion.div>
  );
}

function ProvenanceRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">{label}</dt>
      <dd className={cn("mt-0.5 truncate text-[12px] text-ink", mono ? "mono" : "")}>
        {value}
      </dd>
    </div>
  );
}

function StepTable({ plan, run }: { plan: SearchResponse["plan"]; run: Run }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left">
        <thead>
          <tr className="border-b border-line text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
            <th className="pb-2 pr-3 font-medium">#</th>
            <th className="pb-2 pr-3 font-medium">Engine</th>
            <th className="pb-2 pr-3 font-medium">Calls</th>
            <th className="pb-2 pr-3 font-medium">Freshness</th>
            <th className="pb-2 pr-3 font-medium">Layer</th>
            <th className="pb-2 pr-3 text-right font-medium">Credits</th>
            <th className="pb-2 text-right font-medium">Latency</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {plan.steps.map((step) => {
            const executed = run.steps.find((candidate) => candidate.index === step.index);
            return (
              <tr key={step.index} className="text-[12px]">
                <td className="py-2 pr-3 mono text-ink-subtle">{step.index}</td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <span className="mono text-ink">{step.engine}</span>
                    <WarmIndicator warm={step.warm} />
                  </div>
                  {step.cache_state?.reason ? (
                    <Tooltip content={step.cache_state.reason}>
                      <p className="mt-0.5 max-w-xs truncate text-[11px] text-ink-subtle">
                        {step.cache_state.reason}
                      </p>
                    </Tooltip>
                  ) : null}
                </td>
                <td className="py-2 pr-3 mono text-ink-muted">
                  {step.fan_out > 1 ? "x" + step.fan_out : "1"}
                </td>
                <td className="py-2 pr-3">
                  <FreshnessBadge level={step.freshness_requirement} />
                </td>
                <td className="py-2 pr-3">
                  <CacheLayerBadge layer={executed?.cache_layer ?? step.cache_state?.layer} />
                </td>
                <td className="py-2 pr-3 text-right mono tabular text-ink">
                  {fmt.credits(executed?.credits ?? 0)}
                </td>
                <td className="py-2 text-right mono tabular text-ink-subtle">
                  {fmt.ms(executed?.latency_ms)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-subtle">
        <ArrowRight className="size-3" />
        Executor order per step: exact, then semantic, then the Searches Archive, then live.
      </p>
    </div>
  );
}
