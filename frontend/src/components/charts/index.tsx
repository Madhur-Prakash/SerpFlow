/**
 * Charts.
 *
 * One palette, one grid treatment, one tooltip. Series colours carry meaning
 * rather than decorating: warm green is a saving, amber is real spend, blue is
 * the accent for everything else.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";

export const SERIES = {
  spend: "var(--color-spend)",
  saved: "var(--color-warm)",
  accent: "var(--color-accent)",
  replay: "var(--color-replay)",
  danger: "var(--color-danger)",
  muted: "var(--color-ink-subtle)",
} as const;

export const LAYER_COLOR: Record<string, string> = {
  exact: "var(--color-warm)",
  semantic: "var(--color-accent)",
  archive: "var(--color-replay)",
  live: "var(--color-spend)",
  mock: "var(--color-accent-muted)",
  replay: "var(--color-replay)",
  miss: "var(--color-ink-subtle)",
};

const axisProps = {
  stroke: "var(--color-line-strong)",
  tick: { fill: "var(--color-ink-subtle)", fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string; payload?: Record<string, unknown> }[];
  label?: string;
  formatter?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const format = formatter ?? ((value: number) => fmt.credits(value));
  return (
    <div className="rounded-[var(--radius-sm)] border border-line bg-surface-raised px-2.5 py-2 shadow-[var(--shadow-raise)]">
      {label ? (
        <p className="mb-1 text-[11px] font-medium text-ink">{label}</p>
      ) : null}
      {payload.map((entry, index) => (
        <p key={index} className="flex items-center gap-2 text-[11px] text-ink-muted">
          <span
            className="size-2 rounded-[2px]"
            style={{ backgroundColor: entry.color ?? SERIES.accent }}
          />
          <span className="flex-1">{entry.name}</span>
          <span className="mono tabular text-ink">{format(entry.value ?? 0)}</span>
        </p>
      ))}
    </div>
  );
}

// ------------------------------------------------------- SavingsWaterfall
/**
 * Section 52's savings decomposition, drawn as a descent from naive execution
 * to actual spend. Each bar is a layer that removed credits from the bill.
 */
export function SavingsWaterfall({
  steps,
  height = 260,
}: {
  steps: { label: string; value: number; kind: string }[];
  height?: number;
}) {
  let running = 0;
  const data = steps.map((step) => {
    if (step.kind === "base") {
      running = step.value;
      return { ...step, base: 0, bar: step.value, display: step.value };
    }
    if (step.kind === "total") {
      return { ...step, base: 0, bar: step.value, display: step.value };
    }
    const magnitude = Math.abs(step.value);
    const base = running - magnitude;
    running = base;
    return { ...step, base, bar: magnitude, display: magnitude };
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <XAxis
          dataKey="label"
          {...axisProps}
          interval={0}
          tick={{ fill: "var(--color-ink-subtle)", fontSize: 10 }}
          angle={-16}
          textAnchor="end"
          height={56}
        />
        <YAxis {...axisProps} width={44} />
        <RechartsTooltip
          cursor={{ fill: "var(--color-surface-raised)", opacity: 0.4 }}
          content={({ active, payload }) => {
            const row = payload?.[0]?.payload as { label: string; display: number; kind: string };
            if (!active || !row) return null;
            return (
              <div className="rounded-[var(--radius-sm)] border border-line bg-surface-raised px-2.5 py-2 shadow-[var(--shadow-raise)]">
                <p className="text-[11px] font-medium text-ink">{row.label}</p>
                <p className="mono mt-0.5 text-[12px] tabular text-ink-muted">
                  {fmt.credits(row.display)} credits
                </p>
              </div>
            );
          }}
        />
        <Bar dataKey="base" stackId="w" fill="transparent" />
        <Bar dataKey="bar" stackId="w" radius={[2, 2, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={
                entry.kind === "base"
                  ? SERIES.muted
                  : entry.kind === "total"
                    ? SERIES.spend
                    : SERIES.saved
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------- LayerDonut
export function LayerDonut({
  layers,
  height = 220,
}: {
  layers: Record<string, number>;
  height?: number;
}) {
  const data = Object.entries(layers)
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }));

  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center text-[12px] text-ink-subtle"
        style={{ height }}
      >
        No cache lookups recorded in this window.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius="58%"
          outerRadius="84%"
          paddingAngle={2}
          stroke="var(--color-ground)"
          strokeWidth={2}
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={LAYER_COLOR[entry.name] ?? SERIES.muted} />
          ))}
        </Pie>
        <RechartsTooltip content={<ChartTooltip formatter={(v) => fmt.credits(v) + " lookups"} />} />
        <Legend
          verticalAlign="bottom"
          height={28}
          formatter={(value) => (
            <span className="text-[11px] text-ink-muted">{String(value)}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// --------------------------------------------------------- SpendArea
export function SpendArea({
  data,
  height = 200,
}: {
  data: { label: string; spent: number; saved: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="spend-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES.spend} stopOpacity={0.3} />
            <stop offset="100%" stopColor={SERIES.spend} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="saved-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES.saved} stopOpacity={0.3} />
            <stop offset="100%" stopColor={SERIES.saved} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={40} />
        <RechartsTooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="saved"
          name="saved"
          stroke={SERIES.saved}
          fill="url(#saved-gradient)"
          strokeWidth={1.6}
        />
        <Area
          type="monotone"
          dataKey="spent"
          name="spent"
          stroke={SERIES.spend}
          fill="url(#spend-gradient)"
          strokeWidth={1.6}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------- HorizontalBars
export function HorizontalBars({
  data,
  height = 240,
  color = SERIES.accent,
  formatter,
}: {
  data: { label: string; value: number }[];
  height?: number;
  color?: string;
  formatter?: (value: number) => string;
}) {
  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center text-[12px] text-ink-subtle"
        style={{ height }}
      >
        Nothing to show yet.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
        <XAxis type="number" {...axisProps} />
        <YAxis
          type="category"
          dataKey="label"
          {...axisProps}
          width={140}
          tick={{ fill: "var(--color-ink-muted)", fontSize: 11 }}
        />
        <RechartsTooltip
          cursor={{ fill: "var(--color-surface-raised)", opacity: 0.4 }}
          content={<ChartTooltip formatter={formatter} />}
        />
        <Bar dataKey="value" name="value" fill={color} radius={[0, 2, 2, 0]} barSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------- AccuracyRadar
export function AccuracyRadar({
  systems,
  height = 280,
}: {
  systems: { name: string; values: Record<string, number> }[];
  height?: number;
}) {
  const categories = [...new Set(systems.flatMap((system) => Object.keys(system.values)))];
  const data = categories.map((category) => {
    const row: Record<string, string | number> = { category: fmt.titleCase(category) };
    for (const system of systems) {
      row[system.name] = Math.round((system.values[category] ?? 0) * 100);
    }
    return row;
  });

  const colors = [SERIES.muted, SERIES.replay, SERIES.accent];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="var(--color-line)" />
        <PolarAngleAxis
          dataKey="category"
          tick={{ fill: "var(--color-ink-subtle)", fontSize: 10 }}
        />
        <RechartsTooltip content={<ChartTooltip formatter={(v) => v + "%"} />} />
        <Legend
          formatter={(value) => (
            <span className="text-[11px] text-ink-muted">{String(value)}</span>
          )}
        />
        {systems.map((system, index) => (
          <Radar
            key={system.name}
            name={system.name}
            dataKey={system.name}
            stroke={colors[index % colors.length]}
            fill={colors[index % colors.length]}
            fillOpacity={index === systems.length - 1 ? 0.22 : 0.08}
            strokeWidth={1.6}
          />
        ))}
      </RadarChart>
    </ResponsiveContainer>
  );
}

// --------------------------------------------------------- MiniSparkline
export function UtilizationBar({
  used,
  limit,
  alertAt,
  className,
}: {
  used: number;
  limit: number;
  alertAt?: number;
  className?: string;
}) {
  const ratio = limit > 0 ? Math.min(1, used / limit) : 0;
  const tone =
    ratio >= 1 ? "bg-danger" : ratio >= (alertAt ?? 0.8) ? "bg-caution" : "bg-accent";
  return (
    <div className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken", className)}>
      <div
        className={cn("h-full transition-[width] duration-500 ease-out", tone)}
        style={{ width: (ratio * 100).toFixed(1) + "%" }}
      />
      {alertAt && alertAt < 1 ? (
        <span
          className="absolute inset-y-0 w-px bg-ink-subtle/60"
          style={{ left: (alertAt * 100).toFixed(1) + "%" }}
          aria-hidden="true"
        />
      ) : null}
    </div>
  );
}
