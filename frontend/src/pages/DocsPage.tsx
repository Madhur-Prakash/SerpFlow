/**
 * The documentation browser.
 *
 * A three-column reading layout: section navigation, the document, and its own
 * table of contents. The markdown comes from the repository's `docs/` folder at
 * build time, so this page and the committed files cannot disagree.
 */

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  ExternalLink,
  FileText,
  Menu,
  Search,
  X,
} from "lucide-react";
import * as React from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Markdown, extractHeadings, slugify, type Heading } from "@/components/docs/Markdown";
import { Atmosphere, MonoLabel } from "@/components/marketing";
import { Input, ScrollArea, Skeleton } from "@/components/ui";
import { scrollToElement, scrollToTop } from "@/lib/scroll";
import {
  DOC_SECTIONS,
  findDoc,
  neighbours,
  sectionOf,
  type DocEntry,
} from "@/lib/docs";
import { cn } from "@/lib/utils";

const GITHUB_BASE = "https://github.com/serpflow/serpflow/blob/main/";

// --------------------------------------------------------------------------
// Navigation
// --------------------------------------------------------------------------

function SideNav({
  current,
  query,
  onNavigate,
}: {
  current: string;
  query: string;
  onNavigate?: () => void;
}) {
  const needle = query.trim().toLowerCase();

  const sections = React.useMemo(
    () =>
      DOC_SECTIONS.map((section) => ({
        ...section,
        entries: section.entries.filter(
          (entry) =>
            !needle ||
            entry.title.toLowerCase().includes(needle) ||
            entry.slug.toLowerCase().includes(needle),
        ),
      })).filter((section) => section.entries.length > 0),
    [needle],
  );

  if (!sections.length) {
    return <p className="px-2.5 py-6 text-[13px] text-ink-subtle">Nothing matches that.</p>;
  }

  return (
    <nav className="flex flex-col gap-7 pb-10 pr-3">
      {sections.map((section) => (
        <div key={section.id} className="flex flex-col gap-1.5">
          <h3 className="mono px-2.5 text-[10.5px] uppercase tracking-[0.16em] text-ink-subtle">
            {section.title}
          </h3>
          <ul className="flex flex-col gap-0.5">
            {section.entries.map((entry) => {
              const active = entry.slug === current;
              return (
                <li key={entry.slug}>
                  <Link
                    to={`/docs/${entry.slug}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative block rounded-md px-2.5 py-1.5 text-[13px] transition-colors duration-250",
                      active
                        ? "bg-accent-ghost/60 text-ink"
                        : "text-ink-muted hover:bg-surface hover:text-ink",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent transition-transform duration-300 ease-out-quint",
                        active ? "scale-y-100" : "scale-y-0",
                      )}
                    />
                    <span className="truncate">{entry.title}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/** The on-page contents, with the heading nearest the top highlighted. */
function TableOfContents({ headings }: { headings: Heading[] }) {
  const [active, setActive] = React.useState<string>("");

  React.useEffect(() => {
    if (!headings.length) return;

    // rootMargin pulls the detection line to just under the sticky header, so
    // the entry lights up as its heading reaches the top rather than when it
    // enters the viewport at the bottom.
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-88px 0px -70% 0px", threshold: 0 },
    );

    headings.forEach((heading) => {
      const el = document.getElementById(heading.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [headings]);

  if (headings.length < 2) return null;

  return (
    <div className="flex flex-col gap-3">
      <h3 className="mono text-[10.5px] uppercase tracking-[0.16em] text-ink-subtle">
        On this page
      </h3>
      <ul className="flex flex-col gap-0.5 border-l border-line">
        {headings.map((heading) => (
          <li key={heading.id}>
            <a
              href={`#${heading.id}`}
              onClick={(event) => {
                event.preventDefault();
                const el = document.getElementById(heading.id);
                if (el) scrollToElement(el);
              }}
              className={cn(
                "-ml-px block border-l-2 py-1 text-[12.5px] leading-snug transition-colors duration-250",
                heading.level === 3 ? "pl-6" : "pl-3",
                active === heading.id
                  ? "border-accent text-ink"
                  : "border-transparent text-ink-muted hover:border-line-strong hover:text-ink",
              )}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pager({ prev, next }: { prev?: DocEntry; next?: DocEntry }) {
  if (!prev && !next) return null;
  return (
    <nav className="mt-16 grid gap-3 border-t border-line pt-8 sm:grid-cols-2">
      {prev ? (
        <Link
          to={`/docs/${prev.slug}`}
          className="group flex flex-col gap-1 rounded-xl border border-line bg-surface p-4 transition-[border-color,transform] duration-300 ease-out-quint hover:-translate-y-0.5 hover:border-line-strong"
        >
          <span className="mono inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.14em] text-ink-subtle">
            <ArrowLeft className="h-3 w-3 transition-transform duration-300 group-hover:-translate-x-0.5" />
            Previous
          </span>
          <span className="text-[14px] font-medium text-ink">{prev.title}</span>
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link
          to={`/docs/${next.slug}`}
          className="group flex flex-col items-end gap-1 rounded-xl border border-line bg-surface p-4 text-right transition-[border-color,transform] duration-300 ease-out-quint hover:-translate-y-0.5 hover:border-line-strong sm:col-start-2"
        >
          <span className="mono inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.14em] text-ink-subtle">
            Next
            <ArrowRight className="h-3 w-3 transition-transform duration-300 group-hover:translate-x-0.5" />
          </span>
          <span className="text-[14px] font-medium text-ink">{next.title}</span>
        </Link>
      ) : null}
    </nav>
  );
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export function DocsPage() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const slug = (params["*"] ?? "").replace(/^\/+|\/+$/g, "");
  const entry = findDoc(slug);

  const [source, setSource] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [navOpen, setNavOpen] = React.useState(false);

  // Load the document. `alive` guards the case where somebody clicks through
  // two links faster than the first import resolves.
  React.useEffect(() => {
    if (!entry) {
      setSource(null);
      setFailed(true);
      return;
    }
    let alive = true;
    setSource(null);
    setFailed(false);
    void entry
      .load()
      .then((text) => {
        if (alive) setSource(text);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [entry]);

  // Jump to a hash once the document has rendered, not before it exists.
  React.useEffect(() => {
    if (!source) return;
    if (location.hash) {
      const timer = window.setTimeout(() => {
        const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        if (el) scrollToElement(el);
      }, 60);
      return () => window.clearTimeout(timer);
    }
    scrollToTop(true);
  }, [source, location.hash, slug]);

  React.useEffect(() => setNavOpen(false), [slug]);

  const headings = React.useMemo(() => (source ? extractHeadings(source) : []), [source]);
  const { prev, next } = neighbours(slug);
  const section = sectionOf(slug);

  if (failed && !entry) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-5 px-5 py-28 text-center">
        <FileText className="h-7 w-7 text-ink-subtle" />
        <h1 className="text-[1.6rem] font-semibold tracking-[-0.02em]">
          That page is not in the docs.
        </h1>
        <p className="text-[14.5px] leading-relaxed text-ink-muted">
          The documentation tree is read from the repository, so this path does not exist in it.
        </p>
        <button
          type="button"
          onClick={() => navigate("/docs")}
          className="mono rounded-lg border border-line bg-surface px-4 py-2 text-[13px] text-ink transition-colors hover:border-line-strong"
        >
          Back to the index
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Hero, on the index only. Inner pages go straight to the content. */}
      {slug === "" ? (
        <section className="relative overflow-hidden border-b border-line">
          <Atmosphere variant="band" />
          <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-5 px-5 py-14 sm:px-8 sm:py-20">
            <MonoLabel>
              <BookOpen className="h-3 w-3" />
              documentation
            </MonoLabel>
            <h1 className="max-w-3xl text-balance text-[clamp(2rem,4.6vw,3.2rem)] font-semibold leading-[1.06] tracking-[-0.035em]">
              Every page links to the code it describes.
            </h1>
            <p className="max-w-2xl text-pretty text-[15px] leading-[1.75] text-ink-muted">
              Rendered from the repository&apos;s own <code className="mono">docs/</code> directory.
              If a path in these pages does not exist in the project, that is a bug.
            </p>
          </div>
        </section>
      ) : null}

      <div className="mx-auto w-full max-w-7xl px-5 sm:px-8">
        <div className="grid gap-8 py-10 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_13rem] xl:gap-10">
          {/* Sidebar */}
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <button
              type="button"
              onClick={() => setNavOpen((v) => !v)}
              aria-expanded={navOpen}
              className="mb-3 inline-flex w-full items-center justify-between gap-2 rounded-lg border border-line bg-surface px-3 py-2.5 text-[13.5px] text-ink lg:hidden"
            >
              <span className="inline-flex items-center gap-2">
                <Menu className="h-4 w-4 text-ink-subtle" />
                {entry?.title ?? "Documentation"}
              </span>
              <span className="mono text-[11px] text-ink-subtle">
                {section?.title ?? "Browse"}
              </span>
            </button>

            <div
              className={cn(
                "grid overflow-hidden transition-[grid-template-rows] duration-400 ease-out-quint lg:grid-rows-[1fr]",
                navOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
              )}
            >
              <div className="min-h-0">
                <div className="relative mb-4">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle" />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Filter pages"
                    aria-label="Filter documentation pages"
                    className="h-9 pl-8 pr-8 text-[13px]"
                  />
                  {query ? (
                    <button
                      type="button"
                      onClick={() => setQuery("")}
                      aria-label="Clear filter"
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-subtle hover:text-ink"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </div>
                <ScrollArea className="lg:max-h-[calc(100dvh-12rem)]">
                  <SideNav current={slug} query={query} onNavigate={() => setNavOpen(false)} />
                </ScrollArea>
              </div>
            </div>
          </aside>

          {/* Document */}
          <article className="min-w-0 pb-12">
            {entry && section ? (
              <div className="mb-6 flex flex-wrap items-center gap-2 text-[12px] text-ink-subtle">
                <Link to="/docs" className="transition-colors hover:text-ink">
                  Docs
                </Link>
                <span aria-hidden>/</span>
                <span>{section.title}</span>
                <a
                  href={`${GITHUB_BASE}${entry.source}`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mono ml-auto inline-flex items-center gap-1.5 transition-colors hover:text-ink"
                >
                  {entry.source}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            ) : null}

            {source === null && !failed ? (
              <div className="flex flex-col gap-4">
                <Skeleton className="h-9 w-2/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="mt-4 h-36 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            ) : failed ? (
              <p className="text-[14px] text-danger">That page could not be loaded.</p>
            ) : (
              <Markdown source={source ?? ""} slug={slug} />
            )}

            <Pager prev={prev} next={next} />
          </article>

          {/* Contents */}
          <aside className="hidden xl:sticky xl:top-24 xl:block xl:self-start">
            <TableOfContents headings={headings} />
          </aside>
        </div>
      </div>
    </div>
  );
}

export { slugify };
