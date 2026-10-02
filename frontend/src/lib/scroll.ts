/**
 * Scrolling the page, through whichever engine is active.
 *
 * Lenis on the marketing pages, native everywhere else. Call these rather than
 * `scrollTo` directly: a raw `window.scrollTo` while Lenis is running fights
 * the engine and lands somewhere between the two positions.
 */

import type Lenis from "lenis";

import { motionAllowed } from "@/hooks/useReducedMotion";

let engine: Lenis | null = null;

export function setLenis(next: Lenis | null): void {
  engine = next;
}

/** Height of the sticky marketing header, plus air. Anchor targets clear it. */
export const HEADER_OFFSET = 88;

export function scrollToElement(el: Element, { offset = HEADER_OFFSET, immediate = false } = {}): void {
  if (engine) {
    // Lenis caches the document limit; content loaded since the last resize
    // would otherwise clamp the target short.
    engine.resize();
    engine.scrollTo(el as HTMLElement, { offset: -offset, immediate, duration: 1.1 });
    return;
  }
  window.scrollTo({
    top: el.getBoundingClientRect().top + window.scrollY - offset,
    behavior: !immediate && motionAllowed() ? "smooth" : "auto",
  });
}

export function scrollToTop(immediate = true): void {
  if (engine) engine.scrollTo(0, { immediate });
  else window.scrollTo({ top: 0, behavior: immediate ? "auto" : "smooth" });
}

/** Smooth-scroll to `#id` and move focus there, without a second jump. */
export function scrollToAnchor(hash: string): void {
  const id = decodeURIComponent(hash.replace(/^#/, ""));
  if (!id) return;
  const el = document.getElementById(id);
  if (!el) return;
  scrollToElement(el);
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: true });
}
