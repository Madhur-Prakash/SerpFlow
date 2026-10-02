/** The dashboard (section 46). Every figure is computed server side. */

import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Database,
  Gauge,
  GitBranch,
  Network,
  Search,
  Server,
  TrendingDown,
  Wallet,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";

import { itemVariants, listVariants } from "@/animations";
import { HorizontalBars, LayerDonut, UtilizationBar } from "@/components/charts";
import {
  CostComparison,
  EmptyState,
  ErrorMessage,
  ModeBadge,
  PageHeader,
  Section,
  StatCard,
  StatusDot,
} from "@/components/shared";
import { Badge, Button, Card, CardBody, Skeleton, Tooltip } from "@/components/ui";
import { useCrossProject, useDashboard, useHealth } from "@/hooks/useQueries";
import * as fmt from "@/lib/format";
import { useSession } from "@/stores/session";

export function OverviewPage() {
  const dashboard = useDashboard(30);
  const crossProject = useCrossProject();
  const health = useHealth();
  const { me } = useSession();

  if (dashboard.isError) {
    return <ErrorMessage error={dashboard.error} onRetry={() => dashboard.refetch()} />;
  }

  const data = dashboard.data;
  const replan = data?.marginal_replanning;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-7">
      <PageHeader
        title="Overview"
        icon={Gauge}
        description={
          "What SerpFlow spent, what it avoided spending, and how often cache-aware replanning changed the answer. Last " +
          (data?.window_days ?? 30) +
          " days."
        }
        actions={
          <>
            {health.data ? (
              <ModeBadge mode={health.data.mode} reason="Configured SERPFLOW_MODE." />
            ) : null}
            <Button asChild variant="primary" size="sm">
              <Link to="/app/search">
                <Search />
                New search
              </Link>
            </Button>
          </>
        }
      />

      {/* ------------------------------------------------ headline stats */}
      <motion.div
        variants={itemVariants}
        className="stagger-children grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {dashboard.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))
        ) : (
          <>
            <StatCard
              label="Credits spent"
              value={data?.credits_spent ?? 0}
              unit="cr"
              tone="spend"
              icon={Wallet}
              hint="Real upstream calls. Mock and replay runs cost nothing."
            />
            <StatCard
              label="Credits saved"
              value={data?.credits_saved ?? 0}
              unit="cr"
              tone="warm"
              icon={TrendingDown}
              hint={
                fmt.percent(data?.savings_ratio ?? 0) +
                " of what a naive execution would have cost."
              }
            />
            <StatCard
              label="Cache hit rate"
              value={fmt.percent(data?.cache_hit_rate ?? 0)}
              tone="accent"
              icon={Database}
              hint="Across the exact, semantic and archive layers."
            />
            <StatCard
              label="Replan changed plan"
              value={replan?.selection_changed ?? 0}
              unit={"of " + (replan?.plans_total ?? 0) + " plans"}
              tone="warm"
              icon={Zap}
              hint="Times the marginal-cost ranking disagreed with the cold-cost ranking. This is the thesis."
            />
          </>
        )}
      </motion.div>

      {/* ---------------------------------------------- thesis callout */}
      {replan && replan.selection_changed > 0 ? (
        <motion.div variants={itemVariants}>
          <Card className="border-warm/40 bg-warm-ghost/20">
            <CardBody className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-warm/40 bg-warm-ghost">
                  <Zap className="size-4 text-warm" />
                </div>
                <div>
                  <p className="text-[13px] font-semibold text-ink">
                    Cache-aware replanning changed the selected plan{" "}
                    {replan.selection_changed} {fmt.plural(replan.selection_changed, "time")}
                  </p>
                  <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-ink-muted text-pretty">
                    In {fmt.percent(replan.selection_changed_ratio)} of plans, ranking candidates
                    on marginal cost produced a different winner than ranking them on cold cost.
                    A cache hit on the same plan would not count: this is a different plan being
                    chosen because of what was already warm.
                  </p>
                </div>
              </div>
              <Button asChild variant="secondary" size="sm">
                <Link to="/app/runs?changed=true">
                  See those runs
                  <ArrowRight />
                </Link>
              </Button>
            </CardBody>
          </Card>
        </motion.div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* -------------------------------------------- recent runs */}
        <Section
          title="Recent runs"
          icon={Activity}
          description="Cold cost against what was actually spent."
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link to="/app/runs">
                All runs
                <ArrowRight />
              </Link>
            </Button>
          }
        >
          <Card>
            {dashboard.isLoading ? (
              <CardBody className="space-y-2">
                {Array.from({ length: 5 }).map((_, index) => (
                  <Skeleton key={index} className="h-9" />
                ))}
              </CardBody>
            ) : data?.recent_runs.length ? (
              <ul className="divide-y divide-line">
                {data.recent_runs.map((run) => (
                  <li key={run.id}>
                    <Link
                      to={"/app/runs/" + run.id}
                      className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-raised"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] text-ink">{run.intent}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-2.5">
                          <StatusDot status={run.status} />
                          <ModeBadge mode={run.mode} />
                          <span className="text-[11px] text-ink-subtle">
                            {fmt.ago(run.created_at)}
                          </span>
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <CostComparison
                          naive={run.naive_cost}
                          marginal={run.marginal_cost}
                          compact
                        />
                        <p className="mono mt-1 text-[11px] tabular text-ink-subtle">
                          spent {fmt.credits(run.credits_spent)}
                        </p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <CardBody>
                <EmptyState
                  icon={Search}
                  title="No runs yet"
                  description="A run is one executed plan: the engines chosen, the cache layers that served each step, and what it cost. Run a search to create the first one."
                  action={
                    <Button asChild variant="primary" size="sm">
                      <Link to="/app/search">
                        <Search />
                        Run a search
                      </Link>
                    </Button>
                  }
                />
              </CardBody>
            )}
          </Card>
        </Section>

        <div className="space-y-5">
          {/* ------------------------------------- cache distribution */}
          <Section
            title="Cache layer distribution"
            icon={Database}
            description="Only the live layer spends credits."
          >
            <Card>
              <CardBody>
                {dashboard.isLoading ? (
                  <Skeleton className="h-52" />
                ) : (
                  <LayerDonut layers={data?.cache_layers ?? {}} />
                )}
              </CardBody>
            </Card>
          </Section>

          {/* ------------------------------------------ upstream quota */}
          <Section
            title="Budget and upstream quota"
            icon={Server}
            description="Two different numbers. SerpFlow's ledger is not the SerpApi account."
          >
            <Card>
              <CardBody className="space-y-4">
                {data?.projected_exhaustion ? (
                  <div className="space-y-1.5">
                    <div className="flex items-baseline justify-between">
                      <span className="text-[12px] text-ink-muted">
                        SerpFlow {data.projected_exhaustion.scope} budget
                      </span>
                      <span className="mono text-[12px] tabular text-ink">
                        {fmt.credits(data.projected_exhaustion.remaining)} left
                      </span>
                    </div>
                    <UtilizationBar
                      used={Math.max(0, 250 - data.projected_exhaustion.remaining)}
                      limit={250}
                      alertAt={0.8}
                    />
                    <p className="text-[11px] text-ink-subtle">
                      {data.projected_exhaustion.exhausts_at
                        ? "At the current burn rate of " +
                          data.projected_exhaustion.burn_rate_per_hour +
                          " credits an hour, this exhausts " +
                          fmt.ago(data.projected_exhaustion.exhausts_at) +
                          "."
                        : (data.projected_exhaustion.note ?? "No spend recorded yet.")}
                    </p>
                  </div>
                ) : null}

                {data?.upstream_quota.length ? (
                  data.upstream_quota.map((quota) => (
                    <div
                      key={quota.credential_id}
                      className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[12px] text-ink">{quota.name}</span>
                        <Badge tone="outline" className="mono">
                          ...{quota.fingerprint.slice(-4)}
                        </Badge>
                      </div>
                      <div className="mt-1.5 flex items-baseline justify-between">
                        <span className="text-[11px] text-ink-subtle">SerpApi searches left</span>
                        <span className="mono text-[12px] tabular text-ink">
                          {quota.upstream_searches_left ?? "unknown"}
                        </span>
                      </div>
                      {quota.divergence !== null && quota.divergence !== undefined ? (
                        <Tooltip content="The two diverge the moment this credential is used outside SerpFlow. Surfacing that is the point.">
                          <p className="mt-1 inline-flex items-center gap-1 text-[11px] text-caution">
                            <AlertTriangle className="size-3" />
                            ledger diverges by {quota.divergence}
                          </p>
                        </Tooltip>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-[12px] text-ink-subtle text-pretty">
                    No upstream credential is attached, so there is no SerpApi quota to
                    reconcile against. Test API keys run against the deterministic mock and
                    spend nothing.
                  </p>
                )}
              </CardBody>
            </Card>
          </Section>
        </div>
      </div>

      {/* -------------------------------------------- spend by project */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Section
          title="Spend by project"
          icon={BarChart3}
          description="Spend is attributed to the project that fetched."
        >
          <Card>
            <CardBody>
              {dashboard.isLoading ? (
                <Skeleton className="h-56" />
              ) : (
                <HorizontalBars
                  data={(data?.spend_by_project ?? []).map((row) => ({
                    label: row.project_name,
                    value: row.spent,
                  }))}
                  color="var(--color-spend)"
                  formatter={(value) => fmt.credits(value) + " cr"}
                />
              )}
            </CardBody>
          </Card>
        </Section>

        <Section
          title="Cross-project cache benefit"
          icon={Network}
          description="Savings are attributed to the project that benefited."
        >
          <Card>
            <CardBody>
              {crossProject.isLoading ? (
                <Skeleton className="h-56" />
              ) : crossProject.data?.flows.length ? (
                <div className="space-y-2">
                  <p className="text-[12px] text-ink-muted">
                    <span className="mono font-semibold text-warm">
                      {fmt.credits(crossProject.data.total_credits)}
                    </span>{" "}
                    credits of one project's upstream spend benefited another.
                  </p>
                  {crossProject.data.flows.map((flow, index) => (
                    <div
                      key={index}
                      className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2 text-[12px]"
                    >
                      <span className="truncate text-ink-muted">
                        {flow.fetching_project_name}
                      </span>
                      <ArrowRight className="size-3 shrink-0 text-warm" />
                      <span className="truncate text-ink">{flow.beneficiary_project_name}</span>
                      <span className="mono ml-auto tabular text-warm">
                        {fmt.credits(flow.credits)} cr
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Network}
                  title="No cross-project benefit yet"
                  description="With an organization-level shared cache, one project's upstream spend can serve another's requests. That crosses a billing and data boundary, so it is off by default and enabled per project in Settings."
                />
              )}
            </CardBody>
          </Card>
        </Section>
      </div>

      {/* ------------------------------------------------ active alerts */}
      {data?.active_alerts.length ? (
        <Section title="Active alerts" icon={AlertTriangle}>
          <Card>
            <ul className="divide-y divide-line">
              {data.active_alerts.map((alert) => (
                <li key={alert.id} className="flex items-start gap-3 px-4 py-3">
                  <Badge
                    tone={
                      alert.severity === "critical"
                        ? "danger"
                        : alert.severity === "warning"
                          ? "caution"
                          : "outline"
                    }
                  >
                    {alert.severity}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-ink">{alert.title}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                      {alert.message}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] text-ink-subtle">
                    {fmt.ago(alert.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </Section>
      ) : null}

      {/* ----------------------------------------------- getting started */}
      {!data?.recent_runs.length && !dashboard.isLoading ? (
        <Section title="Where to go next" icon={GitBranch}>
          <div className="grid gap-3 sm:grid-cols-3">
            <NextStep
              to="/app/catalog"
              icon={Network}
              title="Catalog"
              description={
                "Browse the engines, their typed dependency edges, and which ones compete. " +
                (me?.organization?.name ?? "Your organization") +
                " can route to any of them."
              }
            />
            <NextStep
              to="/app/benchmarks"
              icon={GitBranch}
              title="Benchmarks"
              description="120 hand-authored routing tasks, scored against an unaided model and an embedding-only baseline."
            />
            <NextStep
              to="/app/settings/api-keys"
              icon={Zap}
              title="API keys"
              description="A test key routes to the deterministic mock and spends zero SerpApi credits, so you can integrate before connecting a paid account."
            />
          </div>
        </Section>
      ) : null}
    </motion.div>
  );
}

function NextStep({
  to,
  icon: Icon,
  title,
  description,
}: {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Link
      to={to}
      className="group rounded-[var(--radius-md)] border border-line bg-surface p-4 transition-colors hover:border-accent-muted hover:bg-surface-raised"
    >
      <Icon className="size-4 text-ink-subtle group-hover:text-accent" />
      <p className="mt-2.5 text-[13px] font-semibold text-ink">{title}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-ink-subtle text-pretty">
        {description}
      </p>
    </Link>
  );
}
