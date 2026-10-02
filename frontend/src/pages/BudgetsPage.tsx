/**
 * Budgets and policies (sections 38, 39, 40, 51).
 *
 * The page keeps two numbers visibly apart: the SerpFlow cap you configured,
 * and the quota left on the SerpApi account. They are not the same thing, and
 * they diverge the moment that credential is used anywhere else.
 */

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Building2,
  Key,
  Plus,
  RefreshCw,
  Server,
  Settings,
  Terminal,
  Trash2,
  Wallet,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { itemVariants, listVariants } from "@/animations";
import { UtilizationBar } from "@/components/charts";
import {
  EmptyState,
  ErrorMessage,
  PageHeader,
  Section,
  StatCard,
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
  Field,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Switch,
  Tooltip,
} from "@/components/ui";
import { useBudgets, useProjects } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { PERMISSIONS, useSession } from "@/stores/session";

const SCOPE_ICON = {
  organization: Building2,
  project: Terminal,
  api_key: Key,
  session: Server,
} as const;

const EXHAUSTION_NOTE: Record<string, string> = {
  error: "Refuse the request with BUDGET_EXHAUSTED. The caller knows immediately.",
  stale: "Serve the cached answer even if it is past its freshness bound, and say so.",
  queue: "Accept the request and execute it when the next period opens.",
};

export function BudgetsPage() {
  const { can, project } = useSession();
  const budgets = useBudgets();
  const projects = useProjects();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [reconciling, setReconciling] = React.useState(false);

  const canWrite = can(PERMISSIONS.budgetWrite);

  async function reconcile() {
    setReconciling(true);
    try {
      const result = await api.reconcileQuota();
      toast[result.ok ? "success" : "warning"]("Quota reconciliation", {
        description: result.message,
      });
      budgets.refetch();
    } catch (error) {
      toast.error("Could not queue reconciliation", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setReconciling(false);
    }
  }

  if (budgets.isError) {
    return <ErrorMessage error={budgets.error} onRetry={() => budgets.refetch()} />;
  }

  const data = budgets.data;
  const exhaustion = data?.projected_exhaustion;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Budgets"
        icon={Wallet}
        description="Caps at organization, project, API key and session scope. The tightest applicable one decides."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={reconcile} disabled={reconciling}>
              <RefreshCw />
              Reconcile upstream quota
            </Button>
            {canWrite ? (
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus />
                New budget
              </Button>
            ) : null}
          </>
        }
      />

      <motion.div variants={itemVariants} className="grid gap-3 sm:grid-cols-3">
        {budgets.isLoading ? (
          Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-28" />)
        ) : (
          <>
            <StatCard
              label="Credits spent"
              value={data?.credits_spent_total ?? 0}
              unit="cr"
              tone="spend"
              icon={Wallet}
            />
            <StatCard
              label="Credits saved"
              value={data?.credits_saved_total ?? 0}
              unit="cr"
              tone="warm"
              icon={RefreshCw}
            />
            <StatCard
              label="Projected exhaustion"
              value={
                exhaustion?.exhausts_at
                  ? fmt.ago(exhaustion.exhausts_at)
                  : "not projected"
              }
              animate={false}
              icon={AlertTriangle}
              hint={
                exhaustion?.burn_rate_per_hour
                  ? exhaustion.burn_rate_per_hour + " credits an hour at the current rate."
                  : "No spend recorded in the current period."
              }
            />
          </>
        )}
      </motion.div>

      {/* Section 39: these two are never conflated. */}
      <motion.div variants={itemVariants} className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="SerpFlow budgets"
            icon={Wallet}
            description="Your own caps. When one is exhausted the fix is to raise it."
          />
          <CardBody className="space-y-3">
            {budgets.isLoading ? (
              Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-16" />
              ))
            ) : data?.budgets.length ? (
              data.budgets.map((budget) => {
                const Icon = SCOPE_ICON[budget.scope] ?? Wallet;
                const projectName = projects.data?.find(
                  (candidate) => candidate.id === budget.scope_id,
                )?.name;
                return (
                  <div
                    key={budget.id}
                    className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Icon className="size-3.5 text-ink-subtle" />
                      <span className="text-[12px] font-medium text-ink">
                        {budget.name || budget.scope}
                      </span>
                      <Badge tone="outline">{budget.scope}</Badge>
                      {projectName ? (
                        <span className="text-[11px] text-ink-subtle">{projectName}</span>
                      ) : null}
                      <Tooltip content={EXHAUSTION_NOTE[budget.on_exhausted]}>
                        <Badge tone="outline">on exhausted: {budget.on_exhausted}</Badge>
                      </Tooltip>
                      <span className="mono ml-auto text-[12px] tabular text-ink">
                        {fmt.credits(budget.current_usage)} / {fmt.credits(budget.limit_credits)}
                      </span>
                    </div>
                    <UtilizationBar
                      used={budget.current_usage}
                      limit={budget.limit_credits}
                      alertAt={budget.alert_at}
                      className="mt-2"
                    />
                    <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-subtle">
                      <span>
                        {budget.period} period, alert at {fmt.percent(budget.alert_at, 0)}
                      </span>
                      <span className="mono">{fmt.credits(budget.remaining)} left</span>
                    </div>
                  </div>
                );
              })
            ) : (
              <EmptyState
                icon={Wallet}
                title="No budgets configured"
                description="Without a budget, SerpFlow will execute whatever a plan costs. A budget makes the planner reduce fan-out to fit rather than refuse, and records exactly what that reduction cost you."
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Upstream SerpApi quota"
            icon={Server}
            description="The account's own remaining searches. When this runs out the fix is upstream capacity, not a bigger budget here."
          />
          <CardBody className="space-y-3">
            {data?.upstream_quota.length ? (
              data.upstream_quota.map((quota) => (
                <div
                  key={quota.credential_id}
                  className="rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] font-medium text-ink">
                      {quota.name}
                    </span>
                    <Badge tone="outline" className="mono">
                      ...{quota.fingerprint.slice(-4)}
                    </Badge>
                  </div>
                  <dl className="mt-2 space-y-1.5">
                    <QuotaRow label="Plan" value={quota.upstream_plan ?? "unknown"} />
                    <QuotaRow
                      label="Searches left"
                      value={
                        quota.upstream_searches_left !== null &&
                        quota.upstream_searches_left !== undefined
                          ? fmt.credits(quota.upstream_searches_left)
                          : "unknown"
                      }
                    />
                    <QuotaRow
                      label="Last checked"
                      value={fmt.ago(quota.upstream_checked_at)}
                    />
                    {quota.divergence !== null && quota.divergence !== undefined ? (
                      <QuotaRow
                        label="Ledger divergence"
                        value={String(quota.divergence)}
                        tone={Math.abs(quota.divergence) > 5 ? "caution" : undefined}
                      />
                    ) : null}
                  </dl>
                  {quota.divergence !== null &&
                  quota.divergence !== undefined &&
                  Math.abs(quota.divergence) > 5 ? (
                    <Alert tone="caution" icon={AlertTriangle} className="mt-2">
                      SerpFlow recorded {quota.internal_spend_since_last} credits since the last
                      reconciliation while the account consumed{" "}
                      {quota.upstream_spend_since_last}. This credential is most likely in use
                      outside SerpFlow.
                    </Alert>
                  ) : null}
                </div>
              ))
            ) : (
              <EmptyState
                icon={Server}
                title="No upstream credential attached"
                description="Attach a SerpApi credential in Settings to reconcile SerpFlow's internal ledger against the account's real remaining quota. Test API keys route to the deterministic mock and never touch it."
              />
            )}
          </CardBody>
        </Card>
      </motion.div>

      {/* --------------------------------------------- project policy */}
      {project ? <ProjectPolicy projectId={project.id} /> : null}

      <CreateBudgetDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => budgets.refetch()}
      />
    </motion.div>
  );
}

function QuotaRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "caution";
}) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="text-[11px] text-ink-subtle">{label}</dt>
      <dd
        className={
          "mono text-[12px] tabular " + (tone === "caution" ? "text-caution" : "text-ink")
        }
      >
        {value}
      </dd>
    </div>
  );
}

function ProjectPolicy({ projectId }: { projectId: string }) {
  const projects = useProjects();
  const { can } = useSession();
  const project = projects.data?.find((candidate) => candidate.id === projectId);
  const [saving, setSaving] = React.useState(false);
  const canWrite = can(PERMISSIONS.policyWrite) || can(PERMISSIONS.projectWrite);

  if (!project) return null;

  async function update(patch: Record<string, unknown>) {
    setSaving(true);
    try {
      await api.updateProject(projectId, patch);
      toast.success("Policy updated");
      projects.refetch();
    } catch (error) {
      toast.error("Could not update the policy", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Section
      title="Project policy"
      icon={Settings}
      description="Engine allow and deny lists, semantic threshold, TTL overrides and cache scope."
    >
      <Card>
        <CardBody className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label="Semantic similarity threshold"
              hint="Below this, a semantic candidate is never considered. The entity guard runs on top and does not consult the score."
            >
              <Input
                type="number"
                step="0.01"
                min="0.5"
                max="1"
                defaultValue={project.semantic_threshold ?? 0.95}
                disabled={!canWrite || saving}
                onBlur={(event) =>
                  update({ semantic_threshold: Number(event.target.value) })
                }
              />
            </Field>

            <Field
              label="Engine denylist"
              hint="Comma separated. A denied engine is rejected during planning, not mid-run."
            >
              <Input
                defaultValue={project.engine_denylist.join(", ")}
                disabled={!canWrite || saving}
                placeholder="yelp, yelp_reviews"
                onBlur={(event) =>
                  update({
                    engine_denylist: event.target.value
                      .split(",")
                      .map((value) => value.trim())
                      .filter(Boolean),
                  })
                }
              />
            </Field>

            <Field
              label="Retention, standard"
              hint="Days before ordinary run payloads are deleted."
            >
              <Input
                type="number"
                min="1"
                defaultValue={project.retention_days ?? 30}
                disabled={!canWrite || saving}
                onBlur={(event) => update({ retention_days: Number(event.target.value) })}
              />
            </Field>

            <Field
              label="Retention, high PII risk"
              hint="Shorter window for payloads containing named individuals' histories."
            >
              <Input
                type="number"
                min="1"
                defaultValue={project.retention_high_pii_days ?? 7}
                disabled={!canWrite || saving}
                onBlur={(event) =>
                  update({ retention_high_pii_days: Number(event.target.value) })
                }
              />
            </Field>
          </div>

          {/* Section 51: say what enabling this actually does, where it is enabled. */}
          <div className="rounded-[var(--radius-sm)] border border-caution/30 bg-caution-ghost px-3 py-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[13px] font-medium text-caution">
                  Shared organization cache
                </p>
                <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-ink-muted text-pretty">
                  This allows one project to benefit from another project's upstream spend. It
                  crosses a billing and a data boundary: results fetched for one project become
                  readable by another. Spend stays attributed to the project that fetched;
                  savings are attributed to the project that benefited.
                </p>
              </div>
              <Switch
                checked={project.shared_cache_enabled}
                disabled={!canWrite || saving}
                onCheckedChange={(checked) => update({ shared_cache_enabled: checked })}
              />
            </div>
          </div>
        </CardBody>
      </Card>
    </Section>
  );
}

function CreateBudgetDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { me, project } = useSession();
  const [scope, setScope] = React.useState<"organization" | "project">("project");
  const [limit, setLimit] = React.useState("250");
  const [period, setPeriod] = React.useState("monthly");
  const [onExhausted, setOnExhausted] = React.useState("error");
  const [saving, setSaving] = React.useState(false);

  async function submit() {
    setSaving(true);
    try {
      await api.createBudget({
        scope,
        scope_id: scope === "organization" ? me?.org_id : project?.id,
        limit_credits: Number(limit),
        period,
        on_exhausted: onExhausted,
        alert_at: 0.8,
        name: scope === "organization" ? "Organization budget" : project?.name + " budget",
      });
      toast.success("Budget created");
      onOpenChange(false);
      onCreated();
    } catch (error) {
      toast.error("Could not create the budget", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="New budget"
          description="The tightest applicable budget decides. A session or key budget can be stricter than the project it belongs to."
        />
        <div className="space-y-4 px-5 py-4">
          <Field label="Scope">
            <Select value={scope} onValueChange={(value) => setScope(value as typeof scope)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="organization">Organization</SelectItem>
                <SelectItem value="project">Project</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Limit" hint="The SerpApi free tier is 250 searches a month.">
            <Input
              type="number"
              min="1"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
            />
          </Field>
          <Field label="Period">
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="monthly">Monthly</SelectItem>
                <SelectItem value="total">Total</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="When exhausted" hint={EXHAUSTION_NOTE[onExhausted]}>
            <Select value={onExhausted} onValueChange={setOnExhausted}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="error">Error</SelectItem>
                <SelectItem value="stale">Serve stale</SelectItem>
                <SelectItem value="queue">Queue</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={submit} disabled={saving}>
            <Plus />
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export { Trash2 };
