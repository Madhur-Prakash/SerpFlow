/**
 * A vertical section rail, pinned to the right edge of the landing page.
 *
 * Replaces the hairline progress bar that used to sit across the top. That bar
 * told you how far down the page you were and nothing else; this says which
 * section you are in, how far through the page that is, and lets you jump -
 * which is the part a reader actually wants on a page this long.
 *
 * Three things animate on scroll: the fill climbing the track, the active tick
 * widening, and its label sliding out. None of them is React state - the fill
 * is a CSS custom property written from rAF, so sixty frames a second of
 * scrolling does not re-render the tree.
 */

import * as React from "react";

import { useIsDesktop } from "@/hooks/useMediaQuery";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { scrollToElement } from "@/lib/scroll";
import { cn } from "@/lib/utils";

export type RailSection = { id: string; label: string };

export function SectionRail({ sections }: { sections: RailSection[] }) {
  const fillRef = React.useRef<HTMLSpanElement>(null);
  const [active, setActive] = React.useState<string>(sections[0]?.id ?? "");
  const [visible, setVisible] = React.useState(false);

  const desktop = useIsDesktop();
  const reduced = useReducedMotion();

  // Progress of the whole document, written straight to a custom property.
  React.useEffect(() => {
    if (!desktop) return;
    let frame = 0;

    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const progress = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      fillRef.current?.style.setProperty("--rail-progress", String(progress));
      // The rail is noise over the hero; it earns its place once there is a
      // page behind you.
      setVisible(window.scrollY > window.innerHeight * 0.55);
    };

    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [desktop]);

  // Which section owns the top of the viewport.
  React.useEffect(() => {
    if (!desktop) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const onScreen = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (onScreen[0]) setActive(onScreen[0].target.id);
      },
      // The detection line sits just under the header, so a section becomes
      // active as it reaches the top rather than when it first peeks in.
      { rootMargin: "-20% 0px -62% 0px", threshold: 0 },
    );

    const nodes = sections
      .map((section) => document.getElementById(section.id))
      .filter((node): node is HTMLElement => node !== null);
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [desktop, sections]);

  if (!desktop) return null;

  return (
    <nav
      aria-label="Sections"
      className={cn(
        "fixed right-5 top-1/2 z-40 hidden -translate-y-1/2 lg:block xl:right-8",
        "transition-[opacity,transform] duration-500 ease-out-quint",
        visible
          ? "pointer-events-auto translate-x-0 opacity-100"
          : "pointer-events-none translate-x-3 opacity-0",
        reduced && "transition-none",
      )}
    >
      <div className="relative flex flex-col items-end gap-3.5 pl-2">
        {/* The track and its fill, behind the ticks. */}
        <span
          aria-hidden
          className="absolute right-[3px] top-1 bottom-1 w-px overflow-hidden rounded-full bg-line"
        >
          <span
            ref={fillRef}
            // scaleY rather than height: a transform does not trigger layout,
            // which is what keeps this free during a scroll.
            style={
              {
                "--rail-progress": "0",
                height: "100%",
                transform: "scaleY(var(--rail-progress))",
                transformOrigin: "top",
              } as React.CSSProperties
            }
            className="block w-full rounded-full bg-accent"
          />
        </span>

        {sections.map((section) => {
          const isActive = active === section.id;
          return (
            <button
              key={section.id}
              type="button"
              aria-current={isActive ? "true" : undefined}
              onClick={() => {
                const el = document.getElementById(section.id);
                if (el) scrollToElement(el);
              }}
              className="group relative flex items-center justify-end gap-2.5"
            >
              {/* The label rides out on hover, or whenever its tick is active. */}
              <span
                className={cn(
                  "mono whitespace-nowrap rounded-md border border-line bg-surface/90 px-2 py-1 text-[10.5px] uppercase tracking-[0.12em] backdrop-blur",
                  "transition-[opacity,transform] duration-400 ease-out-quint",
                  isActive
                    ? "text-accent-strong opacity-100"
                    : "text-ink-muted opacity-0 group-hover:opacity-100",
                  isActive ? "translate-x-0" : "translate-x-2 group-hover:translate-x-0",
                )}
              >
                {section.label}
              </span>

              <span
                className={cn(
                  "block h-px rounded-full transition-[width,background-color] duration-400 ease-out-quint",
                  isActive
                    ? "w-[18px] bg-accent"
                    : "w-[9px] bg-line-strong group-hover:w-[14px] group-hover:bg-ink-subtle",
                )}
              />
            </button>
          );
        })}
      </div>
    </nav>
  );
}
