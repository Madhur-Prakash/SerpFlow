/**
 * The thesis, told on scroll.
 *
 * Four beats, pinned: two candidate plans appear, the cold ranking picks the
 * cheap one, the cache warms one family, and the marginal ranking flips the
 * winner. Scrubbed rather than played, so scrolling back runs it in reverse and
 * somebody can hold the moment the selection changes.
 *
 * The numbers are the demo's real ones - 51 against 101 cold, 1 against 0
 * marginal. Nothing here is illustrative.
 */

import { ArrowRight, ChevronDown, Flame, Snowflake } from "lucide-react";
import * as React from "react";

import { usePinnedStory } from "@/animations/scroll";
import { Atmosphere, MonoLabel } from "@/components/marketing";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { cn } from "@/lib/utils";

type Plan = {
  id: "local" | "maps";
  label: string;
  engines: string[];
  cold: number;
  marginal: number;
};

const PLANS: Plan[] = [
  {
    id: "local",
    label: "Plan A",
    engines: ["google_local", "google_maps_reviews", "google_maps_contributor_reviews"],
    cold: 51,
    marginal: 1,
  },
  {
    id: "maps",
    label: "Plan B",
    engines: ["google_maps", "google_maps_reviews", "google_maps_contributor_reviews"],
    cold: 101,
    marginal: 0,
  },
];

/**
 * Beat boundaries on the timeline, one unit each.
 *
 * The ScrollTrigger scrubs 0 to 1 across the pinned distance and the timeline
 * is `BEATS.length` units long, so unit N and beat N are the same place.
 */
const BEAT_2 = 1;
const BEAT_3 = 2;
const BEAT_4 = 3;

const BEATS = [
  {
    title: "Two plans reach the same answer",
    body: "Both chains end at contributor identity. They differ only at the entry engine, so either one answers the question.",
  },
  {
    title: "Cold ranking picks the cheaper one",
    body: "51 credits against 101. With no cache to consult, that is the whole comparison, and Plan A wins it.",
  },
  {
    title: "A related run warms one family",
    body: "Someone asks a neighbouring question. The Maps corpus fills; the Local corpus does not. Nothing about the catalog has changed.",
  },
  {
    title: "Marginal ranking flips the selection",
    body: "Plan B still costs 101 cold, and 0 now. Plan A still costs 51 cold, and 1 now. The expensive plan is the cheap one, and it executes.",
  },
] as const;

export function ThesisStory() {
  const root = React.useRef<HTMLElement>(null);
  const [beat, setBeat] = React.useState(0);
  const [warm, setWarm] = React.useState(false);
  const [flipped, setFlipped] = React.useState(false);
  const [progress, setProgress] = React.useState(0);

  const desktop = useIsDesktop();
  const reduced = useReducedMotion();
  const enabled = desktop && !reduced;

  usePinnedStory(
    root,
    ({ gsap }, el) => {
      const q = gsap.utils.selector(el);
      const tl = gsap.timeline();

      // One timeline unit per beat, so the rail, the beat label and what the
      // cards are doing cannot disagree. Previously the counter read 04/04
      // while the flip was still a fifth of the scroll away.
      tl.to(q("[data-plan='local']"), { borderColor: "var(--color-accent)", duration: 0.3 }, BEAT_2)
        .to(q("[data-winner='cold']"), { opacity: 1, y: 0, duration: 0.3 }, BEAT_2 + 0.1)
        .to(
          q("[data-warm-sweep]"),
          { scaleX: 1, duration: 0.6, ease: "power2.inOut" },
          BEAT_3 + 0.1,
        )
        // Beat 4 opens with the flip rather than ending on it, so the last
        // stretch of scrolling is spent reading the result.
        .to(q("[data-plan='local']"), { borderColor: "var(--color-line)", duration: 0.25 }, BEAT_4)
        .to(q("[data-winner='cold']"), { opacity: 0, y: -8, duration: 0.2 }, BEAT_4)
        .to(q("[data-plan='maps']"), { borderColor: "var(--color-accent)", duration: 0.3 }, BEAT_4 + 0.1)
        .to(q("[data-cold-col]"), { opacity: 0.35, duration: 0.3 }, BEAT_4 + 0.1)
        .to(q("[data-marginal-col]"), { opacity: 1, duration: 0.3 }, BEAT_4 + 0.1)
        .to(q("[data-winner='marginal']"), { opacity: 1, y: 0, duration: 0.3 }, BEAT_4 + 0.2)
        // A beat of stillness, so the timeline's last unit is readable rather
        // than a frame that only exists at the very bottom of the scroll.
        .to({}, { duration: 0.4 }, BEAT_4 + 0.6);

      return tl;
    },
    {
      distance: 3.2,
      enabled,
      onProgress: (p) => {
        setProgress(p);
        setBeat(Math.min(BEATS.length - 1, Math.floor(p * BEATS.length)));
        // Thresholds sit just inside their beat, so the badge and the card
        // change together rather than a scroll-tick apart.
        setWarm(p >= 0.52);
        setFlipped(p >= 0.76);
      },
    },
  );

  // Without the pinned story (narrow screens, reduced motion) the same content
  // reads top to bottom in its final state. The claim does not depend on the
  // animation.
  const staticState = !enabled;
  const showWarm = staticState || warm;
  const showFlip = staticState || flipped;

  return (
    <section
      ref={root}
      id="thesis"
      className="relative overflow-hidden border-t border-line bg-ground"
    >
      <Atmosphere variant="band" />

      <div
        className={cn(
          "page-shell relative flex min-w-0 flex-col gap-8 py-14",
          enabled && "min-h-dvh justify-center py-16",
        )}
      >
        <div className="grid min-w-0 items-end gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-12">
          <div className="flex min-w-0 flex-col gap-4">
            <MonoLabel>the thesis</MonoLabel>
            <h2 className="display text-balance text-[clamp(1.75rem,3.4vw,2.65rem)] leading-[1.08]">
              Same intent. Same catalog. A different plan wins.
            </h2>
          </div>

          {/* The story's own progress. On a pinned section the page scrollbar
              stops moving, so without this there is nothing telling a reader
              that scrolling is still doing something. */}
          {enabled ? (
            <div className="flex flex-col gap-3 lg:pb-1">
              <div className="flex items-baseline justify-between gap-4">
                <span className="mono text-[10.5px] uppercase tracking-[0.16em] text-ink-subtle">
                  {BEATS[beat].title}
                </span>
                <span className="mono shrink-0 text-[10.5px] tabular-nums text-ink-subtle">
                  <span className="text-accent-strong">
                    {String(Math.min(BEATS.length, beat + 1)).padStart(2, "0")}
                  </span>
                  {" / 0"}
                  {BEATS.length}
                </span>
              </div>

              {/* One continuous track with a head that travels it, rather than
                  four separate gradient segments. The beat marks stay as
                  stops on the way, so the structure is still legible. */}
              <div className="relative h-5">
                <span
                  aria-hidden
                  className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 rounded-full bg-line"
                />
                <span
                  aria-hidden
                  className="absolute left-0 top-1/2 h-px origin-left -translate-y-1/2 rounded-full bg-accent transition-none"
                  style={{ width: `${progress * 100}%` }}
                />

                {BEATS.map((item, index) => {
                  const at = (index / (BEATS.length - 1)) * 100;
                  const reached = progress >= index / BEATS.length - 0.001;
                  return (
                    <span
                      key={item.title}
                      aria-hidden
                      style={{ left: `${at}%` }}
                      className={cn(
                        "absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full",
                        "transition-[background-color,box-shadow,transform] duration-400 ease-out-quint",
                        reached
                          ? "scale-100 bg-accent"
                          : "scale-75 bg-line-strong",
                      )}
                    />
                  );
                })}

                {/* The head: a lit dot that rides the track. */}
                <span
                  aria-hidden
                  style={{ left: `${progress * 100}%` }}
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent shadow-[0_0_0_4px_var(--color-accent-ghost),0_0_12px_2px_var(--color-accent-ghost)]"
                />
              </div>

              {/* A cue that bows out once the story is moving. */}
              <div
                className={cn(
                  "flex items-center gap-1.5 text-[11.5px] text-ink-subtle",
                  "transition-opacity duration-500",
                  progress > 0.04 ? "opacity-0" : "opacity-100",
                )}
              >
                <ChevronDown className="h-3.5 w-3.5 animate-nudge" />
                Keep scrolling
              </div>
            </div>
          ) : null}
        </div>

        <div className="grid min-w-0 gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:items-start lg:gap-10">
          {/* The beats. On desktop the active one is lit; elsewhere all are. */}
          <ol className="flex min-w-0 flex-col gap-4">
            {BEATS.map((item, index) => {
              const active = staticState || index <= beat;
              const current = !staticState && index === beat;
              return (
                <li
                  key={item.title}
                  className={cn(
                    "relative flex gap-4 rounded-xl border p-4 transition-[opacity,border-color,background-color] duration-500 ease-out-quint",
                    current
                      ? "border-line-strong bg-surface"
                      : "border-transparent bg-transparent",
                    active ? "opacity-100" : "opacity-35",
                  )}
                >
                  <span
                    className={cn(
                      "mono mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-[11px] transition-colors duration-500",
                      current
                        ? "border-accent bg-accent-ghost text-accent-strong"
                        : "border-line text-ink-subtle",
                    )}
                  >
                    {index + 1}
                  </span>
                  <div className="flex flex-col gap-1.5">
                    <h3 className="text-[14.5px] font-medium leading-snug text-ink">
                      {item.title}
                    </h3>
                    <p className="text-[13px] leading-[1.65] text-ink-muted">{item.body}</p>
                  </div>
                </li>
              );
            })}
          </ol>

          {/* The two plans. */}
          <div className="flex flex-col gap-4">
            {PLANS.map((plan) => {
              const isWinner = showFlip ? plan.id === "maps" : plan.id === "local";
              const planWarm = plan.id === "maps" && showWarm;
              return (
                <div
                  key={plan.id}
                  data-plan={plan.id}
                  className={cn(
                    "relative overflow-hidden rounded-xl border bg-surface p-4 transition-[border-color,box-shadow] duration-500 ease-out-quint sm:p-5",
                    staticState && isWinner
                      ? "border-accent shadow-raise"
                      : "border-line",
                  )}
                >
                  {/* The warm-up sweep. scaleX is driven by the timeline on
                      desktop; the static fallback just shows it filled.
                      Accent-tinted: `warm` here means cache-warm, not a
                      temperature, and the green read as a success state. */}
                  {plan.id === "maps" ? (
                    <div
                      data-warm-sweep
                      aria-hidden
                      className="pointer-events-none absolute inset-0 origin-left bg-gradient-to-r from-accent-ghost via-accent-ghost/60 to-transparent"
                      style={{ transform: `scaleX(${staticState ? 1 : 0})` }}
                    />
                  ) : null}

                  <div className="relative flex items-center justify-between gap-3 pb-3">
                    <div className="flex items-center gap-2.5">
                      <span className="mono text-[11px] uppercase tracking-[0.14em] text-ink-subtle">
                        {plan.label}
                      </span>
                      {planWarm ? (
                        <span className="mono inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
                          <Flame className="h-2.5 w-2.5" />
                          warm
                        </span>
                      ) : (
                        <span className="mono inline-flex items-center gap-1 rounded-full border border-line bg-surface-sunken px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-subtle">
                          <Snowflake className="h-2.5 w-2.5" />
                          cold
                        </span>
                      )}
                    </div>

                    <div className="relative h-5">
                      <span
                        data-winner="cold"
                        className={cn(
                          "mono absolute right-0 whitespace-nowrap rounded-full border border-accent-muted/50 bg-accent-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent-strong",
                          plan.id === "local" ? "" : "hidden",
                        )}
                        style={
                          staticState
                            ? { opacity: showFlip ? 0 : 1, transform: "none" }
                            : { opacity: 0, transform: "translateY(8px)" }
                        }
                      >
                        cold winner
                      </span>
                      <span
                        data-winner="marginal"
                        className={cn(
                          "mono absolute right-0 whitespace-nowrap rounded-full border border-accent/40 bg-accent-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent",
                          plan.id === "maps" ? "" : "hidden",
                        )}
                        style={
                          staticState
                            ? { opacity: showFlip ? 1 : 0, transform: "none" }
                            : { opacity: 0, transform: "translateY(8px)" }
                        }
                      >
                        selected
                      </span>
                    </div>
                  </div>

                  <div className="relative flex flex-col gap-1.5">
                    {plan.engines.map((engine, index) => (
                      <div key={engine} className="flex items-center gap-2">
                        <span className="mono w-3 shrink-0 text-[10px] text-ink-subtle">
                          {index}
                        </span>
                        <span className="mono flex-1 truncate text-[11.5px] text-ink-muted">
                          {engine}
                        </span>
                        {index < plan.engines.length - 1 ? (
                          <ArrowRight className="h-3 w-3 shrink-0 text-ink-subtle/60" />
                        ) : null}
                      </div>
                    ))}
                  </div>

                  <div className="relative mt-4 grid grid-cols-2 gap-3 border-t border-line pt-3">
                    <div data-cold-col className="flex flex-col gap-0.5">
                      <span className="mono text-[10px] uppercase tracking-[0.14em] text-ink-subtle">
                        cold
                      </span>
                      <span className="mono text-[19px] font-semibold leading-none text-ink-subtle">
                        {plan.cold}
                      </span>
                    </div>
                    <div
                      data-marginal-col
                      className="flex flex-col gap-0.5"
                      style={staticState ? undefined : { opacity: 0.4 }}
                    >
                      <span className="mono text-[10px] uppercase tracking-[0.14em] text-ink-subtle">
                        marginal
                      </span>
                      <span
                        className={cn(
                          "mono text-[19px] font-semibold leading-none",
                          plan.marginal === 0 ? "text-accent" : "text-ink",
                        )}
                      >
                        {showWarm ? plan.marginal : plan.cold}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}

            <p className="text-[12.5px] leading-relaxed text-ink-subtle">
              A cache hit on the same plan is not this. The metric that counts it is{" "}
              <code className="mono text-ink-muted">
                serpflow_marginal_replan_changed_selection_total
              </code>
              , and <code className="mono text-ink-muted">make demo</code> exits non-zero if it
              stays at zero.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
