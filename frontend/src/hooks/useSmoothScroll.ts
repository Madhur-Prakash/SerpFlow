/**
 * Lenis smooth wheel scrolling, on the public pages only.
 *
 * It drives the native window scroll rather than a transformed container, so
 * `position: sticky`, GSAP's ScrollTrigger pinning, the browser's own find-in-page
 * and the real scrollbar all keep working. The signed-in console keeps plain
 * native scrolling: an operator scanning a run table wants the scroll position
 * their pointer asked for, not an eased approximation of it.
 */

import Lenis from "lenis";
import * as React from "react";

import { motionAllowed } from "@/hooks/useReducedMotion";
import { setLenis } from "@/lib/scroll";

/** Anything that scrolls on its own: the wheel over it must not move the page. */
const OWN_SCROLL = [
  '[role="dialog"]',
  '[role="listbox"]',
  '[role="menu"]',
  "[data-radix-popper-content-wrapper]",
  "[data-lenis-prevent]",
  "[cmdk-list]",
  "pre",
].join(", ");

export function useSmoothScroll(enabled = true): void {
  React.useEffect(() => {
    if (!enabled || !motionAllowed()) return;

    const lenis = new Lenis({
      autoRaf: true,
      lerp: 0.12,
      smoothWheel: true,
      allowNestedScroll: true,
      prevent: (node) => !!node.closest?.(OWN_SCROLL),
    });

    // Radix sets data-scroll-locked on <body> while a dialog owns scrolling.
    // Without this, Lenis keeps driving the page behind the open dialog.
    const syncLock = () =>
      document.body.hasAttribute("data-scroll-locked") ? lenis.stop() : lenis.start();
    const observer = new MutationObserver(syncLock);
    observer.observe(document.body, { attributes: true, attributeFilter: ["data-scroll-locked"] });

    setLenis(lenis);
    return () => {
      observer.disconnect();
      lenis.destroy();
      setLenis(null);
    };
  }, [enabled]);
}
