import { Command } from "cmdk";
import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  GitBranch,
  Key,
  Network,
  Route,
  Search,
  Settings,
  Shield,
  Users,
  Wallet,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { useCatalog, useRuns } from "@/hooks/useQueries";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DESTINATIONS = [
  { to: "/app", label: "Overview", icon: Gauge, hint: "credits, cache, alerts" },
  { to: "/app/search", label: "Search", icon: Search, hint: "run an intent" },
  { to: "/app/runs", label: "Runs", icon: Activity, hint: "execution history" },
  { to: "/app/plans", label: "Plan Inspector", icon: Route, hint: "why this plan won" },
  { to: "/app/catalog", label: "Catalog", icon: Network, hint: "engines and dependencies" },
  { to: "/app/cache", label: "Cache", icon: Database, hint: "layers, TTL, guard" },
  { to: "/app/budgets", label: "Budgets", icon: Wallet, hint: "caps and upstream quota" },
  { to: "/app/analytics", label: "Analytics", icon: BarChart3, hint: "savings decomposition" },
  { to: "/app/benchmarks", label: "Benchmarks", icon: GitBranch, hint: "routing accuracy" },
  { to: "/app/audit", label: "Audit Log", icon: Shield, hint: "hash-chained history" },
  { to: "/app/settings/api-keys", label: "API keys", icon: Key, hint: "mint, rotate, revoke" },
  { to: "/app/settings/members", label: "Members", icon: Users, hint: "roles" },
  { to: "/app/settings", label: "Settings", icon: Settings, hint: "organization and policy" },
];

export function CommandPalette({ open, onOpenChange }: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = React.useState("");
  const runs = useRuns({ limit: 8 });
  const catalog = useCatalog();

  const go = React.useCallback(
    (to: string) => {
      onOpenChange(false);
      setQuery("");
      navigate(to);
    },
    [navigate, onOpenChange],
  );

  const engines = React.useMemo(() => {
    if (!query || !catalog.data) return [];
    const needle = query.toLowerCase();
    return catalog.data.engines
      .filter(
        (engine) =>
          engine.engine.includes(needle) || engine.purpose.toLowerCase().includes(needle),
      )
      .slice(0, 6);
  }, [catalog.data, query]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ground/75 px-4 pt-[12vh] backdrop-blur-[2px] animate-in fade-in"
      onClick={() => onOpenChange(false)}
    >
      <Command
        className="w-full max-w-xl overflow-hidden rounded-[var(--radius-lg)] border border-line bg-surface shadow-[var(--shadow-float)] animate-in zoom-in-95"
        onClick={(event) => event.stopPropagation()}
        shouldFilter={false}
        loop
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Search className="size-4 shrink-0 text-ink-subtle" />
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder="Jump to a page, a run, or an engine"
            className="h-12 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-subtle"
          />
          <kbd className="mono rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-subtle">
            Esc
          </kbd>
        </div>

        <Command.List className="max-h-[22rem] overflow-y-auto p-2">
          <Command.Empty className="px-3 py-8 text-center text-[12px] text-ink-subtle">
            Nothing matched that.
          </Command.Empty>

          <Group heading="Go to">
            {DESTINATIONS.filter(
              (item) =>
                !query ||
                item.label.toLowerCase().includes(query.toLowerCase()) ||
                item.hint.includes(query.toLowerCase()),
            ).map((item) => (
              <Item key={item.to} onSelect={() => go(item.to)}>
                <item.icon className="size-3.5 text-ink-subtle" />
                <span className="flex-1">{item.label}</span>
                <span className="text-[11px] text-ink-subtle">{item.hint}</span>
              </Item>
            ))}
          </Group>

          {query && engines.length ? (
            <Group heading="Engines">
              {engines.map((engine) => (
                <Item
                  key={engine.engine}
                  onSelect={() => go("/app/catalog?engine=" + engine.engine)}
                >
                  <Network className="size-3.5 text-ink-subtle" />
                  <span className="mono flex-1">{engine.engine}</span>
                  <span className="max-w-56 truncate text-[11px] text-ink-subtle">
                    {engine.purpose}
                  </span>
                </Item>
              ))}
            </Group>
          ) : null}

          {runs.data?.items.length ? (
            <Group heading="Recent runs">
              {runs.data.items
                .filter(
                  (run) => !query || run.intent.toLowerCase().includes(query.toLowerCase()),
                )
                .slice(0, 6)
                .map((run) => (
                  <Item key={run.id} onSelect={() => go("/app/runs/" + run.id)}>
                    <Activity className="size-3.5 text-ink-subtle" />
                    <span className="flex-1 truncate">{run.intent}</span>
                    <span className="mono text-[11px] text-ink-subtle">
                      {fmt.credits(run.credits_spent)} cr
                    </span>
                  </Item>
                ))}
            </Group>
          ) : null}
        </Command.List>
      </Command>
    </div>
  );
}

function Group({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.1em] [&_[cmdk-group-heading]]:text-ink-subtle"
    >
      {children}
    </Command.Group>
  );
}

function Item({
  children,
  onSelect,
  className,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  className?: string;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-[var(--radius-xs)] px-2 py-2 text-[13px] text-ink-muted",
        "data-[selected=true]:bg-surface-raised data-[selected=true]:text-ink",
        className,
      )}
    >
      {children}
    </Command.Item>
  );
}
