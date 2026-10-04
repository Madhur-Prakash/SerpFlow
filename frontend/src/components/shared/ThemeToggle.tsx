/**
 * The theme control.
 *
 * Three states, not two. "System" is the default and the one most people
 * actually want, so it has to be reachable - a plain dark/light switch strands
 * anyone whose machine changes at sunset.
 *
 * One button that cycles, rather than a menu. Choosing a theme is a trivial,
 * instantly reversible decision with three options, and a menu made it a
 * two-step one: open, read, aim, click. Cycling costs a click and shows the
 * result immediately, which is its own confirmation.
 *
 * The cost of cycling is that the next state is not visible before you commit,
 * so the tooltip and the accessible name both name it: what this is set to
 * now, and what the next press will do.
 */

import { Monitor, MoonStar, Sun } from "lucide-react";

import { Tooltip } from "@/components/ui";
import { originOf, switchTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useUiPrefs, type Theme } from "@/stores/ui-prefs";

/** Light, then dark, then system, then round again. */
const CYCLE: Theme[] = ["light", "dark", "system"];

const LABEL: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

/** The icon names the setting, not the resolved value: a monitor for system
 *  says "this follows your device", which a sun or a moon cannot. */
const ICON = { light: Sun, dark: MoonStar, system: Monitor } as const;

export function ThemeToggle({ className }: { className?: string }) {
  const theme = useUiPrefs((s) => s.theme);
  const resolved = useUiPrefs((s) => s.resolved);

  const next = CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length];
  const Icon = ICON[theme];

  // "System (currently dark)" rather than just "System": when the setting
  // follows the device, the setting alone does not tell you what you are
  // looking at.
  const summary = theme === "system" ? `System, currently ${resolved}` : LABEL[theme];

  return (
    <Tooltip
      content={
        <span className="flex flex-col gap-0.5">
          <span className="font-medium text-ink">Appearance</span>
          <span className="text-ink-muted">{summary}</span>
          <span className="text-ink-subtle">Click for {LABEL[next].toLowerCase()}</span>
        </span>
      }
    >
      <button
        type="button"
        aria-label={`Appearance: ${summary}. Switch to ${LABEL[next].toLowerCase()}.`}
        onClick={(event) => switchTheme(next, originOf(event.currentTarget))}
        className={cn(
          "group relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface/70 text-ink-muted backdrop-blur",
          "transition-[color,border-color,background-color,transform] duration-300 ease-out-quint",
          "hover:-translate-y-px hover:border-line-strong hover:text-ink",
          "active:translate-y-0",
          className,
        )}
      >
        {/* The icon turns on hover, so the control reads as the same object
            rotating rather than three icons swapping. */}
        <Icon className="h-[17px] w-[17px] transition-transform duration-500 ease-out-quint group-hover:rotate-[22deg]" />
      </button>
    </Tooltip>
  );
}

/** A plain two-state switch, for the footer and other tight spots. */
export function ThemeSwitchCompact({ className }: { className?: string }) {
  const resolved = useUiPrefs((s) => s.resolved);
  const next = resolved === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      aria-label={`Switch to the ${next} theme`}
      title={`Switch to the ${next} theme`}
      onClick={(event) => switchTheme(next, originOf(event.currentTarget))}
      className={cn(
        "group inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[12px] text-ink-muted",
        "transition-colors duration-300 hover:border-line-strong hover:text-ink",
        className,
      )}
    >
      {resolved === "dark" ? (
        <Sun className="h-3.5 w-3.5 transition-transform duration-500 ease-out-quint group-hover:rotate-90" />
      ) : (
        <MoonStar className="h-3.5 w-3.5 transition-transform duration-500 ease-out-quint group-hover:-rotate-12" />
      )}
      <span className="capitalize">{next}</span>
    </button>
  );
}
