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

import { ArrowRight, Flame, Snowflake } from "lucide-react";
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

  const desktop = useIsDesktop();
  const reduced = useReducedMotion();
  const enabled = desktop && !reduced;

  usePinnedStory(
    root,
    ({ gsap }, el) => {
      const q = gsap.utils.selector(el);
      const tl = gsap.timeline();

      // Beat 1 -> 2: the cold figures settle, Plan A gets the ring.
      tl.to(q("[data-plan='local']"), { borderColor: "var(--color-accent)", duration: 0.4 }, 0.6)
        .to(q("[data-winner='cold']"), { opacity: 1, y: 0, duration: 0.4 }, 0.7)
        // Beat 3: the warm-up sweeps across Plan B's steps.
        .to(q("[data-warm-sweep]"), { scaleX: 1, duration: 0.7, ease: "power2.inOut" }, 1.5)
        // Beat 4: the ring moves, and the marginal column takes over.
        .to(q("[data-plan='local']"), { borderColor: "var(--color-line)", duration: 0.35 }, 2.5)
        .to(q("[data-winner='cold']"), { opacity: 0, y: -8, duration: 0.3 }, 2.5)
        .to(q("[data-plan='maps']"), { borderColor: "var(--color-warm)", duration: 0.4 }, 2.6)
        .to(q("[data-winner='marginal']"), { opacity: 1, y: 0, duration: 0.4 }, 2.7)
        .to(q("[data-cold-col]"), { opacity: 0.35, duration: 0.4 }, 2.6)
        .to(q("[data-marginal-col]"), { opacity: 1, duration: 0.4 }, 2.6);

      return tl;
    },
    {
      distance: 3.2,
      enabled,
      onProgress: (p) => {
        setBeat(Math.min(BEATS.length - 1, Math.floor(p * BEATS.length)));
        setWarm(p > 0.42);
        setFlipped(p > 0.68);
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
          "relative mx-auto flex w-full max-w-6xl flex-col gap-10 px-5 py-20 sm:px-8",
          enabled && "min-h-dvh justify-center py-24",
        )}
      >
        <div className="flex flex-col gap-4">
          <MonoLabel>the thesis</MonoLabel>
          <h2 className="max-w-3xl text-balance text-[clamp(1.9rem,4.2vw,3.1rem)] font-semibold leading-[1.08] tracking-[-0.03em]">
            Same intent. Same catalog. A different plan wins.
          </h2>
        </div>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] lg:items-start lg:gap-14">
          {/* The beats. On desktop the active one is lit; elsewhere all are. */}
          <ol className="flex flex-col gap-4">
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
                      ? "border-warm shadow-raise"
                      : "border-line",
                  )}
                >
                  {/* The warm-up sweep. scaleX is driven by the timeline on
                      desktop; the static fallback just shows it filled. */}
                  {plan.id === "maps" ? (
                    <div
                      data-warm-sweep
                      aria-hidden
                      className="pointer-events-none absolute inset-0 origin-left bg-gradient-to-r from-warm-ghost via-warm-ghost/60 to-transparent"
                      style={{ transform: `scaleX(${staticState ? 1 : 0})` }}
                    />
                  ) : null}

                  <div className="relative flex items-center justify-between gap-3 pb-3">
                    <div className="flex items-center gap-2.5">
                      <span className="mono text-[11px] uppercase tracking-[0.14em] text-ink-subtle">
                        {plan.label}
                      </span>
                      {planWarm ? (
                        <span className="mono inline-flex items-center gap-1 rounded-full border border-warm/30 bg-warm-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-warm">
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
                          "mono absolute right-0 whitespace-nowrap rounded-full border border-warm/40 bg-warm-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-warm",
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
                          plan.marginal === 0 ? "text-warm" : "text-ink",
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
