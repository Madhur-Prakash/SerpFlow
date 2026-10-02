/** The audit log (section 54). Append-only, hash chained, exportable. */

import { motion } from "framer-motion";
import { CheckCircle, Download, Link2, Shield, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { itemVariants, listVariants } from "@/animations";
import { EmptyState, ErrorMessage, PageHeader } from "@/components/shared";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Input,
  Skeleton,
  Tooltip,
} from "@/components/ui";
import { useAudit, useAuditVerify } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { PERMISSIONS, useSession } from "@/stores/session";

export function AuditPage() {
  const { can } = useSession();
  const [action, setAction] = React.useState("");
  const [page, setPage] = React.useState(0);
  const limit = 40;
  const audit = useAudit({ action: action || undefined, limit, offset: page * limit });
  const verify = useAuditVerify();
  const [exporting, setExporting] = React.useState(false);

  async function exportLog() {
    setExporting(true);
    try {
      const result = await api.exportAudit(10000);
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "serpflow-audit-" + new Date().toISOString().slice(0, 10) + ".json";
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success("Exported " + result.count + " entries");
    } catch (error) {
      toast.error("Export failed", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setExporting(false);
    }
  }

  if (audit.isError) {
    return <ErrorMessage error={audit.error} onRetry={() => audit.refetch()} />;
  }

  const total = audit.data?.total ?? 0;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-6">
      <PageHeader
        title="Audit Log"
        icon={Shield}
        description="Every privileged action, in order, with the state before and after. Append-only at the database level and chained by hash, so tampering is detectable."
        actions={
          can(PERMISSIONS.auditExport) ? (
            <Button variant="outline" size="sm" onClick={exportLog} disabled={exporting}>
              <Download />
              Export
            </Button>
          ) : null
        }
      />

      <motion.div variants={itemVariants}>
        {verify.isLoading ? (
          <Skeleton className="h-14" />
        ) : verify.data?.valid ? (
          <Alert
            tone="warm"
            icon={CheckCircle}
            title={"Hash chain verified across " + verify.data.entries_checked + " entries"}
          >
            Each entry stores the hash of the one before it. The chain reproduces exactly, so
            no entry has been inserted, edited or removed.
            {verify.data.head ? (
              <span className="mono ml-1 text-[11px] opacity-70">
                head {verify.data.head.slice(0, 16)}
              </span>
            ) : null}
          </Alert>
        ) : (
          <Alert tone="danger" icon={XCircle} title="Hash chain broken">
            The chain diverges at sequence {verify.data?.break_at_sequence}:{" "}
            {verify.data?.reason}
          </Alert>
        )}
      </motion.div>

      <motion.div variants={itemVariants} className="flex flex-wrap items-center gap-2">
        <Input
          value={action}
          onChange={(event) => {
            setAction(event.target.value);
            setPage(0);
          }}
          placeholder="Filter by action, for example credential.rotated"
          className="max-w-sm"
        />
        <span className="ml-auto text-[12px] text-ink-subtle">
          {total} {fmt.plural(total, "entry", "entries")}
        </span>
      </motion.div>

      <motion.div variants={itemVariants}>
        <Card>
          {audit.isLoading ? (
            <CardBody className="space-y-2">
              {Array.from({ length: 10 }).map((_, index) => (
                <Skeleton key={index} className="h-11" />
              ))}
            </CardBody>
          ) : audit.data?.items.length ? (
            <>
              <ul className="divide-y divide-line">
                {audit.data.items.map((entry) => (
                  <li key={entry.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mono w-12 shrink-0 text-[11px] text-ink-subtle">
                        #{entry.sequence}
                      </span>
                      <Badge tone="accent" className="mono">
                        {entry.action}
                      </Badge>
                      <span className="text-[12px] text-ink">{entry.actor_label}</span>
                      <Badge tone="outline">{entry.actor_type}</Badge>
                      {entry.resource_type ? (
                        <span className="mono text-[11px] text-ink-subtle">
                          {entry.resource_type} {fmt.shortId(entry.resource_id)}
                        </span>
                      ) : null}
                      <Tooltip content={"entry " + entry.entry_hash}>
                        <span className="mono inline-flex items-center gap-1 text-[10px] text-ink-subtle">
                          <Link2 className="size-3" />
                          {entry.prev_hash.slice(0, 8)} -{">"} {entry.entry_hash.slice(0, 8)}
                        </span>
                      </Tooltip>
                      <span className="ml-auto text-[11px] text-ink-subtle">
                        {fmt.datetime(entry.created_at)}
                      </span>
                    </div>
                    {entry.before || entry.after ? (
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {entry.before ? (
                          <Diff label="before" value={entry.before} tone="danger" />
                        ) : null}
                        {entry.after ? (
                          <Diff label="after" value={entry.after} tone="warm" />
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>

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
            <CardBody>
              <EmptyState
                icon={Shield}
                title="No audit entries"
                description="Privileged actions - creating keys, rotating credentials, changing budgets, executing runs - are recorded here as they happen. Nothing has been recorded for this organization yet."
              />
            </CardBody>
          )}
        </Card>
      </motion.div>
    </motion.div>
  );
}

function Diff({
  label,
  value,
  tone,
}: {
  label: string;
  value: Record<string, unknown>;
  tone: "danger" | "warm";
}) {
  return (
    <div
      className={
        "rounded-[var(--radius-sm)] border px-2.5 py-2 " +
        (tone === "warm"
          ? "border-warm/25 bg-warm-ghost/20"
          : "border-danger/20 bg-danger-ghost/20")
      }
    >
      <p className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">{label}</p>
      <pre className="mono mt-1 whitespace-pre-wrap break-all text-[11px] leading-relaxed text-ink-muted">
        {JSON.stringify(value, null, 1).slice(0, 400)}
      </pre>
    </div>
  );
}
