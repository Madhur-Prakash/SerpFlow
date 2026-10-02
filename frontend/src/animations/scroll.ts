/**
 * The scroll motion layer: GSAP, loaded on demand.
 *
 * The console does not need any of this, so none of it is in the main bundle.
 * The marketing pages import these hooks, Vite splits them out, and a signed-in
 * user who never visits the landing page never downloads ScrollTrigger or
 * SplitText.
 *
 * Every hook here is a no-op under reduced motion, and leaves the element in
 * its finished state rather than its starting one - an animation that never
 * runs must not leave content invisible.
 */

import * as React from "react";
import type { gsap as GsapStatic } from "gsap";
import type { ScrollTrigger as ScrollTriggerStatic } from "gsap/ScrollTrigger";
import type { SplitText as SplitTextStatic } from "gsap/SplitText";

import { motionAllowed } from "@/hooks/useReducedMotion";

export type ScrollTools = {
  gsap: typeof GsapStatic;
  ScrollTrigger: typeof ScrollTriggerStatic;
  SplitText: typeof SplitTextStatic;
};

let pending: Promise<ScrollTools> | null = null;

/** GSAP with ScrollTrigger, SplitText and DrawSVG. Loaded once, shared. */
export function loadScrollTools(): Promise<ScrollTools> {
  pending ??= Promise.all([
    import("gsap"),
    import("gsap/ScrollTrigger"),
    import("gsap/SplitText"),
    import("gsap/DrawSVGPlugin"),
  ]).then(([{ gsap }, { ScrollTrigger }, { SplitText }, { DrawSVGPlugin }]) => {
    gsap.registerPlugin(ScrollTrigger, SplitText, DrawSVGPlugin);
    // Mobile browsers fire resize when the address bar collapses, which would
    // otherwise re-measure every trigger mid-scroll and make pinned sections
    // jump.
    ScrollTrigger.config({ ignoreMobileResize: true });
    return { gsap, ScrollTrigger, SplitText };
  });
  return pending;
}

export const EASE_OUT = "power3.out";
export const EASE_IN_OUT = "power2.inOut";
export const EASE_BACK = "back.out(1.6)";

/**
 * Run a GSAP setup inside a context scoped to `ref`, and revert it on unmount.
 *
 * `gsap.context` is what makes this safe under React strict mode and route
 * changes: every tween and trigger created inside it is reverted together, so
 * a remount cannot leave an orphaned ScrollTrigger measuring a detached node.
 */
export function useGsap(
  ref: React.RefObject<HTMLElement | null>,
  setup: (tools: ScrollTools, root: HTMLElement) => void | (() => void),
  deps: React.DependencyList = [],
  enabled = true,
): void {
  React.useEffect(() => {
    const root = ref.current;
    if (!enabled || !root || !motionAllowed()) return;

    let alive = true;
    let revert: (() => void) | undefined;

    void loadScrollTools().then((tools) => {
      if (!alive) return;
      const ctx = tools.gsap.context(() => setup(tools, root), root);
      revert = () => ctx.revert();
    });

    return () => {
      alive = false;
      revert?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, enabled, ...deps]);
}

/**
 * Fade and lift children into view as the section crosses the fold.
 *
 * `selector` runs against the ref's subtree. Children animate in document
 * order with a stagger, which reads as the section assembling itself rather
 * than as a dozen independent fades.
 */
export function useReveal(
  ref: React.RefObject<HTMLElement | null>,
  options: {
    selector?: string;
    y?: number;
    stagger?: number;
    duration?: number;
    start?: string;
    once?: boolean;
  } = {},
): void {
  const {
    selector = "[data-reveal]",
    y = 26,
    stagger = 0.075,
    duration = 0.8,
    start = "top 82%",
    once = true,
  } = options;

  useGsap(ref, ({ gsap, ScrollTrigger }, root) => {
    const targets = gsap.utils.toArray<HTMLElement>(selector, root);
    if (!targets.length) return;

    gsap.set(targets, { opacity: 0, y, willChange: "transform, opacity" });
    const tween = gsap.to(targets, {
      opacity: 1,
      y: 0,
      duration,
      stagger,
      ease: EASE_OUT,
      clearProps: "willChange",
      scrollTrigger: { trigger: root, start, once, toggleActions: "play none none none" },
    });

    return () => {
      tween.kill();
      ScrollTrigger.getAll()
        .filter((t) => t.trigger === root)
        .forEach((t) => t.kill());
    };
  });
}

/**
 * Split a heading into words and reveal them with a clip, line by line.
 *
 * Words rather than characters: a character stagger on a long heading reads as
 * a typewriter gimmick, and screen readers get a string of isolated letters.
 * SplitText restores the original markup when reverted.
 */
export function useTextReveal(
  ref: React.RefObject<HTMLElement | null>,
  options: { selector?: string; start?: string; stagger?: number; delay?: number } = {},
): void {
  const { selector = "[data-split]", start = "top 85%", stagger = 0.045, delay = 0 } = options;

  useGsap(ref, ({ gsap, SplitText }, root) => {
    const targets = gsap.utils.toArray<HTMLElement>(selector, root);
    if (!targets.length) return;

    // Each line gets a wrapper with overflow hidden, so the words rise out of
    // a mask instead of simply fading - that is what makes it read as type
    // setting itself rather than a fade.
    const splits = targets.map(
      (el) => new SplitText(el, { type: "lines,words", linesClass: "split-line" }),
    );

    const words = splits.flatMap((s) => s.words);
    gsap.set(words, { yPercent: 115, opacity: 0 });
    const tween = gsap.to(words, {
      yPercent: 0,
      opacity: 1,
      duration: 0.9,
      ease: EASE_OUT,
      stagger,
      delay,
      scrollTrigger: { trigger: root, start, once: true },
    });

    return () => {
      tween.kill();
      // revert() puts the original markup back, which matters for selection
      // and for anything that queried the heading's text.
      splits.forEach((s) => s.revert());
    };
  });
}

/** Move an element against the scroll, slowly. Depth, not decoration. */
export function useParallax(
  ref: React.RefObject<HTMLElement | null>,
  options: { selector?: string; distance?: number } = {},
): void {
  const { selector = "[data-parallax]", distance = 90 } = options;

  useGsap(ref, ({ gsap }, root) => {
    const targets = gsap.utils.toArray<HTMLElement>(selector, root);
    if (!targets.length) return;

    targets.forEach((el) => {
      const depth = Number(el.dataset.parallax || 1);
      gsap.fromTo(
        el,
        { y: distance * depth * 0.5 },
        {
          y: -distance * depth * 0.5,
          ease: "none",
          scrollTrigger: { trigger: root, start: "top bottom", end: "bottom top", scrub: 0.8 },
        },
      );
    });
  });
}

/**
 * Count a number up when it scrolls into view.
 *
 * Reads the target from `data-count` so the markup stays the source of truth
 * and the final value is in the DOM for anyone who never sees the animation.
 */
export function useCounters(
  ref: React.RefObject<HTMLElement | null>,
  selector = "[data-count]",
): void {
  useGsap(ref, ({ gsap }, root) => {
    const targets = gsap.utils.toArray<HTMLElement>(selector, root);
    targets.forEach((el) => {
      const to = Number(el.dataset.count || 0);
      const decimals = Number(el.dataset.countDecimals || 0);
      const suffix = el.dataset.countSuffix || "";
      const state = { value: 0 };
      gsap.to(state, {
        value: to,
        duration: 1.6,
        ease: "power2.out",
        scrollTrigger: { trigger: el, start: "top 88%", once: true },
        onUpdate: () => {
          el.textContent =
            state.value.toLocaleString(undefined, {
              minimumFractionDigits: decimals,
              maximumFractionDigits: decimals,
            }) + suffix;
        },
      });
    });
  });
}

/**
 * Pull an element gently toward the pointer, and let it go on leave.
 *
 * Returns props to spread. The effect is deliberately small - 0.22 of the
 * distance - because a control that chases the cursor is harder to click, not
 * easier.
 */
export function useMagnetic<T extends HTMLElement>(strength = 0.22) {
  const ref = React.useRef<T>(null);
  const frame = React.useRef(0);

  React.useEffect(() => {
    const el = ref.current;
    if (!el || !motionAllowed()) return;

    let gsapRef: typeof GsapStatic | null = null;
    void loadScrollTools().then(({ gsap }) => {
      gsapRef = gsap;
    });

    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const x = (event.clientX - (rect.left + rect.width / 2)) * strength;
        const y = (event.clientY - (rect.top + rect.height / 2)) * strength;
        gsapRef?.to(el, { x, y, duration: 0.5, ease: EASE_OUT });
      });
    };
    const onLeave = () => {
      cancelAnimationFrame(frame.current);
      gsapRef?.to(el, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.4)" });
    };

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame.current);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [strength]);

  return ref;
}

/**
 * Pin a section and scrub a timeline across it.
 *
 * `build` returns the timeline; the section stays fixed while the page scrolls
 * `distance` screens' worth, then releases. Scrolling back plays it in reverse,
 * which is the property that makes a scroll story feel like a control rather
 * than a video.
 */
export function usePinnedStory(
  ref: React.RefObject<HTMLElement | null>,
  build: (tools: ScrollTools, root: HTMLElement) => gsap.core.Timeline,
  options: { distance?: number; onProgress?: (p: number) => void; enabled?: boolean } = {},
): void {
  const { distance = 2.2, onProgress, enabled = true } = options;

  useGsap(
    ref,
    (tools, root) => {
      const { ScrollTrigger } = tools;
      const timeline = build(tools, root);
      const trigger = ScrollTrigger.create({
        trigger: root,
        start: "top top",
        end: () => `+=${window.innerHeight * distance}`,
        pin: true,
        anticipatePin: 1,
        scrub: 0.7,
        animation: timeline,
        invalidateOnRefresh: true,
        onUpdate: (self) => onProgress?.(self.progress),
      });
      return () => {
        trigger.kill();
        timeline.kill();
      };
    },
    [distance],
    enabled,
  );
}

/** Scale and fade a section's backdrop as it enters, for depth between bands. */
export function useBackdropDrift(
  ref: React.RefObject<HTMLElement | null>,
  selector = "[data-backdrop]",
): void {
  useGsap(ref, ({ gsap }, root) => {
    const targets = gsap.utils.toArray<HTMLElement>(selector, root);
    if (!targets.length) return;
    gsap.fromTo(
      targets,
      { scale: 1.08, opacity: 0.35 },
      {
        scale: 1,
        opacity: 1,
        ease: "none",
        scrollTrigger: { trigger: root, start: "top bottom", end: "top 40%", scrub: 1 },
      },
    );
  });
}
