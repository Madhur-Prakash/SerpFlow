/**
 * The Plan Inspector (section 48).
 *
 *   Intent -> candidate engines -> candidate plans (all of them) ->
 *   cache state per step -> marginal cost per plan -> selected path
 *
 * Every number on this page is read from the persisted Plan. The
 * counterfactual - what the cold ranking would have chosen - is a stored
 * decision, not something recomputed in the browser. When marginal cost
 * changed the selection, the page says so first and loudest.
 */

import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Layers,
  Route,
  Search,
  Snowflake,
  Thermometer,
  Wallet,
  XCircle,
  Zap,
} from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";

import { itemVariants, listVariants } from "@/animations";
import { PlanGraph } from "@/components/graphs/PlanGraph";
import {
  CacheLayerBadge,
  CostComparison,
  CoverageBadge,
  EmptyState,
  ErrorMessage,
  FreshnessBadge,
  ModeBadge,
  PageHeader,
  Section,
} from "@/components/shared";
import { Alert, Badge, Button, Card, CardBody, CardHeader, Skeleton, Tooltip } from "@/components/ui";
import { useRuns } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Plan } from "@/types/api";

export function PlanInspectorPage() {
  const { planId } = useParams<{ planId: string }>();
  const [plan, setPlan] = React.useState<Plan | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [loading, setLoading] = React.useState(Boolean(planId));
  const recentRuns = useRuns({ limit: 12 });

  React.useEffect(() => {
    if (!planId) {
      setPlan(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Plans are reached through their run, which is the object that carries
    // execution context as well.
    (async () => {
      try {
        const runs = await api.runs({ limit: 50 });
        const match = runs.items.find((run) => run.plan_id === planId);
        if (!match) throw new Error("No run references that plan.");
        const detail = await api.runPlan(match.id);
        if (!cancelled) setPlan(detail);
      } catch (loadError) {
        if (!cancelled) setError(loadError);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [planId]);

  if (!planId) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Plan Inspector"
          icon={Route}
          description="Pick a run to see every candidate plan the planner generated, what each one would cost cold and on the margin, and why the selected one won."
        />
        {recentRuns.data?.items.length ? (
          <Card>
            <CardHeader title="Recent plans" icon={Layers} />
            <ul className="divide-y divide-line">
              {recentRuns.data.items
                .filter((run) => run.plan_id)
                .map((run) => (
                  <li key={run.id}>
                    <Link
                      to={"/app/plans/" + run.plan_id}
                      className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-raised"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] text-ink">{run.intent}</p>
                        <p className="mono mt-0.5 text-[11px] text-ink-subtle">
                          {fmt.shortId(run.plan_id)} - {fmt.ago(run.created_at)}
                        </p>
                      </div>
                      <CostComparison
                        naive={run.naive_cost}
                        marginal={run.marginal_cost}
                        compact
                      />
                      <ArrowRight className="size-3.5 shrink-0 text-ink-subtle" />
                    </Link>
                  </li>
                ))}
            </ul>
          </Card>
        ) : (
          <EmptyState
            icon={Route}
            title="No plans yet"
            description="A plan is the set of candidate routes the planner generated for one intent, the cache state it found for each step, and the marginal cost it ranked them on. Run a search to create the first one."
            action={
              <Button asChild variant="primary" size="sm">
                <Link to="/app/search">
                  <Search />
                  Run a search
                </Link>
              </Button>
            }
          />
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-20" />
        <Skeleton className="h-72" />
      </div>
    );
  }
  if (error) return <ErrorMessage error={error} />;
  if (!plan) return null;

  const coldWinner = plan.candidates.find((c) => c.id === plan.cold_winner_candidate_id);
  const selected = plan.candidates.find((c) => c.selected);
  const ordered = [...plan.candidates].sort((a, b) => a.marginal_rank - b.marginal_rank);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-7">
      <PageHeader
        title="Plan Inspector"
        icon={Route}
        description={plan.intent}
        actions={<ModeBadge mode={plan.mode} />}
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <Badge tone="outline" className="mono">
            {fmt.shortId(plan.id)}
          </Badge>
          <Badge tone="outline" className="mono">
            {plan.catalog_version}
          </Badge>
          <Badge tone={plan.candidate_count > 1 ? "accent" : "caution"}>
            {plan.candidate_count} {fmt.plural(plan.candidate_count, "candidate")}
          </Badge>
          <span className="text-[12px] text-ink-subtle">
            confidence {plan.confidence.toFixed(3)} - planned in{" "}
            {fmt.ms(plan.planner_latency_ms)}
          </span>
        </div>
      </PageHeader>

      {/* ---------------------------------------- the thesis, up front */}
      {plan.marginal_replan_changed_selection ? (
        <motion.div variants={itemVariants}>
          <Card className="overflow-hidden border-warm/45">
            <div className="border-b border-warm/30 bg-warm-ghost/40 px-4 py-3">
              <div className="flex items-center gap-2">
                <Zap className="size-4 text-warm" />
                <p className="text-[13px] font-semibold text-warm">
                  Marginal cost changed which plan was selected
                </p>
              </div>
            </div>
            <CardBody className="space-y-4">
              <p className="text-[13px] leading-relaxed text-ink-muted text-pretty">
                {plan.replan_explanation}
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <RankingCard
                  title="Cold-cost ranking would have chosen"
                  icon={Snowflake}
                  label={coldWinner?.label ?? plan.cold_winner_candidate_id ?? "unknown"}
                  naive={coldWinner?.naive_cost}
                  marginal={coldWinner?.marginal_cost}
                  tone="cold"
                />
                <RankingCard
                  title="Marginal-cost ranking chose"
                  icon={Thermometer}
                  label={selected?.label ?? plan.steps.map((s) => s.engine).join(">")}
                  naive={selected?.naive_cost ?? plan.naive_cost}
                  marginal={selected?.marginal_cost ?? plan.marginal_cost}
                  tone="warm"
                />
              </div>
            </CardBody>
          </Card>
        </motion.div>
      ) : plan.candidate_count === 1 && plan.single_candidate_reason ? (
        <motion.div variants={itemVariants}>
          <Alert tone="caution" icon={AlertTriangle} title="Only one candidate existed">
            {plan.single_candidate_reason}
          </Alert>
        </motion.div>
      ) : null}

      {/* ---------------------------------------------- selected plan */}
      <motion.div variants={itemVariants}>
        <Card>
          <CardHeader
            title="Selected path"
            icon={Route}
            description="Cache state per step, as the planner found it at ranking time."
          />
          <CardBody className="space-y-5">
            <PlanGraph plan={plan} />
            <CostComparison
              naive={plan.naive_cost}
              marginal={plan.marginal_cost}
              projection={
                plan.projected_full_scale_cost &&
                plan.projected_full_scale_cost > plan.naive_cost
                  ? plan.projected_full_scale_cost
                  : null
              }
            />

            {plan.warm_steps.length ? (
              <div className="space-y-2">
                <p className="text-[12px] font-medium text-warm">
                  Warm steps - satisfiable without a live call
                </p>
                {plan.warm_steps.map((step) => (
                  <div
                    key={step.index}
                    className="flex flex-wrap items-center gap-2 rounded-[var(--radius-sm)] border border-warm/25 bg-warm-ghost/25 px-3 py-2"
                  >
                    <span className="mono text-[12px] text-ink">
                      step {step.index} {step.engine}
                    </span>
                    <CacheLayerBadge layer={step.layer} />
                    {step.age_seconds !== null && step.age_seconds !== undefined ? (
                      <Badge tone="outline" className="mono">
                        age {fmt.seconds(step.age_seconds)}
                      </Badge>
                    ) : null}
                    <Badge tone="warm" className="mono">
                      {fmt.credits(step.credits_avoided)} cr avoided
                    </Badge>
                    {step.reason ? (
                      <p className="w-full text-[11px] text-ink-subtle text-pretty">
                        {step.reason}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </CardBody>
        </Card>
      </motion.div>

      {/* ---------------------------------------------- freshness */}
      {plan.freshness_requirements.length ? (
        <Section
          title="Freshness requirements"
          icon={Thermometer}
          description="Inferred in stage C. A warm entry counts toward marginal savings only if it also satisfies these."
        >
          <Card>
            <CardBody className="space-y-2">
              {plan.freshness_requirements.map((requirement, index) => (
                <div
                  key={index}
                  className="flex flex-wrap items-center gap-2 border-b border-line pb-2 last:border-0 last:pb-0"
                >
                  <span className="mono w-56 shrink-0 text-[12px] text-ink">
                    step {requirement.step} {requirement.engine}
                  </span>
                  <FreshnessBadge level={requirement.requirement} />
                  <span className="min-w-0 flex-1 text-[11px] text-ink-subtle">
                    {requirement.signals.slice(0, 2).join("; ")}
                  </span>
                </div>
              ))}
            </CardBody>
          </Card>
        </Section>
      ) : null}

      {/* ------------------------------------------ candidate comparison */}
      <Section
        title="Every candidate plan"
        icon={Layers}
        description="Ranked twice. The cold rank is what a cache-blind planner would have chosen; the marginal rank is what executed."
      >
        <div className="space-y-3">
          {ordered.map((candidate) => (
            <Card
              key={candidate.id}
              className={cn(
                candidate.selected && "border-warm/45",
                !candidate.feasible_within_budget && "opacity-70",
              )}
            >
              <CardBody className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  {candidate.selected ? (
                    <Badge tone="warm">
                      <Zap />
                      selected
                    </Badge>
                  ) : null}
                  {candidate.id === plan.cold_winner_candidate_id && !candidate.selected ? (
                    <Badge tone="replay">
                      <Snowflake />
                      cold winner
                    </Badge>
                  ) : null}
                  <span className="mono text-[13px] text-ink">{candidate.label}</span>
                  <CoverageBadge coverage={candidate.coverage} />
                  <Badge tone="outline">{candidate.strategy}</Badge>
                  {!candidate.feasible_within_budget ? (
                    <Tooltip content="This plan could not be reduced to fit the budget, so it was excluded from selection.">
                      <Badge tone="danger">
                        <Ban />
                        does not fit
                      </Badge>
                    </Tooltip>
                  ) : null}
                </div>

                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <PlanGraph candidate={candidate} compact />
                  <div className="flex gap-2 sm:flex-col sm:items-end">
                    <RankBadge label="cold" rank={candidate.naive_rank} cost={candidate.naive_cost} />
                    <RankBadge
                      label="marginal"
                      rank={candidate.marginal_rank}
                      cost={candidate.marginal_cost}
                      warm
                    />
                  </div>
                </div>

                {candidate.trade_off_note ? (
                  <p className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2 text-[12px] leading-relaxed text-ink-muted text-pretty">
                    {candidate.trade_off_note}
                  </p>
                ) : null}

                {candidate.rejection_reason ? (
                  <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                    <XCircle className="mt-0.5 size-3 shrink-0" />
                    {candidate.rejection_reason}
                  </p>
                ) : null}
              </CardBody>
            </Card>
          ))}
        </div>
      </Section>

      {/* --------------------------------------------- rejected engines */}
      {plan.rejected_engines.length ? (
        <Section
          title="Engines the selector rejected"
          icon={XCircle}
          description="Stage B records why each retrieved engine was not chosen."
        >
          <Card>
            <CardBody className="space-y-2">
              {plan.rejected_engines.slice(0, 12).map((rejected, index) => (
                <div key={index} className="flex items-start gap-2.5 text-[12px]">
                  <span className="mono w-44 shrink-0 text-ink-muted">{rejected.engine}</span>
                  {rejected.hallucinated ? (
                    <Badge tone="danger">not in candidate set</Badge>
                  ) : null}
                  <span className="min-w-0 flex-1 text-ink-subtle text-pretty">
                    {rejected.reason}
                  </span>
                </div>
              ))}
            </CardBody>
          </Card>
        </Section>
      ) : null}

      {/* ------------------------------------------- budget reductions */}
      {plan.budget_reduction ? (
        <Section
          title="Budget reduction"
          icon={Wallet}
          description="What fitting the budget actually cost in answer quality."
        >
          <Card>
            <CardBody className="space-y-3">
              <p className="text-[12px] leading-relaxed text-ink-muted text-pretty">
                {plan.budget_reduction.note}
              </p>
              {plan.budget_reduction.reductions.map((reduction, index) => (
                <div
                  key={index}
                  className="rounded-[var(--radius-sm)] border border-caution/25 bg-caution-ghost px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="caution">{reduction.type.replace(/_/g, " ")}</Badge>
                    <span className="mono text-[12px] text-ink">
                      step {reduction.step} {reduction.engine}
                    </span>
                    <span className="mono text-[12px] text-caution">
                      {reduction.original} -{">"} {reduction.reduced}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-ink-muted text-pretty">
                    {reduction.impact_note}
                  </p>
                </div>
              ))}
            </CardBody>
          </Card>
        </Section>
      ) : null}
    </motion.div>
  );
}

function RankingCard({
  title,
  icon: Icon,
  label,
  naive,
  marginal,
  tone,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  naive?: number;
  marginal?: number;
  tone: "cold" | "warm";
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-sm)] border px-3 py-3",
        tone === "warm" ? "border-warm/35 bg-warm-ghost/25" : "border-line bg-surface-sunken",
      )}
    >
      <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
        <Icon className="size-3" />
        {title}
      </p>
      <p className="mono mt-1.5 text-[13px] font-medium text-ink">{label}</p>
      {naive !== undefined ? (
        <p className="mono mt-1 text-[12px] tabular text-ink-subtle">
          cold {fmt.credits(naive)} - marginal{" "}
          <span className={tone === "warm" ? "text-warm" : ""}>{fmt.credits(marginal ?? 0)}</span>
        </p>
      ) : null}
    </div>
  );
}

function RankBadge({
  label,
  rank,
  cost,
  warm,
}: {
  label: string;
  rank: number;
  cost: number;
  warm?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-sm)] border px-2.5 py-1.5 text-right",
        warm ? "border-warm/30 bg-warm-ghost/25" : "border-line bg-surface-sunken",
      )}
    >
      <p className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">
        {label} rank {rank + 1}
      </p>
      <p
        className={cn(
          "mono mt-0.5 text-[14px] font-semibold tabular",
          warm ? "text-warm" : "text-ink-muted",
        )}
      >
        {fmt.credits(cost)}
      </p>
    </div>
  );
}
