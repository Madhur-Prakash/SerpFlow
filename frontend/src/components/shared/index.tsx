/**
 * Domain components.
 *
 * These carry SerpFlow's vocabulary: execution mode, cache layer, warm versus
 * cold, naive versus marginal cost. They are the pieces that stop the product
 * looking like a generic admin dashboard.
 */

import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock,
  Database,
  FileText,
  History,
  Layers,
  Lock,
  Play,
  RefreshCw,
  Server,
  Shield,
  Terminal,
  TrendingDown,
  XCircle,
  Zap,
} from "lucide-react";
import * as React from "react";

import { Badge, Button, Card, Tooltip } from "@/components/ui";
import { countUp, itemVariants, prefersReducedMotion } from "@/animations";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CacheLayer, Coverage, ExecutionMode, Freshness } from "@/types/api";

// ------------------------------------------------------------- ModeBadge
const MODE_TONE: Record<string, { tone: Parameters<typeof Badge>[0]["tone"]; icon: typeof Zap }> =
  {
    LIVE: { tone: "warm", icon: Zap },
    MOCK: { tone: "accent", icon: Terminal },
    REPLAY: { tone: "replay", icon: History },
    RECORD: { tone: "spend", icon: Server },
  };

/**
 * Section 21: the resolved mode is surfaced on every request. Replayed or
 * mocked data is never presented as live, so this badge is always visible
 * rather than only when something is unusual.
 */
export function ModeBadge({
  mode,
  reason,
  className,
}: {
  mode: string | ExecutionMode;
  reason?: string;
  className?: string;
}) {
  const key = String(mode).toUpperCase();
  const config = MODE_TONE[key] ?? MODE_TONE.MOCK;
  const Icon = config.icon;
  return (
    <Tooltip content={reason}>
      <Badge tone={config.tone} className={cn("uppercase tracking-[0.08em]", className)}>
        <Icon />
        {key}
      </Badge>
    </Tooltip>
  );
}

// ------------------------------------------------------- CacheLayerBadge
const LAYER_TONE: Record<string, Parameters<typeof Badge>[0]["tone"]> = {
  exact: "warm",
  semantic: "accent",
  archive: "replay",
  live: "spend",
  mock: "accent",
  replay: "replay",
  miss: "outline",
  skipped: "outline",
};

const LAYER_EXPLAIN: Record<string, string> = {
  exact: "Served from the Redis hot layer or the durable index. No upstream call.",
  semantic: "Served from a semantically equivalent cached query that passed the entity guard.",
  archive: "Re-read from the SerpApi Searches Archive. Archived reads consume no credit.",
  live: "Executed live against SerpApi. This is the only layer that spends credits.",
  mock: "Served by the deterministic mock. A test API key always routes here.",
  replay: "Served from a recorded cassette. Replay never reaches the network.",
  miss: "Nothing cached satisfied this request.",
  skipped: "This step was not executed.",
};

export function CacheLayerBadge({
  layer,
  className,
}: {
  layer: CacheLayer | string | null | undefined;
  className?: string;
}) {
  const key = String(layer ?? "miss");
  return (
    <Tooltip content={LAYER_EXPLAIN[key]}>
      <Badge tone={LAYER_TONE[key] ?? "outline"} className={cn("mono", className)}>
        {key}
      </Badge>
    </Tooltip>
  );
}

// ------------------------------------------------------- FreshnessBadge
const FRESHNESS_EXPLAIN: Record<Freshness, string> = {
  realtime: "Under 15 minutes. A warm entry older than that is available but not acceptable.",
  fresh: "Under 24 hours.",
  recent: "Under 7 days.",
  stable: "Any valid TTL. Nothing in the intent implies time sensitivity.",
};

export function FreshnessBadge({ level }: { level: Freshness | string }) {
  const tone =
    level === "realtime"
      ? "danger"
      : level === "fresh"
        ? "caution"
        : level === "recent"
          ? "accent"
          : "outline";
  return (
    <Tooltip content={FRESHNESS_EXPLAIN[level as Freshness]}>
      <Badge tone={tone as Parameters<typeof Badge>[0]["tone"]}>
        <Clock />
        {level}
      </Badge>
    </Tooltip>
  );
}

// -------------------------------------------------------- CoverageBadge
const COVERAGE_EXPLAIN: Record<Coverage, string> = {
  full: "Returns an equivalent result set for the same capability.",
  partial: "Overlapping but materially different coverage or field shape.",
  narrow: "Usable only inside a restricted geography, vertical or corpus.",
};

export function CoverageBadge({ coverage }: { coverage: Coverage | string }) {
  const tone = coverage === "full" ? "warm" : coverage === "partial" ? "caution" : "danger";
  return (
    <Tooltip content={COVERAGE_EXPLAIN[coverage as Coverage]}>
      <Badge tone={tone as Parameters<typeof Badge>[0]["tone"]}>{coverage}</Badge>
    </Tooltip>
  );
}

// ----------------------------------------------------------- WarmIndicator
export function WarmIndicator({ warm, label }: { warm: boolean; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[12px] font-medium",
        warm ? "text-warm" : "text-ink-subtle",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          warm ? "bg-warm shadow-[0_0_0_3px_var(--color-warm-ghost)]" : "bg-cold",
        )}
      />
      {label ?? (warm ? "warm" : "cold")}
    </span>
  );
}

// --------------------------------------------------------------- StatCard
export function StatCard({
  label,
  value,
  unit,
  delta,
  hint,
  icon: Icon,
  tone = "neutral",
  animate = true,
  className,
}: {
  label: string;
  value: number | string;
  unit?: string;
  delta?: { value: number; label: string; good?: boolean };
  hint?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "neutral" | "warm" | "spend" | "accent" | "danger";
  animate?: boolean;
  className?: string;
}) {
  const ref = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (!animate || typeof value !== "number" || !ref.current) return;
    const tween = countUp(ref.current, value, {
      format: (v) => fmt.credits(Math.round(v)),
    });
    return () => {
      tween?.kill();
    };
  }, [animate, value]);

  const toneClass = {
    neutral: "text-ink",
    warm: "text-warm",
    spend: "text-spend",
    accent: "text-accent-strong",
    danger: "text-danger",
  }[tone];

  return (
    <Card className={cn("p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.07em] text-ink-subtle">
          {label}
        </p>
        {Icon ? <Icon className="size-4 text-ink-subtle" /> : null}
      </div>
      <div className="mt-2.5 flex items-baseline gap-1.5">
        <span className={cn("mono text-2xl font-semibold tabular leading-none", toneClass)}>
          {typeof value === "number" ? (
            <span ref={ref}>{animate ? "0" : fmt.credits(value)}</span>
          ) : (
            value
          )}
        </span>
        {unit ? <span className="text-[12px] text-ink-subtle">{unit}</span> : null}
      </div>
      {delta ? (
        <p
          className={cn(
            "mt-2 inline-flex items-center gap-1 text-[12px]",
            delta.good === false ? "text-danger" : "text-warm",
          )}
        >
          <TrendingDown className="size-3" />
          <span className="mono tabular">{fmt.credits(delta.value)}</span>
          <span className="text-ink-subtle">{delta.label}</span>
        </p>
      ) : null}
      {hint ? <p className="mt-2 text-[12px] text-ink-subtle text-pretty">{hint}</p> : null}
    </Card>
  );
}

// --------------------------------------------------------- CostComparison
/**
 * Naive against marginal, with the saving between them.
 *
 * Section 48: the counterfactual comes from persisted Plan data. Nothing here
 * is recomputed in the browser; these are the numbers the planner stored.
 */
export function CostComparison({
  naive,
  marginal,
  actual,
  projection,
  compact: isCompact,
  className,
}: {
  naive: number;
  marginal: number;
  actual?: number;
  projection?: number | null;
  compact?: boolean;
  className?: string;
}) {
  const saved = Math.max(0, naive - marginal);
  const savedPercent = naive > 0 ? saved / naive : 0;

  if (isCompact) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 mono text-[12px]", className)}>
        <span className="text-ink-subtle line-through">{fmt.credits(naive)}</span>
        <ArrowRight className="size-3 text-ink-subtle" />
        <span className="font-semibold text-warm">{fmt.credits(marginal)}</span>
      </span>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="grid grid-cols-3 gap-px overflow-hidden rounded-[var(--radius-sm)] border border-line bg-line">
        <CostCell label="Naive execution" value={naive} tone="muted" />
        <CostCell label="Marginal execution" value={marginal} tone="warm" />
        <CostCell
          label={actual !== undefined ? "Actually spent" : "Saved"}
          value={actual !== undefined ? actual : saved}
          tone={actual !== undefined ? "spend" : "accent"}
        />
      </div>

      <div className="space-y-1.5">
        <div className="relative h-2 overflow-hidden rounded-full bg-surface-sunken">
          <motion.div
            className="absolute inset-y-0 left-0 bg-warm"
            initial={{ width: 0 }}
            animate={{ width: (savedPercent * 100).toFixed(2) + "%" }}
            transition={{ duration: prefersReducedMotion() ? 0 : 0.7, ease: [0.22, 1, 0.36, 1] }}
          />
        </div>
        <p className="text-[12px] text-ink-subtle">
          <span className="mono font-medium text-warm">{fmt.percent(savedPercent)}</span> of the
          cold cost avoided because those steps were already warm and still fresh enough to use.
        </p>
      </div>

      {projection ? (
        <div className="flex items-start gap-2 rounded-[var(--radius-sm)] border border-caution/30 bg-caution-ghost px-3 py-2">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-caution" />
          <p className="text-[12px] text-caution">
            Full-scale projection: <span className="mono font-semibold">{fmt.credits(projection)}</span>{" "}
            credits. This is a projection only and is never executed live.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function CostCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "muted" | "warm" | "spend" | "accent";
}) {
  const toneClass = {
    muted: "text-ink-muted",
    warm: "text-warm",
    spend: "text-spend",
    accent: "text-accent-strong",
  }[tone];
  return (
    <div className="bg-surface px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">{label}</p>
      <p className={cn("mono mt-1 text-lg font-semibold tabular leading-none", toneClass)}>
        {fmt.credits(value)}
        <span className="ml-1 text-[11px] font-normal text-ink-subtle">cr</span>
      </p>
    </div>
  );
}

// ------------------------------------------------------------- EmptyState
/**
 * Section 75: an empty state explains what the section contains, why it
 * matters and what to do next. Lucide icons only.
 */
export function EmptyState({
  icon: Icon = Layers,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-line px-6 py-14 text-center",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 grid-field opacity-25" />
      <div className="relative flex size-10 items-center justify-center rounded-[var(--radius-md)] border border-line bg-surface-raised">
        <Icon className="size-4.5 text-ink-subtle" />
      </div>
      <h3 className="relative mt-4 text-[13px] font-semibold text-ink">{title}</h3>
      <p className="relative mt-1.5 max-w-md text-[12px] leading-relaxed text-ink-subtle text-pretty">
        {description}
      </p>
      {action ? <div className="relative mt-4">{action}</div> : null}
    </div>
  );
}

// ----------------------------------------------------------- StatusDot
export function StatusDot({ status }: { status: string }) {
  const map: Record<string, { tone: string; label: string }> = {
    succeeded: { tone: "bg-warm", label: "succeeded" },
    running: { tone: "bg-accent animate-pulse-ring", label: "running" },
    planning: { tone: "bg-accent animate-pulse-ring", label: "planning" },
    planned: { tone: "bg-accent", label: "planned" },
    pending: { tone: "bg-ink-subtle", label: "pending" },
    queued: { tone: "bg-ink-subtle", label: "queued" },
    failed: { tone: "bg-danger", label: "failed" },
  };
  const config = map[status] ?? { tone: "bg-ink-subtle", label: status };
  return (
    <span className="inline-flex items-center gap-2 text-[12px] text-ink-muted">
      <span className={cn("size-1.5 rounded-full", config.tone)} />
      {config.label}
    </span>
  );
}

// ------------------------------------------------------------ PageHeader
export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="rule pb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          {Icon ? (
            <div className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-line bg-surface-raised">
              <Icon className="size-4 text-ink-muted" />
            </div>
          ) : null}
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-[-0.01em] text-ink">{title}</h1>
            {description ? (
              <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-subtle text-pretty">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children ? <div className="mt-4">{children}</div> : null}
    </header>
  );
}

// ------------------------------------------------------------- Section
export function Section({
  title,
  description,
  icon,
  actions,
  children,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const Icon = icon;
  return (
    <motion.section variants={itemVariants} className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          {Icon ? <Icon className="size-4 text-ink-subtle" /> : null}
          <div>
            <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
            {description ? (
              <p className="mt-0.5 text-[12px] text-ink-subtle text-pretty">{description}</p>
            ) : null}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </motion.section>
  );
}

// ----------------------------------------------------------- CopyButton
export function CopyButton({
  value,
  label = "Copy",
  size = "icon-sm",
}: {
  value: string;
  label?: string;
  size?: "icon-sm" | "sm";
}) {
  const [copied, setCopied] = React.useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Tooltip content={copied ? "Copied" : label}>
      <Button variant="ghost" size={size} onClick={copy} aria-label={label}>
        {copied ? <CheckCircle className="text-warm" /> : <FileText />}
      </Button>
    </Tooltip>
  );
}

// ----------------------------------------------------------- KeyValue
export function KeyValue({
  rows,
  className,
  columns = 2,
}: {
  rows: { label: React.ReactNode; value: React.ReactNode; mono?: boolean }[];
  className?: string;
  columns?: 1 | 2 | 3;
}) {
  return (
    <dl
      className={cn(
        "grid gap-x-6 gap-y-3",
        columns === 1 ? "grid-cols-1" : columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3",
        className,
      )}
    >
      {rows.map((row, index) => (
        <div key={index} className="min-w-0">
          <dt className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
            {row.label}
          </dt>
          <dd
            className={cn(
              "mt-1 truncate text-[13px] text-ink",
              row.mono ? "mono tabular" : "",
            )}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// --------------------------------------------------------- ErrorMessage
export function ErrorMessage({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const apiError = error as { code?: string; message?: string; remedy?: string | null; requestId?: string };
  return (
    <Alert
      tone="danger"
      icon={XCircle}
      title={apiError?.code ?? "Something went wrong"}
      action={
        onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw />
            Retry
          </Button>
        ) : null
      }
    >
      <p>{apiError?.message ?? String(error)}</p>
      {apiError?.remedy ? <p className="mt-1 opacity-80">{apiError.remedy}</p> : null}
      {apiError?.requestId ? (
        <p className="mono mt-1 text-[11px] opacity-60">request {apiError.requestId}</p>
      ) : null}
    </Alert>
  );
}

function Alert({
  tone,
  icon: Icon,
  title,
  children,
  action,
}: {
  tone: "danger";
  icon: React.ComponentType<{ className?: string }>;
  title: React.ReactNode;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-[var(--radius-sm)] border px-3 py-2.5",
        tone === "danger" ? "border-danger/30 bg-danger-ghost text-danger" : "",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[13px] font-medium">{title}</p>
        <div className="text-[12px] leading-relaxed opacity-90 text-pretty">{children}</div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

// -------------------------------------------------------- PermissionGate
export function PermissionGate({
  permitted,
  message,
  children,
}: {
  permitted: boolean;
  message?: string;
  children: React.ReactNode;
}) {
  if (permitted) return <>{children}</>;
  return (
    <EmptyState
      icon={Lock}
      title="Not permitted"
      description={
        message ??
        "Your role does not include this permission. An owner or admin can change it in Settings, Members."
      }
    />
  );
}

export const Icons = {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Clock,
  Database,
  FileText,
  History,
  Layers,
  Play,
  RefreshCw,
  Server,
  Shield,
  Terminal,
  XCircle,
  Zap,
};
