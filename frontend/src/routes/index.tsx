/** Application routing (section 68). Application routes are protected. */

import * as React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui";
import {
  ForgotPasswordPage,
  LoginPage,
  RegisterPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "@/pages/AuthPages";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { AuditPage } from "@/pages/AuditPage";
import { BenchmarksPage } from "@/pages/BenchmarksPage";
import { BudgetsPage } from "@/pages/BudgetsPage";
import { CachePage } from "@/pages/CachePage";
import { CatalogPage } from "@/pages/CatalogPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PlanInspectorPage } from "@/pages/PlanInspectorPage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { RunsPage } from "@/pages/RunsPage";
import { SearchPage } from "@/pages/SearchPage";
import { SettingsRoutes } from "@/pages/SettingsPage";
import { useSession } from "@/stores/session";

function Protected({ children }: { children: React.ReactNode }) {
  const status = useSession((state) => state.status);
  const location = useLocation();

  if (status === "idle" || status === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-ground p-8">
        <div className="w-full max-w-sm space-y-3">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    );
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route
        path="/app"
        element={
          <Protected>
            <AppShell />
          </Protected>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="plans" element={<PlanInspectorPage />} />
        <Route path="plans/:planId" element={<PlanInspectorPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="cache" element={<CachePage />} />
        <Route path="budgets" element={<BudgetsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="benchmarks" element={<BenchmarksPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="settings/*" element={<SettingsRoutes />} />
      </Route>

      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
