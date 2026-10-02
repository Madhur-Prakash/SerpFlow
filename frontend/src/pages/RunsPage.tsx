/** Run history with the filters an operator actually reaches for. */

import { motion } from "framer-motion";
import { Activity, Filter, Search, Zap } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";

import { itemVariants, listVariants } from "@/animations";
import {
  CostComparison,
  EmptyState,
  ErrorMessage,
  ModeBadge,
  PageHeader,
  StatusDot,
} from "@/components/shared";
import {
  Badge,
  Button,
  Card,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@/components/ui";
import { useRuns } from "@/hooks/useQueries";
import * as fmt from "@/lib/format";

export function RunsPage() {
  const [params, setParams] = useSearchParams();
  const [engine, setEngine] = React.useState(params.get("engine") ?? "");
  const [status, setStatus] = React.useState(params.get("status") ?? "all");
  const changedOnly = params.get("changed") === "true";
  const [page, setPage] = React.useState(0);
  const limit = 25;

  const runs = useRuns({
    limit,
    offset: page * limit,
    status: status === "all" ? undefined : status,
    engine: engine || undefined,
    changed_selection: changedOnly ? true : undefined,
  });

  function toggleChanged() {
    const next = new URLSearchParams(params);
    if (changedOnly) next.delete("changed");
    else next.set("changed", "true");
    setParams(next);
    setPage(0);
  }

  if (runs.isError) {
    return <ErrorMessage error={runs.error} onRetry={() => runs.refetch()} />;
  }

  const items = runs.data?.items ?? [];
  const total = runs.data?.total ?? 0;

  return (
    <motion.div
      variants={listVariants}
      initial="initial"
      animate="animate"
      className="space-y-6"
    >
      <PageHeader
        title="Runs"
        icon={Activity}
        description="Every executed plan, with what it would have cost cold and what it actually spent."
        actions={
          <Button asChild variant="primary" size="sm">
            <Link to="/app/search">
              <Search />
              New search
            </Link>
          </Button>
        }
      />

      <motion.div variants={itemVariants} className="flex flex-wrap items-center gap-2">
        <div className="relative w-56">
          <Filter className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-subtle" />
          <Input
            value={engine}
            onChange={(event) => {
              setEngine(event.target.value);
              setPage(0);
            }}
            placeholder="Filter by engine"
            className="pl-8"
          />
        </div>

        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value);
            setPage(0);
          }}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Any status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any status</SelectItem>
            <SelectItem value="succeeded">Succeeded</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="planned">Planned</SelectItem>
          </SelectContent>
        </Select>

        <Button
          variant={changedOnly ? "primary" : "outline"}
          size="md"
          onClick={toggleChanged}
        >
          <Zap />
          Replan changed the plan
        </Button>

        <span className="ml-auto text-[12px] text-ink-subtle">
          {total} {fmt.plural(total, "run")}
        </span>
      </motion.div>

      <motion.div variants={itemVariants}>
        <Card>
          {runs.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 8 }).map((_, index) => (
                <Skeleton key={index} className="h-11" />
              ))}
            </div>
          ) : items.length ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] text-left">
                  <thead>
                    <tr className="border-b border-line text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                      <th className="px-4 py-2.5 font-medium">Intent</th>
                      <th className="px-3 py-2.5 font-medium">Status</th>
                      <th className="px-3 py-2.5 font-medium">Mode</th>
                      <th className="px-3 py-2.5 font-medium">Cost</th>
                      <th className="px-3 py-2.5 text-right font-medium">Spent</th>
                      <th className="px-3 py-2.5 text-right font-medium">Duration</th>
                      <th className="px-4 py-2.5 text-right font-medium">When</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {items.map((run) => (
                      <tr
                        key={run.id}
                        className="group transition-colors hover:bg-surface-raised"
                      >
                        <td className="max-w-md px-4 py-2.5">
                          <Link
                            to={"/app/runs/" + run.id}
                            className="block truncate text-[13px] text-ink group-hover:text-accent-strong"
                          >
                            {run.intent}
                          </Link>
                          <span className="mono text-[10px] text-ink-subtle">
                            {fmt.shortId(run.id)}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <StatusDot status={run.status} />
                          {run.error_code ? (
                            <Badge tone="danger" className="mono mt-1">
                              {run.error_code}
                            </Badge>
                          ) : null}
                        </td>
                        <td className="px-3 py-2.5">
                          <ModeBadge mode={run.mode} />
                        </td>
                        <td className="px-3 py-2.5">
                          <CostComparison
                            naive={run.naive_cost}
                            marginal={run.marginal_cost}
                            compact
                          />
                        </td>
                        <td className="px-3 py-2.5 text-right mono tabular text-[12px] text-spend">
                          {fmt.credits(run.credits_spent)}
                        </td>
                        <td className="px-3 py-2.5 text-right mono tabular text-[12px] text-ink-subtle">
                          {fmt.ms(run.duration_ms)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-[12px] text-ink-subtle">
                          {fmt.ago(run.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {total > limit ? (
                <div className="flex items-center justify-between border-t border-line px-4 py-2.5">
                  <span className="text-[12px] text-ink-subtle">
                    {page * limit + 1} to {Math.min((page + 1) * limit, total)} of {total}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page === 0}
                      onClick={() => setPage((value) => Math.max(0, value - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={(page + 1) * limit >= total}
                      onClick={() => setPage((value) => value + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="p-4">
              <EmptyState
                icon={Activity}
                title={changedOnly ? "No replan changes recorded yet" : "No runs yet"}
                description={
                  changedOnly
                    ? "This filter shows runs where ranking candidates on marginal cost produced a different winner than ranking them on cold cost. It needs a warm cache: run the same intent twice, or run the reference demo with make demo."
                    : "A run is one executed plan: the engines chosen, the cache layer that served each step, and what it cost. Run a search to create the first one."
                }
                action={
                  <Button asChild variant="primary" size="sm">
                    <Link to="/app/search">
                      <Search />
                      Run a search
                    </Link>
                  </Button>
                }
              />
            </div>
          )}
        </Card>
      </motion.div>
    </motion.div>
  );
}
