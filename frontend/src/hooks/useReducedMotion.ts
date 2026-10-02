/**
 * Reduced motion, from two sources.
 *
 * The OS setting is the one that matters; the in-app preference exists because
 * somebody may want the product's scroll stories off without turning motion off
 * everywhere else on their machine. Either one wins.
 */

import * as React from "react";

import { useUiPrefs } from "@/stores/ui-prefs";

const QUERY = "(prefers-reduced-motion: reduce)";

/** Imperative check, for code outside React: GSAP builders, Lenis setup. */
export function motionAllowed(): boolean {
  if (typeof window === "undefined") return false;
  if (useUiPrefs.getState().reduceMotion) return false;
  return !window.matchMedia(QUERY).matches;
}

export function useReducedMotion(): boolean {
  const preference = useUiPrefs((s) => s.reduceMotion);
  const [system, setSystem] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches,
  );

  React.useEffect(() => {
    const query = window.matchMedia(QUERY);
    const onChange = () => setSystem(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return system || preference;
}

/** The inverse, which reads better at most call sites. */
export function useMotionAllowed(): boolean {
  return !useReducedMotion();
}
