/**
 * Interface preferences that outlive a session: theme, sidebar state, motion.
 *
 * Theme is tri-state. "system" is the default and follows the OS, which is the
 * only setting that is right for someone who switches at sunset; "dark" and
 * "light" are explicit overrides. The resolved value is what the document
 * carries as a class.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";

const STORAGE_KEY = "serpflow.ui";

export function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === "system" ? systemTheme() : theme;
}

/** Put the resolved theme on <html>, which is what the CSS tokens key off. */
export function applyTheme(theme: Theme): ResolvedTheme {
  const resolved = resolveTheme(theme);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  root.dataset.theme = resolved;
  return resolved;
}

type UiPrefs = {
  theme: Theme;
  /** The value actually on the document, so components can read it without re-deriving. */
  resolved: ResolvedTheme;
  sidebarCollapsed: boolean;
  /** Opt out of the landing page's scroll stories without touching the OS setting. */
  reduceMotion: boolean;
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
  setReduceMotion: (value: boolean) => void;
};

export const useUiPrefs = create<UiPrefs>()(
  persist(
    (set) => ({
      theme: "system",
      resolved: typeof window === "undefined" ? "dark" : systemTheme(),
      sidebarCollapsed: false,
      reduceMotion: false,
      setTheme: (theme) => set({ theme, resolved: applyTheme(theme) }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setReduceMotion: (reduceMotion) => set({ reduceMotion }),
    }),
    {
      name: STORAGE_KEY,
      partialize: (s) => ({
        theme: s.theme,
        sidebarCollapsed: s.sidebarCollapsed,
        reduceMotion: s.reduceMotion,
      }),
      onRehydrateStorage: () => (state) => {
        // The inline script in index.html has already applied the stored theme
        // to avoid a flash. This re-applies it from the hydrated store so the
        // two can never disagree.
        if (state) state.resolved = applyTheme(state.theme);
      },
    },
  ),
);

/**
 * Follow the OS while the theme is "system".
 *
 * Returns an unsubscribe. Called once from the app root rather than from a
 * component that might mount twice.
 */
export function watchSystemTheme(): () => void {
  if (typeof window === "undefined") return () => {};
  const query = window.matchMedia("(prefers-color-scheme: light)");
  const onChange = () => {
    const { theme } = useUiPrefs.getState();
    if (theme === "system") useUiPrefs.setState({ resolved: applyTheme("system") });
  };
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
