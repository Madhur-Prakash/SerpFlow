/**
 * The theme control.
 *
 * Three states, not two. "System" is the default and the one most people
 * actually want, so it has to be reachable - a plain dark/light switch strands
 * anyone whose machine changes at sunset.
 *
 * The trigger is an unlabelled icon, so it carries a tooltip that names the
 * control *and* reports the current setting. An icon button whose tooltip only
 * repeats its own name tells you nothing you could not already see.
 */

import { Check, Monitor, MoonStar, Sun } from "lucide-react";
import * as React from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
} from "@/components/ui";
import { originOf, switchTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useUiPrefs, type Theme } from "@/stores/ui-prefs";

type Option = {
  value: Theme;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
};

const OPTIONS: Option[] = [
  { value: "light", label: "Light", hint: "Always light", icon: Sun },
  { value: "dark", label: "Dark", hint: "Always dark", icon: MoonStar },
  { value: "system", label: "System", hint: "Follows your device", icon: Monitor },
];

export function ThemeToggle({ className }: { className?: string }) {
  const theme = useUiPrefs((s) => s.theme);
  const resolved = useUiPrefs((s) => s.resolved);
  const [open, setOpen] = React.useState(false);

  const Icon = theme === "system" ? Monitor : resolved === "dark" ? MoonStar : Sun;

  // "System (currently dark)" rather than just "System": when the setting
  // follows the device, the setting alone does not tell you what you are
  // looking at.
  const summary =
    theme === "system"
      ? `System, currently ${resolved}`
      : theme === "dark"
        ? "Dark"
        : "Light";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Tooltip
        // Suppressed rather than emptied while the menu is open: an empty
        // tooltip would unwrap the trigger, and the open menu would lose the
        // element it is anchored to.
        suppressed={open}
        content={
          <span className="flex flex-col gap-0.5">
            <span className="font-medium text-ink">Appearance</span>
            <span className="text-ink-muted">{summary}</span>
          </span>
        }
      >
        <DropdownMenuTrigger
          aria-label={`Appearance: ${summary}. Change the theme.`}
          className={cn(
            "group relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface/70 text-ink-muted backdrop-blur",
            "transition-[color,border-color,background-color,transform] duration-300 ease-out-quint",
            "hover:-translate-y-px hover:border-line-strong hover:text-ink",
            "data-[state=open]:border-line-strong data-[state=open]:text-ink",
            className,
          )}
        >
          {/* The icon turns on hover, so the control reads as the same object
              rotating rather than two icons swapping. */}
          <Icon className="h-[17px] w-[17px] transition-transform duration-500 ease-out-quint group-hover:rotate-[22deg]" />
        </DropdownMenuTrigger>
      </Tooltip>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {OPTIONS.map((option) => {
          const OptionIcon = option.icon;
          const active = theme === option.value;
          return (
            <DropdownMenuItem
              key={option.value}
              onSelect={(event) => {
                // The reveal grows from the trigger, not from the menu item,
                // which has already started unmounting by the time this runs.
                const trigger = (event.currentTarget as HTMLElement)
                  .closest("[data-radix-popper-content-wrapper]")
                  ?.previousElementSibling;
                switchTheme(option.value, originOf(trigger ?? null));
              }}
              className="items-start gap-2.5 py-2"
            >
              <OptionIcon
                className={cn("mt-px shrink-0", active && "!text-accent-strong")}
              />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className={cn("leading-none", active && "text-accent-strong")}>
                  {option.label}
                </span>
                <span className="text-[11.5px] leading-none text-ink-subtle">
                  {option.value === "system" ? `${option.hint}, now ${resolved}` : option.hint}
                </span>
              </span>
              {/* A check, not a dot: it says "this is the one in use" without
                  needing a legend. */}
              {active ? (
                <Check className="mt-px shrink-0 !text-accent-strong" aria-hidden />
              ) : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
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
