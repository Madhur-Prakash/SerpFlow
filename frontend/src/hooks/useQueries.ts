/** React Query bindings. One hook per server resource. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useSession } from "@/stores/session";

const MINUTE = 60_000;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  });
}

export function useDashboard(days = 30) {
  return useQuery({
    queryKey: ["dashboard", days],
    queryFn: () => api.dashboard(days),
    staleTime: MINUTE,
  });
}

export function useSavings(days = 30) {
  return useQuery({
    queryKey: ["savings", days],
    queryFn: () => api.savings(days),
    staleTime: MINUTE,
  });
}

export function useRuns(filters: Parameters<typeof api.runs>[0] = {}) {
  const project = useSession((state) => state.project);
  return useQuery({
    queryKey: ["runs", project?.id, filters],
    queryFn: () => api.runs({ project_id: project?.id, ...filters }),
    staleTime: 15_000,
  });
}

export function useRun(id: string | undefined) {
  return useQuery({
    queryKey: ["run", id],
    queryFn: () => api.run(id as string),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useCatalog(filters: Parameters<typeof api.catalog>[0] = {}) {
  return useQuery({
    queryKey: ["catalog", filters],
    queryFn: () => api.catalog(filters),
    // The catalog is a committed artefact; it only changes on deploy.
    staleTime: 30 * MINUTE,
  });
}

export function useCatalogGraph() {
  return useQuery({
    queryKey: ["catalog-graph"],
    queryFn: () => api.catalogGraph(),
    staleTime: 30 * MINUTE,
  });
}

export function useCatalogTags() {
  return useQuery({
    queryKey: ["catalog-tags"],
    queryFn: () => api.catalogTags(),
    staleTime: 30 * MINUTE,
  });
}

export function useCacheDashboard(days = 30) {
  return useQuery({
    queryKey: ["cache-dashboard", days],
    queryFn: () => api.cacheDashboard(days),
    staleTime: 30_000,
  });
}

export function useCacheEntries(filters: Parameters<typeof api.cacheEntries>[0] = {}) {
  return useQuery({
    queryKey: ["cache-entries", filters],
    queryFn: () => api.cacheEntries(filters),
    staleTime: 30_000,
  });
}

export function useGuardRejections(limit = 50) {
  return useQuery({
    queryKey: ["guard-rejections", limit],
    queryFn: () => api.guardRejections({ limit }),
    staleTime: 30_000,
  });
}

export function useBudgets() {
  return useQuery({
    queryKey: ["budgets"],
    queryFn: () => api.budgets(),
    staleTime: 20_000,
  });
}

export function useBenchmarks(catalogVersion?: string) {
  return useQuery({
    queryKey: ["benchmarks", catalogVersion],
    queryFn: () => api.benchmarks(catalogVersion),
    staleTime: 5 * MINUTE,
  });
}

export function useBenchmarkTasks(filters: Parameters<typeof api.benchmarkTasks>[0] = {}) {
  return useQuery({
    queryKey: ["benchmark-tasks", filters],
    queryFn: () => api.benchmarkTasks(filters),
    staleTime: 10 * MINUTE,
  });
}

export function useRoutingQuality() {
  return useQuery({
    queryKey: ["routing-quality"],
    queryFn: () => api.routingQuality(),
    staleTime: 5 * MINUTE,
  });
}

export function useVolatility(days = 90) {
  return useQuery({
    queryKey: ["volatility", days],
    queryFn: () => api.volatility(days),
    staleTime: 5 * MINUTE,
  });
}

export function useEngineReach() {
  return useQuery({
    queryKey: ["engine-reach"],
    queryFn: () => api.engineReach(),
    staleTime: 5 * MINUTE,
  });
}

export function useAudit(filters: Parameters<typeof api.audit>[0] = {}) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: () => api.audit(filters),
    staleTime: 30_000,
  });
}

export function useAuditVerify() {
  return useQuery({
    queryKey: ["audit-verify"],
    queryFn: () => api.verifyAudit(),
    staleTime: MINUTE,
  });
}

export function useAlerts(status = "open") {
  return useQuery({
    queryKey: ["alerts", status],
    queryFn: () => api.alerts({ status }),
    staleTime: 30_000,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api.projects(),
    staleTime: MINUTE,
  });
}

export function useMembers() {
  return useQuery({
    queryKey: ["members"],
    queryFn: () => api.members(),
    staleTime: MINUTE,
  });
}

export function useApiKeys(projectId?: string) {
  return useQuery({
    queryKey: ["keys", projectId],
    queryFn: () => api.keys({ project_id: projectId, limit: 100 }),
    staleTime: 30_000,
  });
}

export function useCredentials() {
  return useQuery({
    queryKey: ["credentials"],
    queryFn: () => api.credentials(),
    staleTime: 30_000,
  });
}

/** Which keys this organization must bring, and whether it has brought them. */
export function useCredentialProviders() {
  return useQuery({
    queryKey: ["credential-providers"],
    queryFn: () => api.credentialProviders(),
    staleTime: 30_000,
  });
}

export function useSessions() {
  return useQuery({
    queryKey: ["auth-sessions"],
    queryFn: () => api.sessions(),
    staleTime: 30_000,
  });
}

export function useCrossProject() {
  return useQuery({
    queryKey: ["cross-project"],
    queryFn: () => api.crossProject(),
    staleTime: MINUTE,
  });
}

/** Invalidate everything a run touches, after an execution or a replay. */
export function useInvalidateRunData() {
  const client = useQueryClient();
  return () => {
    for (const key of [
      "runs",
      "dashboard",
      "savings",
      "cache-dashboard",
      "cache-entries",
      "budgets",
      "guard-rejections",
      "cross-project",
      "audit",
      "alerts",
    ]) {
      client.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useReplayRun() {
  const invalidate = useInvalidateRunData();
  return useMutation({
    mutationFn: (runId: string) => api.replay(runId),
    onSuccess: invalidate,
  });
}

export function useReportFalseHit() {
  const invalidate = useInvalidateRunData();
  return useMutation({
    mutationFn: (input: {
      runId: string;
      stepId?: string | null;
      note: string;
      invalidate?: boolean;
    }) =>
      api.reportFalseHit(input.runId, {
        step_id: input.stepId,
        note: input.note,
        invalidate_entry: input.invalidate ?? true,
      }),
    onSuccess: invalidate,
  });
}

export function useInvalidateCache() {
  const invalidate = useInvalidateRunData();
  return useMutation({
    mutationFn: (input: { engine?: string | null; entry_id?: string | null }) =>
      api.invalidateCache(input),
    onSuccess: invalidate,
  });
}
