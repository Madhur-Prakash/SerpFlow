/**
 * The shell around every public page: landing, docs, API reference.
 *
 * It owns the smooth-scroll engine, the scroll progress bar and the header's
 * condensed state. The signed-in console has its own shell and shares none of
 * this - different job, different motion budget.
 */

import { ArrowUpRight, BookOpen, Github, History, Menu, Terminal, X } from "lucide-react";
import * as React from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Tooltip, TooltipProvider } from "@/components/ui";
import { useSmoothScroll } from "@/hooks/useSmoothScroll";
import { scrollToAnchor, scrollToTop } from "@/lib/scroll";
import { cn } from "@/lib/utils";

/**
 * `route` items are pages; `hash` items are sections of the landing page.
 *
 * "Console" is deliberately absent: it is the primary button at the other end
 * of the same bar, and a nav that repeats its own call to action wastes the
 * one row a reader actually scans.
 */
const NAV: { to: string; label: string; hash?: boolean }[] = [
  { to: "/docs", label: "Docs" },
  { to: "/api", label: "API" },
  { to: "/#how-it-works", label: "How it works", hash: true },
  { to: "/#benchmark", label: "Benchmark", hash: true },
];

const YEAR = new Date().getFullYear();

// --------------------------------------------------------------------------
// Header
// --------------------------------------------------------------------------

function Wordmark({ onClick }: { onClick?: () => void }) {
  return (
    <Link
      to="/"
      onClick={onClick}
      className="group inline-flex min-w-0 shrink-0 items-center gap-2.5 text-[15px] font-semibold tracking-[-0.02em]"
    >
      <span className="relative inline-flex h-7 w-7 items-center justify-center overflow-hidden rounded-md border border-line bg-surface">
        <span className="absolute inset-0 bg-gradient-to-br from-accent-ghost to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
        <Terminal className="relative h-3.5 w-3.5 text-accent transition-transform duration-500 ease-out-quint group-hover:scale-110" />
      </span>
      <span>
        Serp<span className="text-accent">Flow</span>
      </span>
    </Link>
  );
}

function MarketingHeader() {
  const [condensed, setCondensed] = React.useState(false);
  const [open, setOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => {
    const onScroll = () => setCondensed(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  React.useEffect(() => setOpen(false), [location.pathname]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-[background-color,border-color,backdrop-filter] duration-400 ease-out-quint",
        condensed
          ? "border-b border-line bg-[var(--color-ground)]/85 backdrop-blur-xl"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="page-shell flex h-16 items-center justify-between gap-3 px-4 sm:gap-6 sm:px-8 lg:px-10">
        <Wordmark onClick={() => scrollToTop(false)} />

        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((item) =>
            item.hash ? (
              // A section link is never "active": its pathname is the landing
              // page, which would light it up on every scroll position.
              <Link
                key={item.to}
                to={item.to}
                className="group relative rounded-md px-3 py-2 text-[13.5px] text-ink-muted transition-colors duration-300 hover:text-ink"
              >
                {item.label}
                <span className="absolute inset-x-3 -bottom-px h-px origin-left scale-x-0 bg-accent transition-transform duration-400 ease-out-quint group-hover:scale-x-100" />
              </Link>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "group relative rounded-md px-3 py-2 text-[13.5px] text-ink-muted transition-colors duration-300 hover:text-ink",
                    isActive && "text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {item.label}
                    <span
                      className={cn(
                        "absolute inset-x-3 -bottom-px h-px origin-left bg-accent transition-transform duration-400 ease-out-quint",
                        isActive ? "scale-x-100" : "scale-x-0 group-hover:scale-x-100",
                      )}
                    />
                  </>
                )}
              </NavLink>
            ),
          )}
        </nav>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <Tooltip
            content={
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-ink">What changed</span>
                <span className="text-ink-muted">Release notes and catalog version</span>
              </span>
            }
          >
            <Link
              to="/docs/readme:CHANGELOG"
              aria-label="Changelog"
              className="hidden h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface/70 text-ink-muted backdrop-blur transition-[color,transform,border-color] duration-300 ease-out-quint hover:-translate-y-px hover:border-line-strong hover:text-ink sm:inline-flex"
            >
              <History className="h-[17px] w-[17px]" />
            </Link>
          </Tooltip>
          <ThemeToggle />
          <Link
            to="/app"
            className="hidden items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-[13px] font-medium text-[oklch(0.14_0.01_265)] shadow-raise transition-[transform,background-color,box-shadow] duration-300 ease-out-quint hover:-translate-y-px hover:bg-accent-strong hover:shadow-float sm:inline-flex"
          >
            Open console
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface/70 text-ink-muted backdrop-blur md:hidden"
          >
            {open ? <X className="h-[17px] w-[17px]" /> : <Menu className="h-[17px] w-[17px]" />}
          </button>
        </div>
      </div>

      {/* Mobile sheet. Height-animated rather than mounted/unmounted so it
          closes as smoothly as it opens. */}
      <div
        className={cn(
          "grid overflow-hidden border-line bg-[var(--color-ground)]/95 backdrop-blur-xl transition-[grid-template-rows,border-width] duration-400 ease-out-quint md:hidden",
          open ? "grid-rows-[1fr] border-b" : "grid-rows-[0fr] border-b-0",
        )}
      >
        <div className="min-h-0">
          <nav className="flex flex-col gap-1 px-5 py-4">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="rounded-md px-3 py-2.5 text-[15px] text-ink-muted transition-colors hover:bg-surface hover:text-ink"
              >
                {item.label}
              </Link>
            ))}
            <Link
              to="/docs/readme:CHANGELOG"
              className="rounded-md px-3 py-2.5 text-[15px] text-ink-muted transition-colors hover:bg-surface hover:text-ink"
            >
              Changelog
            </Link>
            <Link
              to="/app"
              className="mt-2 inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-4 py-2.5 text-[14px] font-medium text-[oklch(0.14_0.01_265)]"
            >
              Open console
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
}

// --------------------------------------------------------------------------
// Footer
// --------------------------------------------------------------------------

const FOOTER_GROUPS: { title: string; links: { label: string; to?: string; href?: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "How it works", to: "/#how-it-works" },
      { label: "Marginal replanning", to: "/#thesis" },
      { label: "Cache layers", to: "/#cache" },
      { label: "Benchmark", to: "/#benchmark" },
      { label: "Console", to: "/app" },
    ],
  },
  {
    title: "Developers",
    links: [
      { label: "Documentation", to: "/docs" },
      { label: "API reference", to: "/api" },
      { label: "Streaming", to: "/docs/api/streaming" },
      { label: "SDKs", to: "/docs/api/examples" },
      { label: "OpenAPI", href: "http://localhost:8000/docs" },
    ],
  },
  {
    title: "Operations",
    links: [
      { label: "Local development", to: "/docs/deployment/local" },
      { label: "Docker", to: "/docs/deployment/docker" },
      { label: "Observability", to: "/docs/operations/observability" },
      { label: "Troubleshooting", to: "/docs/operations/troubleshooting" },
    ],
  },
  {
    title: "Project",
    links: [
      { label: "Architecture", to: "/docs/architecture/overview" },
      { label: "Decision records", to: "/docs/adr" },
      { label: "Security", to: "/docs/security/threat-model" },
      { label: "GitHub", href: "https://github.com/serpflow/serpflow" },
    ],
  },
];

function MarketingFooter() {
  return (
    <footer className="relative border-t border-line bg-surface-sunken">
      <div className="pointer-events-none absolute inset-0 grid-field opacity-30" aria-hidden />

      <div className="page-shell relative py-14 sm:py-16">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_3fr]">
          <div className="flex flex-col gap-5">
            <Wordmark />
            <p className="max-w-xs text-[13.5px] leading-[1.75] text-ink-muted">
              A search control plane for SerpApi. It re-plans around what is already warm and
              executes only the searches that still need a live call.
            </p>
            <div className="flex items-center gap-2">
              <Tooltip content="Source on GitHub">
                <a
                  href="https://github.com/serpflow/serpflow"
                  target="_blank"
                  rel="noreferrer noopener"
                  aria-label="Source on GitHub"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink-muted transition-[color,transform,border-color] duration-300 ease-out-quint hover:-translate-y-px hover:border-line-strong hover:text-ink"
                >
                  <Github className="h-[17px] w-[17px]" />
                </a>
              </Tooltip>
              <Tooltip content="Documentation">
                <Link
                  to="/docs"
                  aria-label="Documentation"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink-muted transition-[color,transform,border-color] duration-300 ease-out-quint hover:-translate-y-px hover:border-line-strong hover:text-ink"
                >
                  <BookOpen className="h-[17px] w-[17px]" />
                </Link>
              </Tooltip>
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-2 gap-8 sm:grid-cols-4">
            {FOOTER_GROUPS.map((group) => (
              <div key={group.title} className="flex min-w-0 flex-col gap-3.5">
                <h3 className="mono text-[11px] uppercase tracking-[0.16em] text-ink-subtle">
                  {group.title}
                </h3>
                <ul className="flex flex-col gap-2.5">
                  {group.links.map((link) => (
                    <li key={link.label}>
                      {link.href ? (
                        <a
                          href={link.href}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="link-underline inline-flex items-center gap-1 text-[13px] text-ink-muted transition-colors duration-300 hover:text-ink"
                        >
                          {link.label}
                          <ArrowUpRight className="h-3 w-3 opacity-60" />
                        </a>
                      ) : (
                        <Link
                          to={link.to ?? "/"}
                          className="link-underline text-[13px] text-ink-muted transition-colors duration-300 hover:text-ink"
                        >
                          {link.label}
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t border-line pt-7 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[12.5px] text-ink-subtle">
            &copy; {YEAR} SerpFlow. All rights reserved.
          </p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px] text-ink-subtle">
            <span className="mono">Apache-2.0</span>
            <Link to="/docs/security/threat-model" className="transition-colors hover:text-ink">
              Security
            </Link>
            <Link to="/docs" className="transition-colors hover:text-ink">
              Documentation
            </Link>
            <span className="mono text-ink-subtle/70">catalog v1.0.0</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

// --------------------------------------------------------------------------
// Scroll progress
// --------------------------------------------------------------------------

/**
 * A hairline that fills as the page scrolls.
 *
 * Written straight to a CSS custom property from rAF - putting scroll position
 * in React state re-renders the whole tree sixty times a second for one line.
 */
function ScrollProgress() {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const value = max > 0 ? Math.min(1, window.scrollY / max) : 0;
      ref.current?.style.setProperty("--progress", String(value));
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
  }, []);

  return (
    <div
      aria-hidden
      className="fixed inset-x-0 top-0 z-[60] h-[3px] bg-[var(--color-line)]/40"
    >
      <div
        ref={ref}
        className="scroll-progress relative h-full bg-gradient-to-r from-accent via-accent-strong to-warm"
      >
        {/* A lit tip at the leading edge, so the bar reads as moving rather
            than as a static rule that happens to be a different width. */}
        <span className="absolute right-0 top-1/2 h-[7px] w-[7px] -translate-y-1/2 translate-x-1/2 rounded-full bg-warm shadow-[0_0_10px_2px_var(--color-warm)]" />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Layout
// --------------------------------------------------------------------------

export function MarketingLayout() {
  const location = useLocation();
  useSmoothScroll();

  // A new page starts at the top; a hash goes to its section once the route's
  // content has rendered.
  React.useEffect(() => {
    if (location.hash) {
      const id = location.hash;
      const timer = window.setTimeout(() => scrollToAnchor(id), 80);
      return () => window.clearTimeout(timer);
    }
    scrollToTop(true);
  }, [location.pathname, location.hash]);

  return (
    <TooltipProvider delayDuration={220} skipDelayDuration={400}>
      <div className="flex min-h-dvh flex-col bg-ground text-ink">
        <ScrollProgress />
        <MarketingHeader />
        <main className="flex-1 pt-16">
          <Outlet />
        </main>
        <MarketingFooter />
      </div>
    </TooltipProvider>
  );
}
