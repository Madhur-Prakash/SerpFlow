/**
 * The selected plan as a dependency chain.
 *
 * Edges are drawn with GSAP in dependency order so the chain reads the way it
 * executes. Warm steps are marked distinctly from cold ones, because that
 * distinction is what the marginal cost is computed from.
 */

import { gsap } from "gsap";
import * as React from "react";

import { drawPath, prefersReducedMotion, revealNodes } from "@/animations";
import { CacheLayerBadge, FreshnessBadge } from "@/components/shared";
import { Tooltip } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { Plan, PlanCandidate } from "@/types/api";

interface Props {
  plan?: Plan;
  /** Render a candidate instead of the selected plan. */
  candidate?: PlanCandidate;
  compact?: boolean;
  className?: string;
}

interface Node {
  index: number;
  engine: string;
  fanOut: number;
  warm: boolean;
  layer: string;
  freshness: string;
  reason?: string;
  dependsOn: number[];
}

function nodesFromPlan(plan: Plan): Node[] {
  return plan.steps.map((step) => ({
    index: step.index,
    engine: step.engine,
    fanOut: step.fan_out,
    warm: step.warm,
    layer: step.cache_state?.layer ?? "miss",
    freshness: step.freshness_requirement,
    reason: step.cache_state?.reason,
    dependsOn: step.depends_on,
  }));
}

function nodesFromCandidate(candidate: PlanCandidate): Node[] {
  return candidate.engines.map((engine, index) => {
    const state = candidate.cache_state?.[index];
    const raw = candidate.steps?.[index] as { fan_out?: number; depends_on?: number[] } | undefined;
    return {
      index,
      engine,
      fanOut: raw?.fan_out ?? 1,
      warm: candidate.warm_step_indices.includes(index),
      layer: state?.layer ?? "miss",
      freshness: state?.freshness_requirement ?? "stable",
      reason: state?.reason,
      dependsOn: raw?.depends_on ?? (index > 0 ? [index - 1] : []),
    };
  });
}

export function PlanGraph({ plan, candidate, compact, className }: Props) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const nodes = React.useMemo(
    () => (plan ? nodesFromPlan(plan) : candidate ? nodesFromCandidate(candidate) : []),
    [plan, candidate],
  );

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container || !nodes.length) return;

    const context = gsap.context(() => {
      const nodeElements = Array.from(container.querySelectorAll("[data-plan-node]"));
      revealNodes(nodeElements, { stagger: 0.09 });

      const connectors = Array.from(
        container.querySelectorAll<SVGLineElement>("[data-plan-edge] line"),
      );
      connectors.forEach((line, index) => {
        if (prefersReducedMotion()) {
          gsap.set(line, { opacity: 1, strokeDashoffset: 0 });
          return;
        }
        drawPath(line, { duration: 0.34, delay: 0.1 + index * 0.09 });
      });
    }, container);

    return () => context.revert();
  }, [nodes]);

  if (!nodes.length) return null;

  return (
    <div
      ref={containerRef}
      className={cn("flex flex-wrap items-stretch gap-0", className)}
      role="list"
      aria-label="Execution plan"
    >
      {nodes.map((node, index) => (
        <React.Fragment key={node.index + node.engine}>
          {index > 0 ? <Connector warm={node.warm} fanOut={node.fanOut} /> : null}
          <NodeCard node={node} compact={compact} />
        </React.Fragment>
      ))}
    </div>
  );
}

function Connector({ warm, fanOut }: { warm: boolean; fanOut: number }) {
  return (
    <div
      data-plan-edge
      className="flex min-w-14 flex-col items-center justify-center gap-1 px-1 py-4"
      aria-hidden="true"
    >
      <svg viewBox="0 0 56 10" className="h-2.5 w-14 overflow-visible">
        <line
          x1="0"
          y1="5"
          x2="48"
          y2="5"
          stroke={warm ? "var(--color-warm)" : "var(--color-line-strong)"}
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0"
        />
        <path
          d="M48 1.5 L54 5 L48 8.5 Z"
          fill={warm ? "var(--color-warm)" : "var(--color-line-strong)"}
        />
      </svg>
      {fanOut > 1 ? (
        <span className="mono text-[10px] leading-none text-ink-subtle">x{fanOut}</span>
      ) : null}
    </div>
  );
}

function NodeCard({ node, compact }: { node: Node; compact?: boolean }) {
  return (
    <Tooltip content={node.reason} side="bottom">
      <div
        data-plan-node
        role="listitem"
        className={cn(
          "relative flex min-w-44 flex-col gap-2 rounded-[var(--radius-md)] border bg-surface px-3 py-2.5 transition-colors",
          node.warm
            ? "border-warm/45 bg-warm-ghost/25"
            : "border-line hover:border-line-strong",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="mono text-[11px] text-ink-subtle">step {node.index}</span>
          <span
            className={cn(
              "size-1.5 rounded-full",
              node.warm
                ? "bg-warm shadow-[0_0_0_3px_var(--color-warm-ghost)]"
                : "bg-cold",
            )}
          />
        </div>

        <p className="mono text-[13px] font-medium leading-tight text-ink">{node.engine}</p>

        {!compact ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <CacheLayerBadge layer={node.layer} />
            <FreshnessBadge level={node.freshness} />
          </div>
        ) : null}

        {node.fanOut > 1 ? (
          <p className="text-[11px] text-ink-subtle">
            <span className="mono">{node.fanOut}</span> calls
          </p>
        ) : null}
      </div>
    </Tooltip>
  );
}
