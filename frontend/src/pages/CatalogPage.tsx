/**
 * The Catalog Explorer (section 49).
 *
 * Substitute relationships are rendered as visually distinct from dependency
 * relationships throughout, because they mean different things: dependency
 * edges describe how engines CHAIN, substitutes describe how they COMPETE.
 */

import { motion } from "framer-motion";
import {
  ArrowRight,
  GitBranch,
  Network,
  Search,
  Shield,
  Shuffle,
  Clock,
  Zap,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { itemVariants, listVariants } from "@/animations";
import { CatalogGraph } from "@/components/graphs/CatalogGraph";
import {
  CoverageBadge,
  EmptyState,
  ErrorMessage,
  PageHeader,
  Section,
} from "@/components/shared";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
  ScrollArea,
  Skeleton,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
} from "@/components/ui";
import { useCatalog, useCatalogGraph, useCatalogTags } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CatalogEngine } from "@/types/api";

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = React.useState("");
  const [showSubstitutes, setShowSubstitutes] = React.useState(true);
  const selected = params.get("engine");

  const catalog = useCatalog();
  const graph = useCatalogGraph();
  const tags = useCatalogTags();
  const [paths, setPaths] = React.useState<{ path_count: number; paths: Record<string, unknown>[] } | null>(
    null,
  );

  React.useEffect(() => {
    if (!selected) {
      setPaths(null);
      return;
    }
    let cancelled = false;
    api
      .catalogPaths(selected)
      .then((result) => {
        if (!cancelled) setPaths(result);
      })
      .catch(() => {
        if (!cancelled) setPaths(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const engines = React.useMemo(() => {
    const all = catalog.data?.engines ?? [];
    if (!query) return all;
    const needle = query.toLowerCase();
    return all.filter(
      (engine) =>
        engine.engine.includes(needle) ||
        engine.purpose.toLowerCase().includes(needle) ||
        engine.capability_tags.some((tag) => tag.includes(needle)),
    );
  }, [catalog.data, query]);

  const engine = React.useMemo(
    () => catalog.data?.engines.find((candidate) => candidate.engine === selected) ?? null,
    [catalog.data, selected],
  );

  function select(name: string) {
    const next = new URLSearchParams(params);
    next.set("engine", name);
    setParams(next);
  }

  if (catalog.isError) {
    return <ErrorMessage error={catalog.error} onRetry={() => catalog.refetch()} />;
  }

  const competingTags = (tags.data?.tags ?? []).filter((tag) => tag.competing);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Catalog"
        icon={Network}
        description="Every engine SerpFlow can route to, the typed dependency edges that let them chain, and the capability tags that make them compete."
        actions={
          catalog.data ? (
            <div className="flex items-center gap-2">
              <Badge tone="outline" className="mono">
                {catalog.data.version}
              </Badge>
              <Badge tone="accent" className="mono">
                {catalog.data.engine_count} engines
              </Badge>
            </div>
          ) : null
        }
      >
        <div className="grid gap-3 sm:grid-cols-4">
          <Metric label="Engines" value={catalog.data?.engine_count} />
          <Metric label="Dependency edges" value={catalog.data?.edge_count} hint="how engines chain" />
          <Metric
            label="Substitute edges"
            value={catalog.data?.substitute_count}
            hint="how engines compete"
          />
          <Metric label="Competing groups" value={competingTags.length} />
        </div>
      </PageHeader>

      <Tabs defaultValue="explore">
        <TabsList>
          <TabsTrigger value="explore">
            <Search />
            Explore
          </TabsTrigger>
          <TabsTrigger value="graph">
            <GitBranch />
            Dependency graph
          </TabsTrigger>
          <TabsTrigger value="groups">
            <Shuffle />
            Substitute groups
          </TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------- explore */}
        <TabsContent value="explore" className="pt-4">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
            <Card className="flex max-h-[70vh] flex-col overflow-hidden">
              <div className="border-b border-line p-3">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-subtle" />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Filter engines, purposes and tags"
                    className="pl-8"
                  />
                </div>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                {catalog.isLoading ? (
                  <div className="space-y-1.5 p-3">
                    {Array.from({ length: 10 }).map((_, index) => (
                      <Skeleton key={index} className="h-10" />
                    ))}
                  </div>
                ) : (
                  <ul className="divide-y divide-line">
                    {engines.map((item) => (
                      <li key={item.engine}>
                        <button
                          onClick={() => select(item.engine)}
                          className={cn(
                            "flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-surface-raised",
                            item.engine === selected && "bg-surface-raised",
                          )}
                        >
                          <span
                            className={cn(
                              "mt-1 size-1.5 shrink-0 rounded-full",
                              item.pii_risk === "high"
                                ? "bg-danger"
                                : item.dependents.length || item.depends_on.length
                                  ? "bg-accent"
                                  : "bg-ink-subtle",
                            )}
                          />
                          <div className="min-w-0">
                            <p className="mono truncate text-[12px] text-ink">{item.engine}</p>
                            <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-subtle">
                              {item.purpose}
                            </p>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </ScrollArea>
            </Card>

            {engine ? (
              <EngineDetail engine={engine} paths={paths} onSelect={select} />
            ) : (
              <EmptyState
                icon={Network}
                title="Pick an engine"
                description="Each entry shows what the engine does, which parameters it requires, which upstream fields can satisfy them, what it produces for downstream hops, and which engines compete with it."
              />
            )}
          </div>
        </TabsContent>

        {/* --------------------------------------------------- graph */}
        <TabsContent value="graph" className="pt-4">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-2xl text-[12px] leading-relaxed text-ink-subtle text-pretty">
                Solid arrows are typed dependency edges: the source engine produces a field that
                satisfies a required parameter of the target. Dashed lines are substitutes:
                engines that answer the same capability and therefore compete for selection.
              </p>
              <label className="flex shrink-0 items-center gap-2 text-[12px] text-ink-muted">
                <Switch checked={showSubstitutes} onCheckedChange={setShowSubstitutes} />
                Show substitutes
              </label>
            </div>
            {graph.isLoading ? (
              <Skeleton className="h-[620px]" />
            ) : graph.data ? (
              <CatalogGraph
                data={graph.data}
                focus={selected}
                onSelect={select}
                showSubstitutes={showSubstitutes}
                className="h-[620px]"
              />
            ) : null}
          </div>
        </TabsContent>

        {/* -------------------------------------------------- groups */}
        <TabsContent value="groups" className="pt-4">
          <Section
            title="Capability tags"
            icon={Shuffle}
            description="Engines sharing a tag are candidate substitutes for each other. Without these, the planner could not generate alternative candidate plans and marginal replanning would have nothing to re-rank."
          >
            <div className="grid gap-3 md:grid-cols-2">
              {(tags.data?.tags ?? []).map((tag) => (
                <Card key={tag.tag}>
                  <CardBody>
                    <div className="flex items-center justify-between gap-2">
                      <p className="mono text-[13px] font-medium text-ink">{tag.tag}</p>
                      <Badge tone={tag.competing ? "accent" : "outline"}>
                        {tag.engines.length} {fmt(tag.engines.length)}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                      {tag.description}
                    </p>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {tag.engines.map((name) => (
                        <button
                          key={name}
                          onClick={() => select(name)}
                          className="mono rounded-[var(--radius-xs)] border border-line bg-surface-sunken px-1.5 py-0.5 text-[11px] text-ink-muted transition-colors hover:border-accent-muted hover:text-accent-strong"
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          </Section>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

function fmt(count: number) {
  return count === 1 ? "engine" : "engines";
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value?: number;
  hint?: string;
}) {
  return (
    <div className="rounded-[var(--radius-sm)] border border-line bg-surface px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">{label}</p>
      <p className="mono mt-1 text-lg font-semibold tabular leading-none text-ink">
        {value ?? "-"}
      </p>
      {hint ? <p className="mt-1 text-[11px] text-ink-subtle">{hint}</p> : null}
    </div>
  );
}

function EngineDetail({
  engine,
  paths,
  onSelect,
}: {
  engine: CatalogEngine;
  paths: { path_count: number; paths: Record<string, unknown>[] } | null;
  onSelect: (engine: string) => void;
}) {
  return (
    <motion.div variants={itemVariants} className="space-y-4">
      <Card>
        <CardHeader
          title={<span className="mono">{engine.engine}</span>}
          description={engine.purpose}
          action={
            engine.docs_url ? (
              <Button asChild variant="ghost" size="sm">
                <a href={engine.docs_url} target="_blank" rel="noreferrer noopener">
                  SerpApi docs
                  <ArrowRight />
                </a>
              </Button>
            ) : null
          }
        />
        <CardBody className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {engine.capability_tags.map((tag) => (
              <Badge key={tag} tone="accent">
                {tag}
              </Badge>
            ))}
            <Badge tone="outline" className="mono">
              cost {engine.cost}
            </Badge>
            <Tooltip content="Seeds the adaptive TTL controller. The controller then learns from observed churn.">
              <Badge tone="outline" className="mono">
                <Clock />
                {engine.volatility_prior}
              </Badge>
            </Tooltip>
            <Badge tone="outline" className="mono">
              <Zap />
              {engine.latency_class}
            </Badge>
            {engine.pii_risk !== "low" ? (
              <Tooltip content="Cached SERPs from this engine are not anonymous infrastructure data, so they get the shorter retention window.">
                <Badge tone={engine.pii_risk === "high" ? "danger" : "caution"}>
                  <Shield />
                  {engine.pii_risk} PII risk
                </Badge>
              </Tooltip>
            ) : null}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                Required parameters
              </p>
              <ul className="mt-2 space-y-2">
                {Object.entries(engine.requires).map(([name, spec]) => (
                  <li key={name} className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2">
                    <p className="mono text-[12px] text-ink">
                      {name}
                      <span className="ml-1.5 text-[11px] text-ink-subtle">{spec.type}</span>
                    </p>
                    {spec.description ? (
                      <p className="mt-0.5 text-[11px] text-ink-subtle">{spec.description}</p>
                    ) : null}
                    {spec.satisfied_by.length ? (
                      <div className="mt-1.5 space-y-0.5">
                        <p className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">
                          satisfied by
                        </p>
                        {spec.satisfied_by.map((source) => (
                          <p key={source} className="mono text-[11px] text-accent-strong">
                            {source}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-1 text-[11px] text-ink-subtle">caller supplies this</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                Produces
              </p>
              {Object.keys(engine.produces).length ? (
                <ul className="mt-2 space-y-2">
                  {Object.entries(engine.produces).map(([field, spec]) => (
                    <li
                      key={field}
                      className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2"
                    >
                      <p className="mono text-[11px] text-ink">{field}</p>
                      {spec.feeds.length ? (
                        <div className="mt-1 space-y-0.5">
                          {spec.feeds.map((target) => (
                            <p key={target} className="mono text-[11px] text-warm">
                              feeds {target}
                            </p>
                          ))}
                          {spec.fan_out_hint > 1 ? (
                            <p className="text-[10px] text-ink-subtle">
                              fan-out hint x{spec.fan_out_hint}
                            </p>
                          ) : null}
                        </div>
                      ) : (
                        <p className="mt-0.5 text-[11px] text-ink-subtle">terminal field</p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[12px] text-ink-subtle">
                  Nothing downstream consumes this engine's output.
                </p>
              )}

              {engine.optional.length ? (
                <>
                  <p className="mt-4 text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                    Optional parameters
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {engine.optional.map((name) => (
                      <span
                        key={name}
                        className="mono rounded-[var(--radius-xs)] border border-line px-1.5 py-0.5 text-[10px] text-ink-subtle"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Substitutes are visually distinct from dependencies throughout. */}
      <Card>
        <CardHeader
          title="Substitutes"
          icon={Shuffle}
          description="Engines that compete for the same capability, with the real trade-off."
        />
        <CardBody>
          {engine.substitutes.length ? (
            <ul className="space-y-2">
              {engine.substitutes.map((substitute) => (
                <li
                  key={substitute.engine}
                  className="rounded-[var(--radius-sm)] border border-replay/25 bg-replay-ghost/25 px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => onSelect(substitute.engine)}
                      className="mono text-[12px] text-ink transition-colors hover:text-accent-strong"
                    >
                      {substitute.engine}
                    </button>
                    <CoverageBadge coverage={substitute.coverage} />
                    {substitute.shared_tags.map((tag) => (
                      <Badge key={tag} tone="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-ink-muted text-pretty">
                    {substitute.note}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] leading-relaxed text-ink-muted text-pretty">
              {engine.single_source_note ||
                "No engine in this catalog version shares a capability tag with " +
                  engine.engine +
                  "."}
            </p>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Dependencies" icon={GitBranch} />
          <CardBody className="space-y-3">
            <Relations label="Depends on" engines={engine.depends_on} onSelect={onSelect} />
            <Relations label="Feeds" engines={engine.dependents} onSelect={onSelect} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Reachable paths"
            icon={Network}
            description="Valid chains that reach this engine from an ordinary query and location."
          />
          <CardBody>
            {paths?.path_count ? (
              <ul className="space-y-1.5">
                {paths.paths.slice(0, 6).map((path, index) => (
                  <li
                    key={index}
                    className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2"
                  >
                    <span className="mono truncate text-[11px] text-ink-muted">
                      {(path.engines as string[]).join(" -> ")}
                    </span>
                    <span className="mono shrink-0 text-[11px] text-ink-subtle">
                      {String(path.naive_cost)} cr
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-ink-subtle text-pretty">
                No chain reaches this engine from a plain query. It needs an identifier the
                caller must supply directly.
              </p>
            )}
          </CardBody>
        </Card>
      </div>
    </motion.div>
  );
}

function Relations({
  label,
  engines,
  onSelect,
}: {
  label: string;
  engines: string[];
  onSelect: (engine: string) => void;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-[0.06em] text-ink-subtle">{label}</p>
      {engines.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {engines.map((name) => (
            <button
              key={name}
              onClick={() => onSelect(name)}
              className="mono rounded-[var(--radius-xs)] border border-accent-muted/40 bg-accent-ghost px-1.5 py-0.5 text-[11px] text-accent-strong transition-colors hover:border-accent"
            >
              {name}
            </button>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-[12px] text-ink-subtle">nothing</p>
      )}
    </div>
  );
}
