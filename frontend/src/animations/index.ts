/**
 * Animation setup (section 5).
 *
 * Framer Motion for interface transitions, GSAP for the plan and catalog
 * graphs. Both respect prefers-reduced-motion: the Framer variants collapse to
 * instant, and the GSAP helpers below set the end state directly instead of
 * tweening to it. Smooth scrolling is public-pages only; see useSmoothScroll.
 */

import { gsap } from "gsap";
import type { Transition, Variants } from "framer-motion";

export const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// --------------------------------------------------------- Framer Motion
export const easeOutQuint = [0.22, 1, 0.36, 1] as const;
export const easeInOutQuart = [0.76, 0, 0.24, 1] as const;

export const transition = (duration = 0.32, delay = 0): Transition =>
  prefersReducedMotion()
    ? { duration: 0 }
    : { duration, delay, ease: easeOutQuint };

export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: transition(0.3) },
  exit: { opacity: 0, y: -6, transition: transition(0.18) },
};

export const listVariants: Variants = {
  animate: { transition: { staggerChildren: prefersReducedMotion() ? 0 : 0.035 } },
};

export const itemVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: transition(0.28) },
};

export const fadeVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: transition(0.22) },
  exit: { opacity: 0, transition: transition(0.14) },
};

export const scaleVariants: Variants = {
  initial: { opacity: 0, scale: 0.97 },
  animate: { opacity: 1, scale: 1, transition: transition(0.24) },
  exit: { opacity: 0, scale: 0.98, transition: transition(0.14) },
};

export const drawerVariants: Variants = {
  initial: { x: "100%" },
  animate: { x: 0, transition: transition(0.34) },
  exit: { x: "100%", transition: transition(0.22) },
};

// ------------------------------------------------------------------ GSAP
/** Count a number up. Used for credit figures on the dashboard. */
export function countUp(
  element: HTMLElement,
  to: number,
  options: { from?: number; duration?: number; format?: (value: number) => string } = {},
): gsap.core.Tween | null {
  const format = options.format ?? ((value: number) => Math.round(value).toLocaleString());
  if (prefersReducedMotion()) {
    element.textContent = format(to);
    return null;
  }
  const state = { value: options.from ?? 0 };
  return gsap.to(state, {
    value: to,
    duration: options.duration ?? 0.9,
    ease: "power2.out",
    onUpdate: () => {
      element.textContent = format(state.value);
    },
  });
}

/** Draw an SVG path from nothing to its full length. */
export function drawPath(
  path: SVGPathElement | SVGLineElement,
  options: { duration?: number; delay?: number } = {},
): gsap.core.Tween | null {
  const length =
    "getTotalLength" in path ? (path as SVGPathElement).getTotalLength() : 0;
  if (!length) return null;
  if (prefersReducedMotion()) {
    gsap.set(path, { strokeDasharray: "none", strokeDashoffset: 0, opacity: 1 });
    return null;
  }
  gsap.set(path, { strokeDasharray: length, strokeDashoffset: length, opacity: 1 });
  return gsap.to(path, {
    strokeDashoffset: 0,
    duration: options.duration ?? 0.6,
    delay: options.delay ?? 0,
    ease: "power2.inOut",
  });
}

/** Reveal graph nodes in dependency order. */
export function revealNodes(
  nodes: Element[],
  options: { stagger?: number; duration?: number } = {},
): gsap.core.Tween | null {
  if (!nodes.length) return null;
  if (prefersReducedMotion()) {
    gsap.set(nodes, { opacity: 1, scale: 1 });
    return null;
  }
  gsap.set(nodes, { opacity: 0, scale: 0.9 });
  return gsap.to(nodes, {
    opacity: 1,
    scale: 1,
    duration: options.duration ?? 0.38,
    stagger: options.stagger ?? 0.07,
    ease: "back.out(1.5)",
  });
}

/** Pulse an element once, to mark a state change worth noticing. */
export function pulse(element: Element | null): gsap.core.Tween | null {
  if (!element || prefersReducedMotion()) return null;
  return gsap.fromTo(
    element,
    { scale: 1 },
    { scale: 1.04, duration: 0.18, yoyo: true, repeat: 1, ease: "power2.inOut" },
  );
}

export { gsap };
