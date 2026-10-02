/**
 * Switching the theme, with the reveal.
 *
 * The new theme grows as a circle from wherever the control was pressed, using
 * the View Transitions API. Browsers without it get a short colour crossfade,
 * and reduced motion switches instantly - a full-page wipe is exactly the kind
 * of motion somebody turns that setting on to avoid.
 */

import { flushSync } from "react-dom";

import { motionAllowed } from "@/hooks/useReducedMotion";
import { useUiPrefs, type Theme } from "@/stores/ui-prefs";

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => {
    ready: Promise<void>;
    finished: Promise<void>;
  };
};

export function switchTheme(next: Theme, _origin?: { x: number; y: number }): void {
  // flushSync, because the View Transition snapshots the DOM synchronously
  // after this callback: a React render scheduled for later would be captured
  // in the "before" frame and the transition would animate nothing.
  const apply = () => flushSync(() => useUiPrefs.getState().setTheme(next));
  const root = document.documentElement;

  if (!motionAllowed()) {
    apply();
    return;
  }

  const doc = document as ViewTransitionDocument;
  if (!doc.startViewTransition) {
    root.classList.add("theme-fading");
    apply();
    window.setTimeout(() => root.classList.remove("theme-fading"), 420);
    return;
  }

  const transition = doc.startViewTransition(apply);
  transition.ready
    .then(() => {
      // A shutter: the new theme comes down from the top edge and covers the
      // old one. `inset()` from 100% bottom to 0 is the whole effect - the new
      // snapshot is clipped to a band that grows downward, so nothing moves
      // and only the reveal animates.
      root.animate(
        { clipPath: ["inset(0 0 100% 0)", "inset(0 0 0% 0)"] },
        {
          duration: 560,
          easing: "cubic-bezier(0.65, 0, 0.35, 1)",
          pseudoElement: "::view-transition-new(root)",
        },
      );
    })
    .catch(() => {
      // The transition was skipped - the tab was hidden, or another started.
      // The theme is already applied either way.
    });
}

/** The centre of the control that triggered a switch, as the reveal's origin. */
export function originOf(el: Element | null | undefined): { x: number; y: number } | undefined {
  if (!el) return undefined;
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

/** Cycle dark -> light -> system, which is the order a toggle button walks. */
export function nextTheme(current: Theme): Theme {
  if (current === "dark") return "light";
  if (current === "light") return "system";
  return "dark";
}
