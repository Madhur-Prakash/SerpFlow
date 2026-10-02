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
 * Rise `[data-card]` children into place when the page mounts.
 *
 * On mount, deliberately - not on scroll. The console scrolls inside its own
 * container rather than the window, and ScrollTrigger watches the window by
 * default: cards below the fold never triggered, so they stayed at opacity 0
 * and the page looked like it would not scroll to the bottom. Tying the
 * trigger to the inner scroller would work, but a bounded page with a dozen
 * cards does not need scroll choreography - it needs to appear.
 *
 * The stagger is capped, so a long page does not make the last card wait.
 * Under reduced motion nothing is touched at all.
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

    void loadScrollTools().then(({ gsap }) => {
      if (!alive) return;
      const ctx = gsap.context(() => {
        const targets = gsap.utils.toArray<HTMLElement>(selector, root);
        if (!targets.length) return;

        gsap.fromTo(
          targets,
          { opacity: 0, y },
          {
            opacity: 1,
            y: 0,
            duration: 0.4,
            ease: "power2.out",
            // Capped: the twentieth card should not wait most of a second.
            stagger: { each: stagger, amount: Math.min(targets.length * stagger, 0.36) },
            // Cleared so a later layout change cannot inherit a stale transform.
            clearProps: "opacity,transform",
          },
        );
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
