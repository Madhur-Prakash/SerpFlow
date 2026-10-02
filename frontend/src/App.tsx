import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui";
import { AppRoutes } from "@/routes";
import { useSession } from "@/stores/session";
import { applyTheme, useUiPrefs, watchSystemTheme } from "@/stores/ui-prefs";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Never retry an authorization or validation failure: the answer will
        // not change, and retrying just delays a clear error message.
        const status = (error as { status?: number })?.status ?? 0;
        if (status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  const load = useSession((state) => state.load);

  React.useEffect(() => {
    void load();
  }, [load]);

  // The theme is applied once here and then kept in step with the OS while it
  // is set to "system". The inline script in index.html has already put the
  // stored value on <html>, so this never causes a flash.
  React.useEffect(() => {
    applyTheme(useUiPrefs.getState().theme);
    return watchSystemTheme();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider delayDuration={200} skipDelayDuration={400}>
          <AppRoutes />
          <Toaster
            position="bottom-right"
            toastOptions={{
              className:
                "!bg-[var(--color-surface-raised)] !border !border-[var(--color-line)] !text-[var(--color-ink)] !text-[13px] !rounded-[var(--radius-md)]",
            }}
          />
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
