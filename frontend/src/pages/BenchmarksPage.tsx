/**
 * Benchmarks (section 53).
 *
 * Accuracy is reported honestly, including the failure analysis. An honest 78%
 * with an error breakdown is more credible than an unqualified claim.
 */

import { motion } from "framer-motion";
import { GitBranch, Play, Target, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { itemVariants, listVariants } from "@/animations";
import { AccuracyRadar, HorizontalBars } from "@/components/charts";
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
  Input,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
} from "@/components/ui";
import { useBenchmarks, useBenchmarkTasks } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { PERMISSIONS, useSession } from "@/stores/session";
import type { BenchmarkRun } from "@/types/api";

const SYSTEM_LABEL: Record<string, string> = {
  serpflow: "SerpFlow planner",
  unaided_llm: "Unaided model",
  embedding_only: "Embedding only",
};

const SYSTEM_NOTE: Record<string, string> = {
  serpflow: "The full pipeline: retrieval, selection, synthesis and typed path-finding.",
  unaided_llm:
    "A frontier model writing SerpApi calls with no catalog, no dependency edges and no substitutes.",
  embedding_only:
    "Retrieval with no selector and no path-finding. It has no way to discover a second hop.",
};

const FAILURE_NOTE: Record<string, string> = {
  wrong_engine: "Routed to an engine that does not answer the intent.",
  missing_hop: "Stopped short of the chain the answer needed.",
  extra_hop: "Added a hop the intent did not require.",
  locale_miss: "Right engine, wrong locale parameters.",
  freshness_miss: "Right engine and parameters, wrong freshness bound.",
  no_plan: "Produced no valid plan at all.",
};

export function BenchmarksPage() {
  const { can } = useSession();
  const benchmarks = useBenchmarks();
  const [category, setCategory] = React.useState("");
  const tasks = useBenchmarkTasks({ category: category || undefined, limit: 50 });
  const [running, setRunning] = React.useState<string | null>(null);

  const canRun = can(PERMISSIONS.benchmarkRun);

  async function run(system: string) {
    setRunning(system);
    try {
      const result = await api.runBenchmark({ system, suite_version: "v1" });
      toast.success(SYSTEM_LABEL[system] + " scored " + fmt.percent(result.accuracy), {
        description: result.notes,
      });
      benchmarks.refetch();
    } catch (error) {
      toast.error("Benchmark failed", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setRunning(null);
    }
  }

  if (benchmarks.isError) {
    return <ErrorMessage error={benchmarks.error} onRetry={() => benchmarks.refetch()} />;
  }

  // Latest run per system.
  const latest = new Map<string, BenchmarkRun>();
  for (const run of benchmarks.data ?? []) {
    if (!latest.has(run.system)) latest.set(run.system, run);
  }
  const serpflow = latest.get("serpflow");
  const unaided = latest.get("unaided_llm");

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Benchmarks"
        icon={GitBranch}
        description="120 hand-authored routing tasks, committed as versioned fixtures and scored against two baselines. The suite makes real LLM calls, so it runs on demand rather than in CI."
        actions={
          canRun ? (
            <div className="flex gap-1.5">
              {["unaided_llm", "embedding_only", "serpflow"].map((system) => (
                <Button
                  key={system}
                  variant={system === "serpflow" ? "primary" : "outline"}
                  size="sm"
                  onClick={() => run(system)}
                  disabled={Boolean(running)}
                >
                  <Play />
                  {running === system ? "Running" : SYSTEM_LABEL[system]}
                </Button>
              ))}
            </div>
          ) : null
        }
      />

      {/* ------------------------------------------- headline numbers */}
      <motion.div variants={itemVariants} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {benchmarks.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-28" />)
        ) : (
          <>
            <StatCard
              label="SerpFlow accuracy"
              value={serpflow ? fmt.percent(serpflow.accuracy) : "not run"}
              animate={false}
              tone="accent"
              icon={Target}
              hint={serpflow ? serpflow.task_count + " labelled tasks" : undefined}
            />
            <StatCard
              label="Unaided model"
              value={unaided ? fmt.percent(unaided.accuracy) : "not run"}
              animate={false}
              icon={GitBranch}
              hint="No catalog, no dependency edges, no substitutes."
            />
            <StatCard
              label="Engine accuracy"
              value={serpflow ? fmt.percent(serpflow.engine_accuracy) : "-"}
              animate={false}
              hint="Chain matched exactly, or matched an acceptable alternative."
            />
            <StatCard
              label="Locale accuracy"
              value={serpflow ? fmt.percent(serpflow.param_accuracy) : "-"}
              animate={false}
              hint="gl and hl inferred correctly. A wrong gl silently changes the result set."
            />
          </>
        )}
      </motion.div>

      <Tabs defaultValue="results">
        <TabsList>
          <TabsTrigger value="results">
            <Target />
            Results
          </TabsTrigger>
          <TabsTrigger value="failures">
            <XCircle />
            Failure analysis
          </TabsTrigger>
          <TabsTrigger value="tasks">
            <GitBranch />
            Task set
          </TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------- results */}
        <TabsContent value="results" className="pt-4">
          {latest.size ? (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <Card>
                <CardHeader
                  title="Accuracy by category"
                  description="Where each system actually differs."
                />
                <CardBody>
                  <AccuracyRadar
                    systems={[...latest.entries()]
                      .sort(([a], [b]) =>
                        a === "serpflow" ? 1 : b === "serpflow" ? -1 : 0,
                      )
                      .map(([system, run]) => ({
                        name: SYSTEM_LABEL[system] ?? system,
                        values: Object.fromEntries(
                          Object.entries(run.by_category).map(([name, bucket]) => [
                            name,
                            (bucket as { accuracy: number }).accuracy,
                          ]),
                        ),
                      }))}
                  />
                </CardBody>
              </Card>

              <div className="space-y-4">
                {[...latest.entries()].map(([system, run]) => (
                  <Card key={run.id}>
                    <CardHeader
                      title={SYSTEM_LABEL[system] ?? system}
                      description={SYSTEM_NOTE[system]}
                      action={
                        <Badge tone={system === "serpflow" ? "accent" : "outline"} className="mono">
                          {fmt.percent(run.accuracy)}
                        </Badge>
                      }
                    />
                    <CardBody className="space-y-2">
                      <Metric label="Correct" value={run.correct_count + " / " + run.task_count} />
                      <Metric label="Engine accuracy" value={fmt.percent(run.engine_accuracy)} />
                      <Metric label="Parameter accuracy" value={fmt.percent(run.param_accuracy)} />
                      <Metric
                        label="Freshness accuracy"
                        value={fmt.percent(run.freshness_accuracy)}
                      />
                      <Metric label="Mean latency" value={fmt.ms(run.mean_latency_ms)} />
                      <Metric label="Catalog" value={run.catalog_version} />
                      <Metric label="Model" value={run.llm_model || "deterministic"} />
                    </CardBody>
                  </Card>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Target}
              title="No benchmark runs yet"
              description="The suite scores three systems on the same 120 tasks: an unaided model with no catalog, retrieval with no selector or path-finding, and the full SerpFlow pipeline. Run it to see where the catalog actually earns its keep."
              action={
                canRun ? (
                  <Button variant="primary" size="sm" onClick={() => run("serpflow")}>
                    <Play />
                    Run SerpFlow
                  </Button>
                ) : null
              }
            />
          )}
        </TabsContent>

        {/* ------------------------------------------------ failures */}
        <TabsContent value="failures" className="pt-4">
          {serpflow && Object.keys(serpflow.failure_modes).length ? (
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader
                  title="Failure modes"
                  icon={XCircle}
                  description="Reported in full. An honest number with its error analysis is more useful than a round one."
                />
                <CardBody>
                  <HorizontalBars
                    data={Object.entries(serpflow.failure_modes).map(([mode, count]) => ({
                      label: mode.replace(/_/g, " "),
                      value: Number(count),
                    }))}
                    color="var(--color-danger)"
                    formatter={(value) => value + " tasks"}
                  />
                </CardBody>
              </Card>

              <Card>
                <CardHeader title="What each mode means" />
                <CardBody className="space-y-2">
                  {Object.entries(serpflow.failure_modes)
                    .sort(([, a], [, b]) => Number(b) - Number(a))
                    .map(([mode, count]) => (
                      <div
                        key={mode}
                        className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="mono text-[12px] text-ink">
                            {mode.replace(/_/g, " ")}
                          </span>
                          <Badge tone="danger" className="mono">
                            {String(count)}
                          </Badge>
                        </div>
                        <p className="mt-1 text-[12px] text-ink-subtle text-pretty">
                          {FAILURE_NOTE[mode] ?? "Unclassified failure."}
                        </p>
                      </div>
                    ))}
                  {serpflow.notes ? (
                    <p className="pt-2 text-[12px] leading-relaxed text-ink-muted text-pretty">
                      {serpflow.notes}
                    </p>
                  ) : null}
                </CardBody>
              </Card>
            </div>
          ) : (
            <EmptyState
              icon={XCircle}
              title="No failures recorded"
              description="Either the suite has not been run, or every task passed. Run it and check: a 100% score on 120 hand-authored tasks usually means the suite is too easy, not that the router is perfect."
            />
          )}
        </TabsContent>

        {/* --------------------------------------------------- tasks */}
        <TabsContent value="tasks" className="pt-4">
          <div className="space-y-3">
            <Input
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder="Filter by category: single_engine, multi_hop, locale, freshness, substitute"
              className="max-w-lg"
            />
            <Card>
              {tasks.isLoading ? (
                <CardBody className="space-y-2">
                  {Array.from({ length: 8 }).map((_, index) => (
                    <Skeleton key={index} className="h-12" />
                  ))}
                </CardBody>
              ) : tasks.data?.items.length ? (
                <ul className="divide-y divide-line">
                  {tasks.data.items.map((task) => (
                    <li key={task.id} className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="mono text-[11px] text-ink-subtle">
                          {task.task_key}
                        </span>
                        <Badge tone="outline">{task.category.replace(/_/g, " ")}</Badge>
                        <Badge tone="outline">{task.difficulty}</Badge>
                        {task.expected_freshness ? (
                          <Badge tone="accent">{task.expected_freshness}</Badge>
                        ) : null}
                        {Object.entries(task.expected_params).map(([key, value]) => (
                          <Badge key={key} tone="outline" className="mono">
                            {key}={value}
                          </Badge>
                        ))}
                      </div>
                      <p className="mt-1.5 text-[13px] text-ink">{task.intent}</p>
                      <p className="mono mt-1 text-[11px] text-accent-strong">
                        {task.expected_engines.join(" -> ")}
                        {task.acceptable_alternatives.length
                          ? "   also accepts " +
                            task.acceptable_alternatives
                              .map((chain) => chain.join(" -> "))
                              .join(" | ")
                          : ""}
                      </p>
                      {task.notes ? (
                        <Tooltip content="What this task is actually testing.">
                          <p className="mt-1 text-[11px] text-ink-subtle text-pretty">
                            {task.notes}
                          </p>
                        </Tooltip>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <CardBody>
                  <EmptyState
                    icon={GitBranch}
                    title="No tasks loaded"
                    description="The task set is committed under backend/fixtures/benchmark and loaded by make seed. Run the seed to populate it."
                  />
                </CardBody>
              )}
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-1.5 last:border-0">
      <span className="text-[12px] text-ink-subtle">{label}</span>
      <span className="mono text-[12px] tabular text-ink">{value}</span>
    </div>
  );
}

export { Section };
