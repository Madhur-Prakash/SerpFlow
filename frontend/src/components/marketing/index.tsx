/**
 * The marketing surface's building blocks.
 *
 * Shared vocabulary for the landing page, the docs and the API reference, so
 * the three read as one site rather than three. Everything here degrades to a
 * static layout under reduced motion.
 */

import * as React from "react";
import { Link } from "react-router-dom";

import { useGsap, useMagnetic } from "@/animations/scroll";
import { cn } from "@/lib/utils";

export { SectionRail, type RailSection } from "./SectionRail";

// --------------------------------------------------------------------------
// Atmosphere - the animated ground behind a section
// --------------------------------------------------------------------------

/**
 * Drifting light and a fine grid, behind the content.
 *
 * Driven by GSAP rather than CSS keyframes, so the grid can be tied to scroll
 * position instead of running on a clock of its own - the ground moves because
 * the reader moves, which is the difference between depth and a screensaver.
 *
 * Nothing here has a hue. Earlier versions washed each section in a colour,
 * and because this component sits under every section at once, that read as a
 * tint over the whole site rather than as atmosphere. The light is white on a
 * dark ground and black on a light one, and the only colour on the page comes
 * from the content.
 *
 * Everything runs through `useGsap`, which no-ops under reduced motion and
 * reverts on unmount, so the static layout is the fallback rather than an
 * afterthought.
 */
export function Atmosphere({
  variant = "hero",
  className,
}: {
  variant?: "hero" | "band" | "quiet";
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);

  useGsap(
    ref,
    ({ gsap, ScrollTrigger }, root) => {
      // The grid travels against the scroll. Slow enough to read as parallax
      // depth rather than as a second thing moving on the page.
      const grid = root.querySelector<HTMLElement>("[data-grid]");
      if (grid) {
        gsap.fromTo(
          grid,
          { yPercent: -6 },
          {
            yPercent: 6,
            ease: "none",
            scrollTrigger: {
              trigger: root,
              start: "top bottom",
              end: "bottom top",
              scrub: 0.8,
            },
          },
        );
      }

      // The lights breathe on their own clock, each slightly out of step with
      // the other, so the pair never returns to the same arrangement twice
      // within a reading. Sine easing keeps them from snapping at the turn.
      gsap.utils.toArray<HTMLElement>("[data-glow]", root).forEach((glow, i) => {
        const sign = i % 2 === 0 ? 1 : -1;
        gsap.to(glow, {
          xPercent: sign * 9,
          yPercent: sign * -7,
          scale: 1.14,
          duration: 16 + i * 6,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
          delay: i * 1.4,
        });
      });

      // A ScrollTrigger created inside a pinned ancestor can measure before
      // that ancestor settles, which leaves the grid parked at its start.
      ScrollTrigger.refresh();
    },
    [variant],
  );

  return (
    <div
      ref={ref}
      aria-hidden
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      <div data-grid className="absolute -inset-y-[12%] inset-x-0 grid-field opacity-[0.45]" />

      {variant !== "quiet" && (
        <>
          <div
            data-glow
            className="absolute -top-[22%] left-[8%] h-[46rem] w-[46rem] rounded-full blur-[120px] bg-[radial-gradient(circle,var(--atmosphere-glow)_0%,transparent_68%)] opacity-[calc(var(--atmosphere)*0.16)]"
          />
          <div
            data-glow
            className="absolute -right-[12%] top-[14%] h-[38rem] w-[38rem] rounded-full blur-[130px] bg-[radial-gradient(circle,var(--atmosphere-glow)_0%,transparent_70%)] opacity-[calc(var(--atmosphere)*0.13)]"
          />
        </>
      )}

      {variant === "hero" && (
        <div
          data-glow
          className="absolute bottom-[-30%] left-1/2 h-[34rem] w-[52rem] -translate-x-1/2 rounded-full blur-[140px] bg-[radial-gradient(circle,var(--atmosphere-glow)_0%,transparent_72%)] opacity-[calc(var(--atmosphere)*0.1)]"
        />
      )}

      {/* A top-down fade so the band below always starts clean. */}
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-[var(--color-ground)]" />
    </div>
  );
}

// --------------------------------------------------------------------------
// Typographic furniture
// --------------------------------------------------------------------------

/** A small monospace label above a heading. Reads as a section marker. */
export function MonoLabel({
  children,
  className,
  tone = "accent",
}: {
  children: React.ReactNode;
  className?: string;
  tone?: "accent" | "warm" | "muted";
}) {
  const tones = {
    accent: "text-accent-strong border-accent-muted/50 bg-accent-ghost/40",
    warm: "text-warm border-warm/30 bg-warm-ghost/40",
    muted: "text-ink-subtle border-line bg-surface",
  } as const;
  return (
    <span
      className={cn(
        "mono inline-flex w-fit shrink-0 items-center gap-2 self-start rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.16em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function SectionHeading({
  label,
  title,
  lede,
  align = "left",
  className,
  tone,
  aside,
}: {
  label?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  align?: "left" | "center";
  className?: string;
  tone?: "accent" | "warm" | "muted";
  /**
   * Content for the right of the heading row.
   *
   * A heading capped at 3xl on a 1280px page leaves half the row empty. Where
   * a section has something worth putting there - a figure, a definition, a
   * fragment of the thing being described - it goes here rather than being
   * stacked underneath.
   */
  aside?: React.ReactNode;
}) {
  const heading = (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-4",
        align === "center" ? "mx-auto max-w-3xl items-center text-center" : "max-w-2xl",
        !aside && className,
      )}
    >
      {label ? (
        <div data-reveal>
          <MonoLabel tone={tone}>{label}</MonoLabel>
        </div>
      ) : null}
      <h2
        data-split
        className="display text-balance text-[clamp(1.75rem,3.4vw,2.65rem)] leading-[1.08]"
      >
        {title}
      </h2>
      {lede ? (
        <p
          data-reveal
          className={cn(
            "text-pretty text-[14.5px] leading-[1.7] text-ink-muted sm:text-[15.5px]",
            align === "center" && "max-w-2xl",
          )}
        >
          {lede}
        </p>
      ) : null}
    </div>
  );

  if (!aside) return heading;

  return (
    <div
      className={cn(
        "grid min-w-0 items-end gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-12",
        className,
      )}
    >
      {heading}
      <div data-reveal className="min-w-0 lg:pb-1">
        {aside}
      </div>
    </div>
  );
}

/** A section band with consistent vertical rhythm and an optional hairline. */
export function Band({
  id,
  children,
  className,
  divided = true,
  tight = false,
}: {
  id?: string;
  children: React.ReactNode;
  className?: string;
  divided?: boolean;
  tight?: boolean;
}) {
  return (
    <section
      id={id}
      className={cn(
        "relative scroll-mt-24",
        tight ? "py-12 sm:py-14" : "py-16 sm:py-20",
        divided && "border-t border-line",
        className,
      )}
    >
      <div className="page-shell">{children}</div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Interaction
// --------------------------------------------------------------------------

/** A button or link that leans toward the pointer. */
export function Magnetic({
  children,
  className,
  strength = 0.2,
}: {
  children: React.ReactNode;
  className?: string;
  strength?: number;
}) {
  const ref = useMagnetic<HTMLSpanElement>(strength);
  return (
    <span ref={ref} className={cn("inline-block will-change-transform", className)}>
      {children}
    </span>
  );
}

const CTA_BASE =
  "group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-lg px-6 py-3 text-[14px] font-medium transition-[transform,box-shadow,background-color,border-color] duration-300 ease-out-quint";

/** The primary call to action: a sheen sweeps across it on hover. */
export function CtaLink({
  to,
  href,
  children,
  variant = "primary",
  className,
}: {
  to?: string;
  href?: string;
  children: React.ReactNode;
  variant?: "primary" | "ghost";
  className?: string;
}) {
  const classes = cn(
    CTA_BASE,
    variant === "primary"
      ? "bg-accent text-[oklch(0.14_0.01_265)] shadow-raise hover:-translate-y-0.5 hover:bg-accent-strong hover:shadow-float"
      : "border border-line bg-surface/60 text-ink backdrop-blur hover:-translate-y-0.5 hover:border-line-strong hover:bg-surface-raised",
    className,
  );

  const inner = (
    <>
      <span className="relative z-10 inline-flex items-center gap-2">{children}</span>
      <span
        aria-hidden
        className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 ease-out-quint group-hover:translate-x-full"
      />
    </>
  );

  if (href) {
    return (
      <Magnetic>
        <a href={href} target="_blank" rel="noreferrer noopener" className={classes}>
          {inner}
        </a>
      </Magnetic>
    );
  }
  return (
    <Magnetic>
      <Link to={to ?? "/"} className={classes}>
        {inner}
      </Link>
    </Magnetic>
  );
}

/**
 * A card that tilts a little toward the pointer and lifts a highlight with it.
 *
 * The highlight is a CSS custom property updated on pointermove, so the whole
 * effect is one repaint and no React state.
 */
export function SpotlightCard({
  children,
  className,
  tilt = true,
}: {
  children: React.ReactNode;
  className?: string;
  tilt?: boolean;
}) {
  const ref = React.useRef<HTMLDivElement>(null);

  const onMove = React.useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width;
      const py = (event.clientY - rect.top) / rect.height;
      el.style.setProperty("--spot-x", `${px * 100}%`);
      el.style.setProperty("--spot-y", `${py * 100}%`);
      if (tilt) {
        el.style.setProperty("--tilt-x", `${(0.5 - py) * 5}deg`);
        el.style.setProperty("--tilt-y", `${(px - 0.5) * 5}deg`);
      }
    },
    [tilt],
  );

  const onLeave = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--tilt-x", "0deg");
    el.style.setProperty("--tilt-y", "0deg");
  }, []);

  return (
    <div
      ref={ref}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      className={cn("spotlight-card group relative overflow-hidden", className)}
    >
      {children}
    </div>
  );
}

/**
 * An infinite horizontal marquee.
 *
 * The row is duplicated and the track translated by exactly -50%, so the seam
 * lands on an identical frame and the loop is invisible.
 */
export function Marquee({
  children,
  speed = 42,
  reverse = false,
  className,
}: {
  children: React.ReactNode;
  speed?: number;
  reverse?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn("marquee group relative flex overflow-hidden", className)}
      style={{ ["--marquee-duration" as string]: `${speed}s` }}
    >
      {[0, 1].map((copy) => (
        <div
          key={copy}
          aria-hidden={copy === 1}
          className={cn(
            "flex shrink-0 items-center gap-10 pr-10",
            reverse ? "animate-marquee-reverse" : "animate-marquee",
          )}
        >
          {children}
        </div>
      ))}
    </div>
  );
}

/** A statistic with a counter that runs when it scrolls into view. */
export function Stat({
  value,
  suffix = "",
  decimals = 0,
  label,
  note,
  className,
}: {
  value: number;
  suffix?: string;
  decimals?: number;
  label: string;
  note?: string;
  className?: string;
}) {
  return (
    <div data-reveal className={cn("flex flex-col gap-1.5", className)}>
      <div
        data-count={value}
        data-count-decimals={decimals}
        data-count-suffix={suffix}
        className="mono text-[clamp(2rem,4vw,2.9rem)] font-semibold leading-none tracking-[-0.03em] text-ink"
      >
        {value.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })}
        {suffix}
      </div>
      <div className="text-[13px] font-medium text-ink">{label}</div>
      {note ? <div className="text-[12px] leading-relaxed text-ink-subtle">{note}</div> : null}
    </div>
  );
}

/** A framed browser chrome, for showing the product without a screenshot. */
export function AppWindow({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-line bg-surface shadow-float",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-line bg-surface-sunken px-4 py-2.5">
        {/* Traffic lights, in the order every real window puts them: close,
            minimise, zoom. They are decoration, not controls, so they carry
            no label and no title - a screen reader should not announce three
            buttons that do nothing.

            macOS's own values, hardcoded rather than taken from the semantic
            tokens. Window chrome is the same colour on every desktop whatever
            the theme, so theming these made them read as status lights - a
            red one next to the word "plan" looked like something had failed.
            The inset ring is what keeps them from disappearing against a
            light title bar, which is also what macOS does. */}
        <div className="flex gap-1.5" aria-hidden>
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57] ring-1 ring-inset ring-black/10" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e] ring-1 ring-inset ring-black/10" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840] ring-1 ring-inset ring-black/10" />
        </div>
        <div className="mono min-w-0 flex-1 truncate text-center text-[11px] text-ink-subtle">
          {title}
        </div>
        <div className="w-12" />
      </div>
      {children}
    </div>
  );
}
