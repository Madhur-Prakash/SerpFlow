/** Analytics (section 52). Every figure is computed, never hand-written. */

import { motion } from "framer-motion";
import {
  BarChart3,
  Gauge,
  Network,
  Thermometer,
  TrendingDown,
  Zap,
} from "lucide-react";
import * as React from "react";

import { itemVariants, listVariants } from "@/animations";
import { HorizontalBars, SavingsWaterfall } from "@/components/charts";
import {
  EmptyState,
  ErrorMessage,
  PageHeader,
  Section,
  StatCard,
} from "@/components/shared";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
} from "@/components/ui";
import {
  useDashboard,
  useEngineReach,
  useRoutingQuality,
  useSavings,
  useVolatility,
} from "@/hooks/useQueries";
import * as fmt from "@/lib/format";

const WINDOWS = [7, 30, 90] as const;

export function AnalyticsPage() {
  const [days, setDays] = React.useState<number>(30);
  const savings = useSavings(days);
  const dashboard = useDashboard(days);
  const reach = useEngineReach();
  const routing = useRoutingQuality();
  const volatility = useVolatility(90);

  if (savings.isError) {
    return <ErrorMessage error={savings.error} onRetry={() => savings.refetch()} />;
  }

  const data = savings.data;
  const replan = dashboard.data?.marginal_replanning;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Analytics"
        icon={BarChart3}
        description="Where the credits went, where they were avoided, and how much of the catalog this organization actually reaches."
        actions={
          <div className="flex gap-1">
            {WINDOWS.map((window) => (
              <Button
                key={window}
                variant={days === window ? "primary" : "outline"}
                size="sm"
                onClick={() => setDays(window)}
              >
                {window}d
              </Button>
            ))}
          </div>
        }
      />

      <motion.div variants={itemVariants} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {savings.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-28" />)
        ) : (
          <>
            <StatCard
              label="Naive execution"
              value={data?.naive_execution ?? 0}
              unit="cr"
              icon={Gauge}
              hint="What every step would have cost with no routing and no cache."
            />
            <StatCard
              label="Actual spend"
              value={data?.actual_spend ?? 0}
              unit="cr"
              tone="spend"
              icon={BarChart3}
            />
            <StatCard
              label="Total saved"
              value={data?.total_saved ?? 0}
              unit="cr"
              tone="warm"
              icon={TrendingDown}
            />
            <StatCard
              label="Replan changed plan"
              value={replan?.selection_changed ?? 0}
              unit={"of " + (replan?.plans_total ?? 0)}
              tone="warm"
              icon={Zap}
              hint="Marginal-cost ranking disagreeing with cold-cost ranking."
            />
          </>
        )}
      </motion.div>

      {/* ------------------------------------------ savings waterfall */}
      <Section
        title="Savings decomposition"
        icon={TrendingDown}
        description="Naive execution, less routing savings, less each cache layer, down to what was actually spent."
      >
        <Card>
          <CardBody>
            {savings.isLoading ? (
              <Skeleton className="h-64" />
            ) : data?.naive_execution ? (
              <>
                <SavingsWaterfall steps={data.waterfall} />
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(data.by_source).map(([source, credits]) => (
                    <Badge key={source} tone={credits > 0 ? "warm" : "outline"} className="mono">
                      {source} {fmt.credits(credits)}
                    </Badge>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                icon={TrendingDown}
                title="Nothing to decompose yet"
                description="This chart separates the credits avoided by better routing from the credits avoided by each cache layer. Run a few searches and it fills in."
              />
            )}
          </CardBody>
        </Card>
      </Section>

      <Tabs defaultValue="reach">
        <TabsList>
          <TabsTrigger value="reach">
            <Network />
            Engine reach
          </TabsTrigger>
          <TabsTrigger value="routing">
            <Gauge />
            Routing quality
          </TabsTrigger>
          <TabsTrigger value="volatility">
            <Thermometer />
            Volatility and TTL
          </TabsTrigger>
        </TabsList>

        {/* --------------------------------------------------- reach */}
        <TabsContent value="reach" className="pt-4">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <Card>
              <CardHeader
                title="Catalog coverage"
                icon={Network}
                description="How much of the catalog this organization actually uses."
              />
              <CardBody className="space-y-3">
                {reach.isLoading ? (
                  <Skeleton className="h-28" />
                ) : (
                  <>
                    <div className="flex items-baseline gap-2">
                      <span className="mono text-3xl font-semibold tabular text-accent-strong">
                        {fmt.percent(reach.data?.reach_ratio ?? 0, 0)}
                      </span>
                      <span className="text-[12px] text-ink-subtle">
                        {reach.data?.engines_used ?? 0} of{" "}
                        {reach.data?.catalog_engines ?? 0} engines
                      </span>
                    </div>
                    <p className="text-[12px] leading-relaxed text-ink-subtle text-pretty">
                      In the SerpApi community showcase, 111 of 185 projects use only
                      engine=google out of 62 available engines. This number is the direct
                      counterpart: how many distinct engines your own traffic actually touches.
                    </p>
                  </>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Calls by engine" icon={BarChart3} />
              <CardBody>
                {reach.isLoading ? (
                  <Skeleton className="h-64" />
                ) : reach.data?.usage.length ? (
                  <HorizontalBars
                    data={reach.data.usage.slice(0, 10).map((row) => ({
                      label: row.engine,
                      value: row.calls,
                    }))}
                    formatter={(value) => value + " calls"}
                  />
                ) : (
                  <EmptyState
                    icon={Network}
                    title="No engine usage yet"
                    description="Once runs execute, this shows which engines your traffic actually reaches, and how concentrated it is."
                  />
                )}
              </CardBody>
            </Card>
          </div>
        </TabsContent>

        {/* ------------------------------------------------- routing */}
        <TabsContent value="routing" className="pt-4">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Live routing signal"
                icon={Gauge}
                description="Confidence and candidate plurality across the plans this organization has generated."
              />
              <CardBody className="space-y-3">
                {routing.isLoading ? (
                  <Skeleton className="h-32" />
                ) : (
                  <>
                    <Row
                      label="Plans generated"
                      value={fmt.credits(routing.data?.live.plans ?? 0)}
                    />
                    <Row
                      label="Mean selector confidence"
                      value={(routing.data?.live.mean_confidence ?? 0).toFixed(3)}
                    />
                    <Row
                      label="Mean candidates per plan"
                      value={(routing.data?.live.mean_candidate_count ?? 0).toFixed(2)}
                    />
                    <Row
                      label="Rejected alternatives recorded"
                      value={fmt.credits(routing.data?.live.rejected_alternatives ?? 0)}
                    />
                    <p className="pt-1 text-[11px] leading-relaxed text-ink-subtle text-pretty">
                      A mean candidate count at or below 1.0 means the planner is routinely
                      finding only one viable route, which leaves marginal replanning nothing
                      to re-rank.
                    </p>
                  </>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Benchmark accuracy by catalog version"
                icon={BarChart3}
                description="Tracked per catalog version so a routing regression is attributable."
              />
              <CardBody className="space-y-3">
                {routing.data?.benchmarks.length ? (
                  routing.data.benchmarks.map((entry) => (
                    <div
                      key={entry.catalog_version}
                      className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5"
                    >
                      <p className="mono text-[12px] text-ink">{entry.catalog_version}</p>
                      <div className="mt-2 space-y-1.5">
                        {Object.entries(entry.systems).map(([system, run]) => (
                          <div key={system} className="flex items-center gap-2">
                            <span className="w-32 shrink-0 text-[11px] text-ink-subtle">
                              {fmt.titleCase(system)}
                            </span>
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                              <div
                                className={
                                  "h-full " +
                                  (system === "serpflow" ? "bg-accent" : "bg-ink-subtle")
                                }
                                style={{ width: (run.accuracy * 100).toFixed(1) + "%" }}
                              />
                            </div>
                            <span className="mono w-12 shrink-0 text-right text-[11px] tabular text-ink">
                              {fmt.percent(run.accuracy, 1)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    icon={Gauge}
                    title="No benchmark results yet"
                    description="The benchmark makes real LLM calls, so it runs on demand rather than in CI. Run make benchmark, or trigger it from the Benchmarks page."
                  />
                )}
              </CardBody>
            </Card>
          </div>
        </TabsContent>

        {/* ---------------------------------------------- volatility */}
        <TabsContent value="volatility" className="pt-4">
          <Card>
            <CardHeader
              title="Measured volatility"
              icon={Thermometer}
              description="TTL is learned per engine and query class, not per engine alone: a volatile query on a stable engine still needs a short TTL."
              action={
                volatility.data?.ttl_movement ? (
                  <div className="flex gap-1.5">
                    {Object.entries(volatility.data.ttl_movement).map(([direction, count]) => (
                      <Badge
                        key={direction}
                        tone={
                          direction === "extended"
                            ? "warm"
                            : direction === "shortened"
                              ? "caution"
                              : "outline"
                        }
                        className="mono"
                      >
                        {direction} {count}
                      </Badge>
                    ))}
                  </div>
                ) : null
              }
            />
            <CardBody>
              {volatility.isLoading ? (
                <Skeleton className="h-56" />
              ) : volatility.data?.by_engine_class.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px] text-left">
                    <thead>
                      <tr className="border-b border-line text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                        <th className="pb-2 pr-3 font-medium">Engine</th>
                        <th className="pb-2 pr-3 font-medium">Query class</th>
                        <th className="pb-2 pr-3 text-right font-medium">Observations</th>
                        <th className="pb-2 pr-3 text-right font-medium">Mean TTL</th>
                        <th className="pb-2 pr-3 text-right font-medium">Mean churn</th>
                        <th className="pb-2 text-right font-medium">Measured interval</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {(
                        volatility.data.by_engine_class as {
                          engine: string;
                          query_class: string;
                          observations: number;
                          mean_ttl_seconds: number;
                          mean_churn: number;
                          measured_refresh_interval_seconds: number;
                        }[]
                      ).map((row, index) => (
                        <tr key={index} className="text-[12px]">
                          <td className="py-2 pr-3 mono text-ink">{row.engine}</td>
                          <td className="py-2 pr-3 text-ink-muted">{row.query_class}</td>
                          <td className="py-2 pr-3 text-right mono tabular text-ink-subtle">
                            {row.observations}
                          </td>
                          <td className="py-2 pr-3 text-right mono tabular text-ink">
                            {fmt.seconds(row.mean_ttl_seconds)}
                          </td>
                          <td className="py-2 pr-3 text-right mono tabular text-ink-subtle">
                            {fmt.percent(row.mean_churn)}
                          </td>
                          <td className="py-2 text-right mono tabular text-ink-subtle">
                            {fmt.seconds(row.measured_refresh_interval_seconds)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  icon={Thermometer}
                  title="No TTL observations yet"
                  description="Each time a cached entry is refreshed, SerpFlow compares the new top ten against the old one and moves the TTL: unchanged extends it by half again, significant churn halves it. Those decisions land here."
                />
              )}
            </CardBody>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-2 last:border-0">
      <span className="text-[12px] text-ink-subtle">{label}</span>
      <span className="mono text-[13px] tabular text-ink">{value}</span>
    </div>
  );
}

export { Tooltip };
