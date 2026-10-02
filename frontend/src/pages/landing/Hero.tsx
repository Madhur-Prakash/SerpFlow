import { ArrowRight, BookOpen, Check, Terminal } from "lucide-react";
import * as React from "react";

import { loadScrollTools, useParallax } from "@/animations/scroll";
import { AppWindow, Atmosphere, CtaLink, MonoLabel } from "@/components/marketing";
import { motionAllowed } from "@/hooks/useReducedMotion";

/** The plan the hero animates: the one the demo actually produces. */
const STEPS = [
  { engine: "google_maps", fan: 1, credits: 1, warm: true },
  { engine: "google_maps_reviews", fan: 20, credits: 20, warm: true },
  { engine: "google_maps_contributor_reviews", fan: 80, credits: 80, warm: true },
] as const;

export function Hero() {
  const root = React.useRef<HTMLElement>(null);
  const [cost, setCost] = React.useState(101);

  useParallax(root, { distance: 70 });

  // The entrance timeline. Written by hand rather than with useReveal because
  // the order matters here: label, heading, lede, actions, then the panel
  // rising with the cost counting down inside it.
  React.useEffect(() => {
    const el = root.current;
    if (!el) return;
    if (!motionAllowed()) {
      setCost(0);
      return;
    }

    let revert: (() => void) | undefined;
    let alive = true;

    void loadScrollTools().then(({ gsap, SplitText }) => {
      if (!alive) return;
      const ctx = gsap.context(() => {
        const heading = el.querySelector<HTMLElement>("[data-hero-title]");
        const split = heading
          ? new SplitText(heading, { type: "lines,words", linesClass: "split-line" })
          : null;

        const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

        tl.from("[data-hero-label]", { opacity: 0, y: 14, duration: 0.6 });

        if (split) {
          tl.from(
            split.words,
            { yPercent: 118, opacity: 0, duration: 0.95, stagger: 0.035 },
            "-=0.35",
          );
        }

        tl.from("[data-hero-lede]", { opacity: 0, y: 18, duration: 0.7 }, "-=0.55")
          .from("[data-hero-action]", { opacity: 0, y: 14, duration: 0.6, stagger: 0.08 }, "-=0.45")
          .from("[data-hero-meta]", { opacity: 0, duration: 0.6, stagger: 0.06 }, "-=0.4")
          .from(
            "[data-hero-panel]",
            { opacity: 0, y: 46, rotateX: 7, duration: 1.1, transformPerspective: 1200 },
            "-=0.75",
          )
          .from("[data-hero-step]", { opacity: 0, x: -18, duration: 0.5, stagger: 0.11 }, "-=0.5")
          // The headline number counts 101 down to 0 as the warm badges land,
          // which is the whole product in one gesture.
          .to(
            { v: 101 },
            {
              v: 0,
              duration: 1.1,
              ease: "power2.inOut",
              onUpdate() {
                setCost(Math.round((this.targets()[0] as { v: number }).v));
              },
            },
            "-=0.3",
          );

        return () => split?.revert();
      }, el);
      revert = () => ctx.revert();
    });

    return () => {
      alive = false;
      revert?.();
    };
  }, []);

  return (
    <section ref={root} className="relative overflow-hidden">
      <Atmosphere variant="hero" />
      <div className="pointer-events-none absolute inset-0 grid-field-dense opacity-40" aria-hidden />

      <div className="relative mx-auto grid w-full max-w-6xl gap-14 px-5 pb-20 pt-14 sm:px-8 sm:pb-28 sm:pt-20 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16">
        <div className="flex flex-col items-start gap-6">
          <div data-hero-label>
            <MonoLabel>cache-aware marginal-cost replanning</MonoLabel>
          </div>

          <h1
            data-hero-title
            className="text-balance text-[clamp(2.1rem,4.4vw,3.5rem)] font-semibold leading-[1.05] tracking-[-0.035em]"
          >
            The cache should change <span className="text-accent">which plan wins</span>.
          </h1>

          <p
            data-hero-lede
            className="max-w-xl text-pretty text-[15.5px] leading-[1.75] text-ink-muted sm:text-[16.5px]"
          >
            Not just make the same plan cheaper. SerpFlow takes a natural-language intent,
            discovers the engine chain that answers it, inspects what is already warm, and ranks
            candidate plans on the cost of the steps that still need a live call.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <span data-hero-action>
              <CtaLink to="/app">
                Open the console
                <ArrowRight className="h-4 w-4 transition-transform duration-300 ease-out-quint group-hover:translate-x-0.5" />
              </CtaLink>
            </span>
            <span data-hero-action>
              <CtaLink to="/docs" variant="ghost">
                <BookOpen className="h-4 w-4" />
                Read the docs
              </CtaLink>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5 pt-1">
            {[
              "Runs on the SerpApi free tier",
              "No API keys to try it",
              "Apache-2.0",
            ].map((item) => (
              <span
                key={item}
                data-hero-meta
                className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-subtle"
              >
                <Check className="h-3.5 w-3.5 text-warm" />
                {item}
              </span>
            ))}
          </div>
        </div>

        <div data-hero-panel data-parallax="0.35" className="relative">
          <AppWindow title="serpflow plan --budget 20">
            <div className="flex flex-col gap-5 p-5 sm:p-6">
              <div className="flex items-start justify-between gap-4 border-b border-line pb-4">
                <div className="flex flex-col gap-1">
                  <span className="mono text-[11px] uppercase tracking-[0.14em] text-ink-subtle">
                    intent
                  </span>
                  <span className="text-[13.5px] leading-snug text-ink">
                    find coordinated review rings among Koramangala cafes
                  </span>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                {STEPS.map((step, index) => (
                  <div
                    key={step.engine}
                    data-hero-step
                    className="flex items-center gap-3 rounded-lg border border-line bg-surface-sunken px-3 py-2.5"
                  >
                    <span className="mono w-4 shrink-0 text-[11px] text-ink-subtle">{index}</span>
                    <span className="mono flex-1 truncate text-[12px] text-ink">{step.engine}</span>
                    <span className="mono shrink-0 text-[11px] text-ink-subtle">
                      &times;{step.fan}
                    </span>
                    <span className="mono inline-flex shrink-0 items-center gap-1 rounded-full border border-warm/30 bg-warm-ghost px-2 py-0.5 text-[10px] uppercase tracking-wider text-warm">
                      <span className="h-1 w-1 rounded-full bg-warm" />
                      warm
                    </span>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-3 gap-3 border-t border-line pt-4">
                <Figure label="cold" value="101" tone="muted" strike />
                <Figure label="marginal" value={String(cost)} tone="warm" />
                <Figure label="spent" value="0" tone="warm" />
              </div>

              <div className="rounded-lg border border-accent-muted/40 bg-accent-ghost/50 p-3.5">
                <div className="mono mb-1.5 text-[10px] uppercase tracking-[0.14em] text-accent-strong">
                  replan changed the selection
                </div>
                <p className="text-[12px] leading-relaxed text-ink-muted">
                  Ranked on cold cost alone,{" "}
                  <span className="mono text-ink">google_local&gt;&hellip;</span> would have won at
                  51 credits. It is cold. This plan costs 101 cold and 0 now.
                </p>
              </div>
            </div>
          </AppWindow>

          {/* A soft glow under the panel, parallaxing at a different rate. */}
          <div
            aria-hidden
            data-parallax="0.6"
            className="pointer-events-none absolute -inset-x-10 -bottom-16 -z-10 h-40 rounded-full bg-accent-ghost blur-[80px]"
          />
        </div>
      </div>
    </section>
  );
}

function Figure({
  label,
  value,
  tone,
  strike,
}: {
  label: string;
  value: string;
  tone: "muted" | "warm";
  strike?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="mono text-[10px] uppercase tracking-[0.14em] text-ink-subtle">{label}</span>
      <span
        className={[
          "mono text-[22px] font-semibold leading-none tracking-[-0.02em]",
          tone === "warm" ? "text-warm" : "text-ink-subtle",
          strike ? "line-through decoration-ink-subtle/50" : "",
        ].join(" ")}
      >
        {value}
      </span>
    </div>
  );
}

/** The strip of technologies under the hero, as a paused-on-hover marquee. */
export function StackStrip() {
  const items = [
    "Python 3.13",
    "FastAPI",
    "PostgreSQL 17",
    "pgvector",
    "Redis 7",
    "Kafka 4 KRaft",
    "SQLAlchemy 2",
    "Alembic",
    "Pydantic v2",
    "OpenTelemetry",
    "Prometheus",
    "React 19",
    "TypeScript",
    "Vite",
    "Tailwind CSS 4",
    "GSAP",
    "Docker",
  ];

  return (
    <div className="relative border-y border-line bg-surface-sunken/60 py-5">
      <div className="marquee group relative flex overflow-hidden">
        {[0, 1].map((copy) => (
          <div
            key={copy}
            aria-hidden={copy === 1}
            className="flex shrink-0 animate-marquee items-center gap-3 pr-3"
            style={{ ["--marquee-duration" as string]: "52s" }}
          >
            {items.map((item) => (
              <span
                key={item}
                className="mono inline-flex shrink-0 items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-[11.5px] text-ink-muted transition-colors duration-300 hover:border-line-strong hover:text-ink"
              >
                <Terminal className="h-3 w-3 text-accent/70" />
                {item}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
