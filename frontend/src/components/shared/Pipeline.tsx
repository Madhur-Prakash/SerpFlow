/**
 * The execution pipeline (sections 42, 69).
 *
 * Every stage below advances because an SSE frame arrived saying it did. There
 * is no timer, no simulated sequence and no optimistic progression. If the
 * backend sits on "inspecting cache state" for two seconds, so does this.
 */

import { AnimatePresence, motion } from "framer-motion";
import { Check, Circle, Loader2, X } from "lucide-react";

import { prefersReducedMotion, transition } from "@/animations";
import { PIPELINE, type StageState } from "@/hooks/useRunStream";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  stages: Record<string, StageState>;
  currentStage: string | null;
  finished: boolean;
  failed: boolean;
  className?: string;
}

export function Pipeline({ stages, currentStage, finished, failed, className }: Props) {
  return (
    <ol className={cn("relative space-y-0", className)}>
      {PIPELINE.map((stage, index) => {
        const state = stages[stage.key];
        const status = state?.status ?? "pending";
        const isLast = index === PIPELINE.length - 1;
        const active = currentStage === stage.key && !finished;

        return (
          <li key={stage.key} className="relative flex gap-3 pb-3 last:pb-0">
            {!isLast ? (
              <span
                className={cn(
                  "absolute left-[11px] top-6 h-[calc(100%-12px)] w-px transition-colors duration-300",
                  status === "complete" ? "bg-warm/40" : "bg-line",
                )}
              />
            ) : null}

            <StageMarker status={status} failed={failed && active} />

            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                <p
                  className={cn(
                    "text-[13px] font-medium transition-colors",
                    status === "pending"
                      ? "text-ink-subtle"
                      : status === "failed"
                        ? "text-danger"
                        : "text-ink",
                  )}
                >
                  {stage.label}
                </p>
                {state ? (
                  <span className="mono text-[11px] tabular text-ink-subtle">
                    {fmt.ms(state.elapsedMs)}
                  </span>
                ) : null}
              </div>

              <p className="mt-0.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                {stage.description}
              </p>

              <AnimatePresence initial={false}>
                {state && status !== "pending" ? (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={transition(0.2)}
                    className="overflow-hidden"
                  >
                    <StageDetail stageKey={stage.key} detail={state.detail} />
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StageMarker({ status, failed }: { status: string; failed: boolean }) {
  return (
    <span
      className={cn(
        "relative z-10 mt-0.5 flex size-[22px] shrink-0 items-center justify-center rounded-full border transition-colors duration-300",
        status === "complete"
          ? "border-warm/50 bg-warm-ghost text-warm"
          : status === "running"
            ? "border-accent bg-accent-ghost text-accent-strong"
            : status === "failed" || failed
              ? "border-danger/50 bg-danger-ghost text-danger"
              : "border-line bg-surface text-ink-subtle",
      )}
    >
      {status === "complete" ? (
        <Check className="size-3" strokeWidth={3} />
      ) : status === "running" ? (
        <Loader2
          className={cn("size-3", prefersReducedMotion() ? "" : "animate-spin")}
          strokeWidth={2.5}
        />
      ) : status === "failed" || failed ? (
        <X className="size-3" strokeWidth={3} />
      ) : (
        <Circle className="size-1.5 fill-current" />
      )}
    </span>
  );
}

/** Each stage shows what it actually produced, straight from the SSE detail. */
function StageDetail({
  stageKey,
  detail,
}: {
  stageKey: string;
  detail: Record<string, unknown>;
}) {
  const chips: { label: string; tone?: "warm" | "accent" | "danger" | "neutral" }[] = [];

  const push = (label: string, tone?: "warm" | "accent" | "danger" | "neutral") =>
    chips.push({ label, tone });

  switch (stageKey) {
    case "finding_candidates": {
      const engines = detail.chosen as string[] | undefined;
      const count = detail.count as number | undefined;
      const fromSub = detail.from_substitution as string[] | undefined;
      if (count) push(count + " engines retrieved");
      if (fromSub?.length) push(fromSub.length + " pulled in as substitutes", "accent");
      engines?.forEach((engine) => push(engine, "accent"));
      if (detail.provider) push("via " + String(detail.provider));
      break;
    }
    case "synthesizing_parameters": {
      const params = detail.parameters as Record<string, unknown> | undefined;
      if (params) {
        for (const key of ["q", "location", "gl", "hl", "departure_id", "arrival_id", "date"]) {
          if (params[key]) push(key + "=" + String(params[key]));
        }
      }
      break;
    }
    case "inferring_freshness": {
      if (detail.freshness) push(String(detail.freshness), "accent");
      (detail.signals as string[] | undefined)?.slice(0, 2).forEach((signal) => push(signal));
      break;
    }
    case "finding_paths": {
      (detail.paths as string[] | undefined)?.forEach((path) => push(path));
      break;
    }
    case "generating_candidates": {
      const count = detail.candidate_count as number | undefined;
      if (count) push(count + " candidate plans", count > 1 ? "accent" : "danger");
      (detail.candidates as { label: string; cold_cost: number }[] | undefined)?.forEach(
        (candidate) => push(candidate.label + "  " + candidate.cold_cost + " cr cold"),
      );
      if (detail.single_candidate_reason) push(String(detail.single_candidate_reason), "danger");
      break;
    }
    case "inspecting_cache": {
      const warm = detail.warm_steps_found as number | undefined;
      if (warm !== undefined) push(warm + " warm steps found", warm ? "warm" : "neutral");
      break;
    }
    case "calculating_marginal_cost": {
      (
        detail.candidates as { plan: string; naive_cost: number; marginal_cost: number }[] | undefined
      )?.forEach((candidate) =>
        push(
          candidate.plan +
            "   cold " +
            candidate.naive_cost +
            "  marginal " +
            candidate.marginal_cost,
          candidate.marginal_cost < candidate.naive_cost ? "warm" : "neutral",
        ),
      );
      break;
    }
    case "reranking_plans": {
      if (detail.changed_selection) {
        push("marginal ranking chose a different plan", "warm");
      }
      if (detail.cold_winner) push("cold winner: " + String(detail.cold_winner));
      if (detail.selected) push("selected: " + String(detail.selected), "accent");
      break;
    }
    case "checking_budget": {
      if (detail.budget) push("budget " + String(detail.budget) + " credits");
      if (detail.selected_plan_cost !== undefined) {
        push("costs " + String(detail.selected_plan_cost) + " on the margin", "warm");
      }
      (detail.reductions as { engine: string; original: number; reduced: number }[] | undefined)
        ?.slice(0, 3)
        .forEach((reduction) =>
          push(
            reduction.engine + " fan-out " + reduction.original + " -> " + reduction.reduced,
            "danger",
          ),
        );
      break;
    }
    case "executing": {
      if (detail.engine) {
        push(
          String(detail.engine) +
            (detail.fan_out && Number(detail.fan_out) > 1 ? " x" + String(detail.fan_out) : ""),
          "accent",
        );
      }
      if (detail.cache_layer) {
        push(
          String(detail.cache_layer),
          detail.cache_layer === "live" ? "danger" : "warm",
        );
      }
      if (detail.credits !== undefined) push(String(detail.credits) + " credits");
      break;
    }
    default:
      break;
  }

  if (!chips.length) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.slice(0, 8).map((chip, index) => (
        <span
          key={index}
          className={cn(
            "mono rounded-[var(--radius-xs)] border px-1.5 py-0.5 text-[11px] leading-none",
            chip.tone === "warm"
              ? "border-warm/30 bg-warm-ghost text-warm"
              : chip.tone === "accent"
                ? "border-accent-muted/50 bg-accent-ghost text-accent-strong"
                : chip.tone === "danger"
                  ? "border-danger/30 bg-danger-ghost text-danger"
                  : "border-line bg-surface-raised text-ink-muted",
          )}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}
