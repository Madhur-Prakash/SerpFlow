/**
 * The Run Inspector (section 47) - the primary debugging surface.
 *
 * Raw payloads are gated behind their own permission, separately from run
 * visibility: a google_maps_contributor_reviews payload is one named person's
 * complete review history, not anonymous infrastructure data.
 */

import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Clock,
  Eye,
  EyeOff,
  FileText,
  Flag,
  Route,
  RotateCcw,
  Shield,
  Terminal,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { itemVariants, listVariants } from "@/animations";
import { PlanGraph } from "@/components/graphs/PlanGraph";
import {
  CacheLayerBadge,
  CostComparison,
  EmptyState,
  ErrorMessage,
  FreshnessBadge,
  KeyValue,
  ModeBadge,
  PageHeader,
  StatusDot,
} from "@/components/shared";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  Label,
  Sheet,
  SheetContent,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Tooltip,
} from "@/components/ui";
import { useReplayRun, useReportFalseHit, useRun } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { PERMISSIONS, useSession } from "@/stores/session";
import type { PayloadResponse, Step } from "@/types/api";

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { can } = useSession();
  const run = useRun(runId);
  const replay = useReplayRun();
  const falseHit = useReportFalseHit();

  const [payloadStep, setPayloadStep] = React.useState<Step | null>(null);
  const [payload, setPayload] = React.useState<PayloadResponse | null>(null);
  const [reportOpen, setReportOpen] = React.useState(false);
  const [reportStep, setReportStep] = React.useState<Step | null>(null);
  const [note, setNote] = React.useState("");

  const canPayload = can(PERMISSIONS.payloadRead);
  const canReplay = can(PERMISSIONS.runReplay);

  async function openPayload(step: Step) {
    if (!runId) return;
    setPayloadStep(step);
    setPayload(null);
    try {
      setPayload(await api.stepPayload(runId, step.id));
    } catch (error) {
      toast.error("Could not load the payload", {
        description: error instanceof Error ? error.message : String(error),
      });
      setPayloadStep(null);
    }
  }

  async function submitReport() {
    if (!runId) return;
    try {
      const result = await falseHit.mutateAsync({
        runId,
        stepId: reportStep?.id,
        note,
        invalidate: true,
      });
      toast.success("Report filed", { description: result.message });
      setReportOpen(false);
      setNote("");
      run.refetch();
    } catch (error) {
      toast.error("Could not file the report", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async function doReplay() {
    if (!runId) return;
    try {
      const result = await replay.mutateAsync(runId);
      toast.success("Replayed", {
        description:
          "New run " +
          fmt.shortId(result.run.id) +
          " - " +
          (result.plan.marginal_replan_changed_selection
            ? "marginal replanning chose a different plan this time."
            : "the same plan was selected."),
      });
      navigate("/app/runs/" + result.run.id);
    } catch (error) {
      toast.error("Replay failed", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (run.isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-20" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (run.isError) return <ErrorMessage error={run.error} onRetry={() => run.refetch()} />;
  if (!run.data) return null;

  const data = run.data;
  const plan = data.plan;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Run Inspector"
        icon={Activity}
        description={data.intent}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setReportStep(data.steps.find((step) => step.cache_layer === "semantic") ?? null);
                setReportOpen(true);
              }}
            >
              <Flag />
              Report false hit
            </Button>
            {canReplay ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={doReplay}
                disabled={replay.isPending}
              >
                <RotateCcw />
                {replay.isPending ? "Replaying" : "Replay"}
              </Button>
            ) : null}
            {plan ? (
              <Button asChild variant="primary" size="sm">
                <Link to={"/app/plans/" + plan.id}>
                  <Route />
                  Plan Inspector
                </Link>
              </Button>
            ) : null}
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <StatusDot status={data.status} />
          <ModeBadge
            mode={data.mode}
            reason={String(data.provenance?.mode_reason ?? "")}
          />
          <Badge tone="outline" className="mono">
            {fmt.shortId(data.id)}
          </Badge>
          {data.replay_of_run_id ? (
            <Badge tone="replay">
              replay of {fmt.shortId(data.replay_of_run_id)}
            </Badge>
          ) : null}
          {data.max_pii_risk === "high" ? (
            <Tooltip content="This run cached named individuals' review histories, so it is retained for 7 days instead of 30.">
              <Badge tone="danger">
                <Shield />
                high PII risk
              </Badge>
            </Tooltip>
          ) : null}
          <span className="text-[12px] text-ink-subtle">{fmt.datetime(data.created_at)}</span>
        </div>
      </PageHeader>

      {data.error_code ? (
        <Alert tone="danger" icon={AlertTriangle} title={data.error_code}>
          {data.error_message}
        </Alert>
      ) : null}

      {plan?.marginal_replan_changed_selection ? (
        <motion.div variants={itemVariants}>
          <Alert tone="warm" icon={Route} title="Marginal cost changed which plan was selected">
            {plan.replan_explanation}
          </Alert>
        </motion.div>
      ) : null}

      <motion.div variants={itemVariants} className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Executed plan" icon={Route} />
          <CardBody className="space-y-5">
            {plan ? <PlanGraph plan={plan} /> : null}
            <CostComparison
              naive={data.naive_cost}
              marginal={data.marginal_cost}
              actual={data.credits_spent}
              projection={plan?.projected_full_scale_cost}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Provenance" icon={Terminal} />
          <CardBody>
            <KeyValue
              columns={1}
              rows={[
                { label: "Run", value: data.id, mono: true },
                { label: "Plan", value: plan?.id ?? "-", mono: true },
                { label: "Trigger", value: data.trigger },
                { label: "Principal", value: data.principal_type },
                {
                  label: "Catalog version",
                  value: plan?.catalog_version ?? "-",
                  mono: true,
                },
                {
                  label: "Cache layers",
                  value:
                    Object.entries(data.cache_summary)
                      .filter(([, count]) => count > 0)
                      .map(([layer, count]) => layer + " " + count)
                      .join(", ") || "none",
                  mono: true,
                },
                { label: "Duration", value: fmt.ms(data.duration_ms), mono: true },
                {
                  label: "Retention",
                  value: data.expires_at
                    ? fmt.datetime(data.expires_at) +
                      (data.max_pii_risk === "high" ? " (7 day PII window)" : "")
                    : "-",
                },
                { label: "Trace", value: data.trace_id ?? "-", mono: true },
              ]}
            />
          </CardBody>
        </Card>
      </motion.div>

      {/* ------------------------------------------------------- steps */}
      <motion.div variants={itemVariants}>
        <Tabs defaultValue="steps">
          <TabsList>
            <TabsTrigger value="steps">
              <Activity />
              Steps
            </TabsTrigger>
            <TabsTrigger value="candidates">
              <Route />
              Candidates ({plan?.candidate_count ?? 0})
            </TabsTrigger>
            <TabsTrigger value="trace">
              <Clock />
              Stage trace
            </TabsTrigger>
            <TabsTrigger value="results">
              <FileText />
              Results
            </TabsTrigger>
          </TabsList>

          <TabsContent value="steps" className="pt-4">
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-left">
                  <thead>
                    <tr className="border-b border-line text-[11px] uppercase tracking-[0.06em] text-ink-subtle">
                      <th className="px-4 py-2.5 font-medium">#</th>
                      <th className="px-3 py-2.5 font-medium">Engine</th>
                      <th className="px-3 py-2.5 font-medium">Parameters</th>
                      <th className="px-3 py-2.5 font-medium">Layer</th>
                      <th className="px-3 py-2.5 font-medium">Freshness</th>
                      <th className="px-3 py-2.5 text-right font-medium">Credits</th>
                      <th className="px-3 py-2.5 text-right font-medium">Latency</th>
                      <th className="px-4 py-2.5 text-right font-medium">Payload</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.steps.map((step) => (
                      <tr key={step.id} className="align-top">
                        <td className="px-4 py-3 mono text-[12px] text-ink-subtle">
                          {step.index}
                        </td>
                        <td className="px-3 py-3">
                          <p className="mono text-[12px] text-ink">{step.engine}</p>
                          <p className="mt-0.5 text-[11px] text-ink-subtle">
                            {step.fan_out > 1 ? step.fan_out + " calls" : "1 call"}
                            {step.pii_risk === "high" ? " - high PII risk" : ""}
                          </p>
                        </td>
                        <td className="max-w-xs px-3 py-3">
                          <code className="block truncate text-[11px] text-ink-muted">
                            {Object.entries(step.parameters)
                              .map(([key, value]) => key + "=" + String(value))
                              .join("  ") || "-"}
                          </code>
                          {step.matched_query ? (
                            <p className="mt-1 truncate text-[11px] text-accent-strong">
                              matched: {step.matched_query}
                              {step.similarity
                                ? "  (" + step.similarity.toFixed(4) + ")"
                                : ""}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">
                          <CacheLayerBadge layer={step.cache_layer} />
                          {step.age_seconds !== null && step.age_seconds !== undefined ? (
                            <p className="mt-1 text-[11px] text-ink-subtle">
                              age {fmt.seconds(step.age_seconds)}
                            </p>
                          ) : null}
                          {step.ttl_source ? (
                            <p className="mono mt-0.5 text-[10px] text-ink-subtle">
                              {step.ttl_source}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">
                          <FreshnessBadge level={step.freshness_requirement} />
                        </td>
                        <td className="px-3 py-3 text-right mono tabular text-[12px] text-ink">
                          {fmt.credits(step.credits)}
                        </td>
                        <td className="px-3 py-3 text-right mono tabular text-[12px] text-ink-subtle">
                          {fmt.ms(step.latency_ms)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {canPayload && step.payload_ref ? (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => openPayload(step)}
                              aria-label="View raw payload"
                            >
                              <Eye />
                            </Button>
                          ) : (
                            <Tooltip content="Raw payloads need the payload:read permission, which is granted separately from run visibility.">
                              <span className="inline-flex text-ink-subtle">
                                <EyeOff className="size-4" />
                              </span>
                            </Tooltip>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="candidates" className="pt-4">
            {plan?.candidates.length ? (
              <div className="space-y-3">
                {plan.candidates.map((candidate) => (
                  <Card
                    key={candidate.id}
                    className={candidate.selected ? "border-warm/45" : undefined}
                  >
                    <CardBody className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {candidate.selected ? <Badge tone="warm">selected</Badge> : null}
                        <span className="mono text-[13px] text-ink">{candidate.label}</span>
                        <Badge tone="outline" className="mono">
                          cold {candidate.naive_cost}
                        </Badge>
                        <Badge
                          tone={
                            candidate.marginal_cost < candidate.naive_cost ? "warm" : "outline"
                          }
                          className="mono"
                        >
                          marginal {candidate.marginal_cost}
                        </Badge>
                        <Badge tone="outline">{candidate.coverage}</Badge>
                        <span className="ml-auto mono text-[11px] text-ink-subtle">
                          cold rank {candidate.naive_rank} - marginal rank{" "}
                          {candidate.marginal_rank}
                        </span>
                      </div>
                      <PlanGraph candidate={candidate} compact />
                      {candidate.rejection_reason ? (
                        <p className="text-[12px] leading-relaxed text-ink-subtle text-pretty">
                          {candidate.rejection_reason}
                        </p>
                      ) : null}
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Route}
                title="No candidates recorded"
                description="This run executed without a persisted plan, which happens for background retries that reuse an earlier plan."
              />
            )}
          </TabsContent>

          <TabsContent value="trace" className="pt-4">
            <Card>
              <CardBody>
                {plan?.stage_trace.length ? (
                  <ol className="space-y-1.5">
                    {plan.stage_trace.map((event, index) => (
                      <li
                        key={index}
                        className="flex items-baseline gap-3 rounded-[var(--radius-xs)] px-2 py-1.5 odd:bg-surface-sunken"
                      >
                        <span className="mono w-16 shrink-0 text-right text-[11px] tabular text-ink-subtle">
                          {fmt.ms(event.elapsed_ms)}
                        </span>
                        <span className="mono w-52 shrink-0 text-[12px] text-ink">
                          {event.stage}
                        </span>
                        <Badge tone={event.status === "complete" ? "warm" : "outline"}>
                          {event.status}
                        </Badge>
                        <span className="min-w-0 flex-1 truncate text-[11px] text-ink-subtle">
                          {JSON.stringify(event.detail).slice(0, 160)}
                        </span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <EmptyState
                    icon={Clock}
                    title="No stage trace"
                    description="The stage trace is recorded by the planner as each stage completes, and is the same data the live pipeline animation consumes."
                  />
                )}
              </CardBody>
            </Card>
          </TabsContent>

          <TabsContent value="results" className="pt-4">
            <Card>
              <CardBody>
                {data.result_summary?.items?.length ? (
                  <ul className="divide-y divide-line">
                    {data.result_summary.items.map((item, index) => (
                      <li key={index} className="py-2.5 first:pt-0">
                        <p className="text-[13px] text-ink">{item.title ?? "(untitled)"}</p>
                        {item.snippet ? (
                          <p className="mt-0.5 text-[12px] text-ink-subtle">{item.snippet}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    icon={FileText}
                    title="No summarised results"
                    description="The terminal engine returned no list-shaped results. The full payload is still stored and available per step."
                  />
                )}
              </CardBody>
            </Card>
          </TabsContent>
        </Tabs>
      </motion.div>

      {/* --------------------------------------------- payload drawer */}
      <Sheet open={Boolean(payloadStep)} onOpenChange={(open) => !open && setPayloadStep(null)}>
        <SheetContent width="max-w-3xl">
          <div className="border-b border-line px-5 py-4">
            <p className="text-sm font-semibold text-ink">Raw payload</p>
            <p className="mono mt-1 text-[12px] text-ink-subtle">
              {payloadStep?.engine} - step {payloadStep?.index}
            </p>
            {payload?.pii_risk === "high" ? (
              <Alert tone="danger" icon={Shield} className="mt-3">
                This payload contains personal data. Cached SERPs are not anonymous
                infrastructure data, and this one is retained for 7 days rather than 30.
              </Alert>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-5">
            {payload ? (
              <pre className="mono whitespace-pre-wrap break-all rounded-[var(--radius-sm)] border border-line bg-surface-sunken p-3 text-[11px] leading-relaxed text-ink-muted">
                {JSON.stringify(payload.payload, null, 2)}
              </pre>
            ) : (
              <Skeleton className="h-64" />
            )}
          </div>
        </SheetContent>
      </Sheet>

      {/* ------------------------------------------ false hit dialog */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent>
          <DialogHeader
            title="Report a false semantic hit"
            description="This records the near-match, increments serpflow_semantic_false_hit_reports_total, and invalidates the offending cache entry so it cannot be served again."
          />
          <div className="space-y-3 px-5 py-4">
            {reportStep ? (
              <div className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2">
                <p className="mono text-[12px] text-ink">{reportStep.engine}</p>
                {reportStep.matched_query ? (
                  <p className="mt-1 text-[12px] text-ink-subtle">
                    matched {reportStep.matched_query}
                    {reportStep.similarity
                      ? " at cosine " + reportStep.similarity.toFixed(4)
                      : ""}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-[12px] text-ink-subtle">
                No semantic hit was recorded on this run. Filing anyway still records the
                report against the run.
              </p>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="note">What was wrong?</Label>
              <Textarea
                id="note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="The cached entry was for a different neighbourhood."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setReportOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={submitReport}
              disabled={falseHit.isPending}
            >
              <Flag />
              File report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
