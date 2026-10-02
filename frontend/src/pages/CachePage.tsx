/** The Cache Dashboard (section 50). */

import { motion } from "framer-motion";
import {
  Database,
  Flag,
  Layers,
  RefreshCw,
  Shield,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { itemVariants, listVariants } from "@/animations";
import { HorizontalBars, LayerDonut } from "@/components/charts";
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
import {
  useCacheDashboard,
  useCacheEntries,
  useGuardRejections,
  useInvalidateCache,
} from "@/hooks/useQueries";
import * as fmt from "@/lib/format";
import { PERMISSIONS, useSession } from "@/stores/session";

const GUARD_REASONS: Record<string, string> = {
  numeral_mismatch: "The numeral sets differed. iphone 16 is not iphone 17.",
  entity_mismatch: "The named entity sets differed. Koramangala is not Indiranagar.",
  version_mismatch: "The model or version identifiers differed.",
};

export function CachePage() {
  const { can } = useSession();
  const dashboard = useCacheDashboard(30);
  const [engineFilter, setEngineFilter] = React.useState("");
  const entries = useCacheEntries({ engine: engineFilter || undefined, limit: 50 });
  const rejections = useGuardRejections(50);
  const invalidate = useInvalidateCache();

  const canInvalidate = can(PERMISSIONS.cacheInvalidate);

  async function doInvalidate(engine?: string) {
    try {
      const result = await invalidate.mutateAsync({ engine: engine ?? null });
      toast.success("Cache invalidated", { description: result.message });
      dashboard.refetch();
      entries.refetch();
    } catch (error) {
      toast.error("Could not invalidate", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (dashboard.isError) {
    return <ErrorMessage error={dashboard.error} onRetry={() => dashboard.refetch()} />;
  }

  const data = dashboard.data;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Cache"
        icon={Database}
        description="Four layers: exact in Redis, semantic in pgvector, the SerpApi Searches Archive, then live. Only the last one spends credits."
        actions={
          canInvalidate ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => doInvalidate()}
              disabled={invalidate.isPending}
            >
              <Trash2 />
              Invalidate project cache
            </Button>
          ) : null
        }
      />

      <motion.div variants={itemVariants} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {dashboard.isLoading ? (
          Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-28" />)
        ) : (
          <>
            <StatCard
              label="Hit rate"
              value={fmt.percent(data?.hit_rate ?? 0)}
              tone="warm"
              icon={Database}
              hint="Lookups served without a live upstream call."
            />
            <StatCard
              label="Durable entries"
              value={data?.entries ?? 0}
              icon={Layers}
              hint="PostgreSQL is the source of truth. A Redis restart loses no credits."
            />
            <StatCard
              label="Guard rejections"
              value={data?.guard_rejections.total ?? 0}
              tone="accent"
              icon={ShieldAlert}
              hint="Near-matches the entity and numeral guard refused, regardless of cosine score."
            />
            <StatCard
              label="False hit reports"
              value={data?.false_hit_reports ?? 0}
              tone={data?.false_hit_reports ? "danger" : "neutral"}
              icon={Flag}
              hint="Filed from the Run Inspector when a semantic hit was wrong."
            />
          </>
        )}
      </motion.div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Layer distribution" icon={Layers}>
          <Card>
            <CardBody>
              {dashboard.isLoading ? (
                <Skeleton className="h-52" />
              ) : (
                <LayerDonut layers={data?.layers ?? {}} />
              )}
            </CardBody>
          </Card>
        </Section>

        <Section
          title="Entries by engine"
          icon={Database}
          description="Mean TTL is what the adaptive controller settled on, not the prior it started from."
        >
          <Card>
            <CardBody>
              {dashboard.isLoading ? (
                <Skeleton className="h-52" />
              ) : (
                <HorizontalBars
                  data={(data?.by_engine ?? []).slice(0, 8).map((row) => ({
                    label: row.engine,
                    value: row.entries,
                  }))}
                  formatter={(value) => value + " entries"}
                />
              )}
            </CardBody>
          </Card>
        </Section>
      </div>

      <Tabs defaultValue="entries">
        <TabsList>
          <TabsTrigger value="entries">
            <Database />
            Entries
          </TabsTrigger>
          <TabsTrigger value="guard">
            <Shield />
            Guard rejections
          </TabsTrigger>
          <TabsTrigger value="partitions">
            <Layers />
            Partitions and storage
          </TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------ entries */}
        <TabsContent value="entries" className="pt-4">
          <div className="space-y-3">
            <Input
              value={engineFilter}
              onChange={(event) => setEngineFilter(event.target.value)}
              placeholder="Filter by engine"
              className="max-w-xs"
            />
            <Card>
              {entries.isLoading ? (
                <CardBody className="space-y-2">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <Skeleton key={index} className="h-10" />
                  ))}
                </CardBody>
              ) : entries.data?.items.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] text-left">
                    <thead>
                      <tr className="border-b border-line text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                        <th className="px-4 py-2.5 font-medium">Query</th>
                        <th className="px-3 py-2.5 font-medium">Engine</th>
                        <th className="px-3 py-2.5 font-medium">Locale</th>
                        <th className="px-3 py-2.5 font-medium">Guard tokens</th>
                        <th className="px-3 py-2.5 font-medium">TTL</th>
                        <th className="px-3 py-2.5 text-right font-medium">Hits</th>
                        <th className="px-4 py-2.5 text-right font-medium">Expires</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {entries.data.items.map((entry) => (
                        <tr key={entry.id} className="align-top">
                          <td className="max-w-sm px-4 py-2.5">
                            <p className="truncate text-[12px] text-ink">
                              {entry.query_text || "(identifier lookup)"}
                            </p>
                            <p className="mono mt-0.5 text-[10px] text-ink-subtle">
                              {entry.request_hash.slice(0, 12)}
                            </p>
                          </td>
                          <td className="px-3 py-2.5 mono text-[12px] text-ink-muted">
                            {entry.engine}
                          </td>
                          <td className="px-3 py-2.5 mono text-[11px] text-ink-subtle">
                            {[entry.gl, entry.hl].filter(Boolean).join(" ") || "-"}
                          </td>
                          <td className="max-w-[200px] px-3 py-2.5">
                            <div className="flex flex-wrap gap-1">
                              {[...entry.entities, ...entry.numerals, ...entry.versions]
                                .slice(0, 4)
                                .map((token) => (
                                  <span
                                    key={token}
                                    className="mono rounded-[var(--radius-xs)] border border-line px-1 py-0.5 text-[10px] text-ink-subtle"
                                  >
                                    {token}
                                  </span>
                                ))}
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <p className="mono text-[11px] text-ink-muted">
                              {fmt.seconds(entry.ttl_seconds)}
                            </p>
                            <p className="text-[10px] text-ink-subtle">{entry.ttl_source}</p>
                          </td>
                          <td className="px-3 py-2.5 text-right mono tabular text-[12px] text-ink">
                            {entry.hit_count}
                          </td>
                          <td className="px-4 py-2.5 text-right text-[11px] text-ink-subtle">
                            {entry.invalidated_at ? (
                              <Badge tone="danger">invalidated</Badge>
                            ) : (
                              fmt.ago(entry.expires_at)
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <CardBody>
                  <EmptyState
                    icon={Database}
                    title="No cache entries"
                    description="Entries appear once a run fetches something live. Each one records the normalised request, the extracted guard tokens, and the TTL the adaptive controller assigned."
                  />
                </CardBody>
              )}
            </Card>
          </div>
        </TabsContent>

        {/* -------------------------------------------------- guard */}
        <TabsContent value="guard" className="pt-4">
          <Card>
            <CardHeader
              title="Entity and numeral guard"
              icon={Shield}
              description="Every near-match rejected, logged so the similarity threshold can be tuned with evidence rather than intuition."
              action={
                data?.guard_rejections.total ? (
                  <div className="flex gap-1.5">
                    {Object.entries(data.guard_rejections.by_reason).map(([reason, count]) => (
                      <Tooltip key={reason} content={GUARD_REASONS[reason]}>
                        <Badge tone="accent" className="mono">
                          {reason.replace("_mismatch", "")} {count}
                        </Badge>
                      </Tooltip>
                    ))}
                  </div>
                ) : null
              }
            />
            {rejections.isLoading ? (
              <CardBody className="space-y-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton key={index} className="h-14" />
                ))}
              </CardBody>
            ) : rejections.data?.items.length ? (
              <ul className="divide-y divide-line">
                {rejections.data.items.map((rejection) => (
                  <li key={rejection.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="danger">{rejection.reason.replace(/_/g, " ")}</Badge>
                      <span className="mono text-[11px] text-ink-subtle">
                        cosine {rejection.similarity.toFixed(4)}
                      </span>
                      <span className="mono text-[11px] text-ink-subtle">
                        {rejection.engine}
                      </span>
                      <span className="ml-auto text-[11px] text-ink-subtle">
                        {fmt.ago(rejection.created_at)}
                      </span>
                    </div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">
                          requested
                        </p>
                        <p className="mt-0.5 text-[12px] text-ink">{rejection.incoming_query}</p>
                      </div>
                      <div className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2">
                        <p className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">
                          cached candidate
                        </p>
                        <p className="mt-0.5 text-[12px] text-ink">
                          {rejection.candidate_query}
                        </p>
                      </div>
                    </div>
                    <p className="mt-1.5 text-[11px] text-ink-subtle text-pretty">
                      {GUARD_REASONS[rejection.reason] ??
                        "The extracted token sets were not identical."}{" "}
                      The hit was rejected regardless of the cosine score.
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <CardBody>
                <EmptyState
                  icon={Shield}
                  title="No rejections recorded"
                  description="The guard rejects a semantic hit whenever the numeral, version or named-entity sets differ, however similar the two queries look. Nothing has tripped it in this window."
                />
              </CardBody>
            )}
          </Card>
        </TabsContent>

        {/* --------------------------------------------- partitions */}
        <TabsContent value="partitions" className="pt-4">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Partitions"
                icon={Layers}
                description="Project-level isolation by default. An org: prefix means a shared organization cache is enabled."
              />
              <CardBody>
                {data?.partitions.length ? (
                  <ul className="space-y-1.5">
                    {data.partitions.map((partition) => (
                      <li
                        key={partition.partition_key}
                        className="flex items-center justify-between rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-2.5 py-2"
                      >
                        <span className="mono truncate text-[11px] text-ink-muted">
                          {partition.partition_key}
                        </span>
                        <span className="mono text-[11px] tabular text-ink">
                          {partition.entries}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[12px] text-ink-subtle">No partitions yet.</p>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Storage" icon={RefreshCw} />
              <CardBody className="space-y-3">
                <Row label="Payload bytes" value={fmt.bytes(data?.bytes_stored ?? 0)} />
                <Row label="Durable entries" value={String(data?.entries ?? 0)} />
                <Row
                  label="Redis"
                  value={String(
                    (data?.redis as { status?: string })?.status ?? "unknown",
                  )}
                />
                <Row
                  label="Redis memory"
                  value={String(
                    (data?.redis as { used_memory_human?: string })?.used_memory_human ?? "-",
                  )}
                />
                <p className="pt-1 text-[11px] leading-relaxed text-ink-subtle text-pretty">
                  Redis is the hot layer and is not the source of truth. On restart it
                  repopulates from the durable PostgreSQL index as requests arrive, and large
                  payloads live in content-addressable object storage, so identical responses
                  deduplicate.
                </p>
              </CardBody>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-line pb-2 last:border-0">
      <span className="text-[12px] text-ink-subtle">{label}</span>
      <span className="mono text-[12px] tabular text-ink">{value}</span>
    </div>
  );
}
