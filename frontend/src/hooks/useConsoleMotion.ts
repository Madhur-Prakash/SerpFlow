/**
 * Scroll motion for the console.
 *
 * Deliberately smaller than the marketing surface's vocabulary. An operator
 * scanning a run table sees these on every navigation, so the budget is a
 * short rise on entry and a count-up on the figures that carry meaning -
 * nothing pinned, nothing scrubbed, nothing that delays reading.
 *
 * GSAP is loaded on demand from the same module the landing page uses, so the
 * console pulls ScrollTrigger only when a page actually asks for it.
 */

import * as React from "react";

import { loadScrollTools } from "@/animations/scroll";
import { motionAllowed } from "@/hooks/useReducedMotion";

/**
 * Rise `[data-card]` children into place as they cross the fold.
 *
 * Elements already on screen animate immediately; the rest wait for the
 * scroll. Under reduced motion nothing is touched, so content is never left
 * at opacity 0 by an animation that did not run.
 */
export function useCardReveal(
  ref: React.RefObject<HTMLElement | null>,
  options: { selector?: string; stagger?: number; y?: number } = {},
): void {
  const { selector = "[data-card]", stagger = 0.045, y = 12 } = options;

  React.useEffect(() => {
    const root = ref.current;
    if (!root || !motionAllowed()) return;

    let revert: (() => void) | undefined;
    let alive = true;

    void loadScrollTools().then(({ gsap, ScrollTrigger }) => {
      if (!alive) return;
      const ctx = gsap.context(() => {
        const targets = gsap.utils.toArray<HTMLElement>(selector, root);
        if (!targets.length) return;

        gsap.set(targets, { opacity: 0, y });

        targets.forEach((el, index) => {
          const above = el.getBoundingClientRect().top < window.innerHeight;
          gsap.to(el, {
            opacity: 1,
            y: 0,
            duration: 0.42,
            ease: "power2.out",
            delay: above ? index * stagger : 0,
            ...(above
              ? {}
              : {
                  scrollTrigger: { trigger: el, start: "top 92%", once: true },
                }),
          });
        });

        // Content above can finish loading after this runs and move everything
        // down; without a refresh the triggers keep their stale positions.
        ScrollTrigger.refresh();
      }, root);
      revert = () => ctx.revert();
    });

    return () => {
      alive = false;
      revert?.();
    };
  }, [ref, selector, stagger, y]);
}

/**
 * Count `[data-figure]` elements up to the number in their `data-figure`.
 *
 * The final value stays in the DOM, so a reader who never sees the animation -
 * reduced motion, a screen reader, a paused tab - reads the right number.
 */
export function useFigureCounters(
  ref: React.RefObject<HTMLElement | null>,
  selector = "[data-figure]",
): void {
  React.useEffect(() => {
    const root = ref.current;
    if (!root || !motionAllowed()) return;

    let revert: (() => void) | undefined;
    let alive = true;

    void loadScrollTools().then(({ gsap }) => {
      if (!alive) return;
      const ctx = gsap.context(() => {
        for (const el of gsap.utils.toArray<HTMLElement>(selector, root)) {
          const to = Number(el.dataset.figure);
          if (!Number.isFinite(to)) continue;
          const decimals = Number(el.dataset.figureDecimals || 0);
          const suffix = el.dataset.figureSuffix || "";
          const state = { value: 0 };

          gsap.to(state, {
            value: to,
            duration: 0.85,
            ease: "power2.out",
            onUpdate: () => {
              el.textContent =
                state.value.toLocaleString(undefined, {
                  minimumFractionDigits: decimals,
                  maximumFractionDigits: decimals,
                }) + suffix;
            },
          });
        }
      }, root);
      revert = () => ctx.revert();
    });

    return () => {
      alive = false;
      revert?.();
    };
  }, [ref, selector]);
}

/** Both, for a page that has cards and figures. Returns the ref to spread. */
export function useConsoleMotion<T extends HTMLElement = HTMLDivElement>() {
  const ref = React.useRef<T>(null);
  useCardReveal(ref);
  useFigureCounters(ref);
  return ref;
}
