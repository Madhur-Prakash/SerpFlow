/**
 * The API reference.
 *
 * Rendered from `api-reference.generated.ts`, which `make api-reference` builds
 * from the OpenAPI schema. Nothing on this page is typed by hand, so it cannot
 * drift from the API the way a written endpoint list does.
 */

import { ChevronRight, Search, Terminal, X } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { useReveal } from "@/animations/scroll";
import { Atmosphere, MonoLabel } from "@/components/marketing";
import { Badge, Input, ScrollArea } from "@/components/ui";
import {
  API_GROUPS,
  API_OPERATIONS,
  API_OPERATION_COUNT,
  API_PATH_COUNT,
  API_VERSION,
  type ApiOperation,
} from "@/lib/api-reference.generated";
import { scrollToElement } from "@/lib/scroll";
import { cn } from "@/lib/utils";

const METHOD_TONE: Record<string, string> = {
  GET: "border-accent-muted/50 bg-accent-ghost text-accent-strong",
  POST: "border-warm/35 bg-warm-ghost text-warm",
  PATCH: "border-caution/35 bg-caution-ghost text-caution",
  PUT: "border-caution/35 bg-caution-ghost text-caution",
  DELETE: "border-danger/35 bg-danger-ghost text-danger",
};

function MethodBadge({ method, className }: { method: string; className?: string }) {
  return (
    <span
      className={cn(
        "mono inline-flex w-[3.6rem] shrink-0 items-center justify-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        METHOD_TONE[method] ?? "border-line bg-surface text-ink-subtle",
        className,
      )}
    >
      {method}
    </span>
  );
}

/** Colour the `{param}` segments so a templated path is readable at a glance. */
function PathText({ path, className }: { path: string; className?: string }) {
  return (
    <span className={cn("mono", className)}>
      {path.split(/(\{[^}]+\})/g).map((part, index) =>
        part.startsWith("{") ? (
          <span key={index} className="text-accent-strong">
            {part}
          </span>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </span>
  );
}

function slug(op: ApiOperation): string {
  return `${op.method.toLowerCase()}-${op.path.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`;
}

// --------------------------------------------------------------------------

function OperationCard({ op }: { op: ApiOperation }) {
  const [open, setOpen] = React.useState(false);
  const hasDetail = op.parameters.length > 0 || op.body !== null || op.responses.length > 0;

  return (
    <article
      id={slug(op)}
      data-reveal
      className="scroll-mt-28 overflow-hidden rounded-xl border border-line bg-surface transition-[border-color,box-shadow] duration-300 hover:border-line-strong"
    >
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        aria-expanded={open}
        className={cn(
          "flex w-full items-start gap-3 px-4 py-3.5 text-left sm:px-5",
          hasDetail && "cursor-pointer",
        )}
      >
        <MethodBadge method={op.method} className="mt-0.5" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <PathText path={op.path} className="truncate text-[13px] text-ink" />
          {op.summary ? (
            <span className="text-[12.5px] leading-snug text-ink-muted">{op.summary}</span>
          ) : null}
        </div>
        {hasDetail ? (
          <ChevronRight
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0 text-ink-subtle transition-transform duration-300 ease-out-quint",
              open && "rotate-90",
            )}
          />
        ) : null}
      </button>

      {/* Height-animated rather than conditionally mounted, so collapsing is
          as smooth as expanding. */}
      <div
        className={cn(
          "grid overflow-hidden transition-[grid-template-rows] duration-400 ease-out-quint",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="min-h-0">
          <div className="flex flex-col gap-5 border-t border-line px-4 py-4 sm:px-5">
            {op.description ? (
              <p className="text-[13px] leading-[1.7] text-ink-muted">{op.description}</p>
            ) : null}

            {op.parameters.length > 0 ? (
              <Detail title="Parameters">
                <div className="flex flex-col divide-y divide-line">
                  {op.parameters.map((param) => (
                    <div
                      key={`${param.location}-${param.name}`}
                      className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 first:pt-0 last:pb-0"
                    >
                      <code className="mono text-[12px] text-ink">{param.name}</code>
                      <span className="mono rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-ink-subtle">
                        {param.location}
                      </span>
                      <span className="mono text-[11.5px] text-accent-strong">{param.type}</span>
                      {param.required ? (
                        <span className="mono text-[10px] uppercase tracking-wider text-danger">
                          required
                        </span>
                      ) : null}
                      {param.description ? (
                        <span className="w-full text-[12px] leading-relaxed text-ink-muted">
                          {param.description}
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </Detail>
            ) : null}

            {op.body ? (
              <Detail title="Request body">
                <div className="flex items-center gap-2.5">
                  <code className="mono text-[12px] text-accent-strong">{op.body.type}</code>
                  <span className="mono text-[10px] uppercase tracking-wider text-ink-subtle">
                    application/json
                  </span>
                  {op.body.required ? (
                    <span className="mono text-[10px] uppercase tracking-wider text-danger">
                      required
                    </span>
                  ) : null}
                </div>
              </Detail>
            ) : null}

            {op.responses.length > 0 ? (
              <Detail title="Responses">
                <div className="flex flex-col gap-1.5">
                  {op.responses.map((response) => (
                    <div key={response.status} className="flex flex-wrap items-baseline gap-2.5">
                      <span
                        className={cn(
                          "mono rounded border px-1.5 py-0.5 text-[10px] font-semibold",
                          response.status.startsWith("2")
                            ? "border-warm/35 bg-warm-ghost text-warm"
                            : "border-line bg-surface-sunken text-ink-subtle",
                        )}
                      >
                        {response.status}
                      </span>
                      {response.type ? (
                        <code className="mono text-[11.5px] text-accent-strong">
                          {response.type}
                        </code>
                      ) : null}
                      <span className="text-[12px] text-ink-muted">{response.description}</span>
                    </div>
                  ))}
                </div>
              </Detail>
            ) : null}

            <div className="rounded-lg border border-line bg-[oklch(0.11_0_0)] p-3">
              <code className="code-block block whitespace-pre-wrap break-all text-[11.5px] text-[oklch(0.92_0_0)]">
                <span className="text-warm">curl</span> -X {op.method}{" "}
                <span className="text-accent-strong">
                  http://localhost:8000{op.path}
                </span>{" "}
                \{"\n"}  -H <span className="tok-string">&quot;X-API-Key: $SERPFLOW_API_KEY&quot;</span>
              </code>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function Detail({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="mono text-[10px] uppercase tracking-[0.16em] text-ink-subtle">{title}</h4>
      {children}
    </div>
  );
}

// --------------------------------------------------------------------------

export function ApiReferencePage() {
  const [query, setQuery] = React.useState("");
  const ref = React.useRef<HTMLDivElement>(null);
  useReveal(ref, { stagger: 0.02, y: 14 });

  const grouped = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    const match = (op: ApiOperation) =>
      !needle ||
      op.path.toLowerCase().includes(needle) ||
      op.summary.toLowerCase().includes(needle) ||
      op.method.toLowerCase() === needle;

    return API_GROUPS.map((group) => ({
      ...group,
      operations: API_OPERATIONS.filter((op) => op.tag === group.tag && match(op)),
    })).filter((group) => group.operations.length > 0);
  }, [query]);

  const total = grouped.reduce((sum, group) => sum + group.operations.length, 0);

  return (
    <div className="relative">
      <section className="relative overflow-hidden border-b border-line">
        <Atmosphere variant="band" />
        <div className="page-shell page-shell-wide relative flex flex-col gap-6 py-14 sm:py-18">
          <MonoLabel>api reference</MonoLabel>
          <h1 className="display max-w-3xl text-balance text-[clamp(2rem,4.6vw,3.2rem)] leading-[1.03]">
            Every endpoint, generated from the schema.
          </h1>
          <p className="max-w-2xl text-pretty text-[15px] leading-[1.75] text-ink-muted">
            {API_OPERATION_COUNT} operations across {API_PATH_COUNT} paths. This page is built from
            the OpenAPI document the server actually serves, so it cannot describe an endpoint that
            does not exist.
          </p>
          <div className="flex flex-wrap items-center gap-2.5">
            <Badge className="mono">v{API_VERSION}</Badge>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer noopener"
              className="link-underline mono text-[12px] text-accent-strong"
            >
              Interactive OpenAPI
            </a>
            <Link to="/docs/api/overview" className="link-underline mono text-[12px] text-ink-muted">
              Written guide
            </Link>
          </div>
        </div>
      </section>

      <div className="page-shell">
        <div className="grid gap-10 py-12 lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-12">
          {/* Group index. Sticky on desktop; a plain list above the content
              on narrow screens, where a sidebar would just push content down. */}
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <ScrollArea className="lg:max-h-[calc(100dvh-9rem)]">
              <nav className="flex flex-col gap-1 pr-3">
                {grouped.map((group) => (
                  <button
                    key={group.tag}
                    type="button"
                    onClick={() => {
                      const el = document.getElementById(`group-${group.tag}`);
                      if (el) scrollToElement(el);
                    }}
                    className="group flex items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-[13px] text-ink-muted transition-colors duration-300 hover:bg-surface hover:text-ink"
                  >
                    <span className="truncate">{group.title}</span>
                    <span className="mono shrink-0 text-[10.5px] text-ink-subtle">
                      {group.operations.length}
                    </span>
                  </button>
                ))}
              </nav>
            </ScrollArea>
          </aside>

          <div ref={ref} className="min-w-0">
            <div className="sticky top-16 z-20 -mx-1 mb-8 bg-[var(--color-ground)]/90 px-1 py-3 backdrop-blur">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Filter by path, summary or method"
                  aria-label="Filter endpoints"
                  className="pl-9 pr-9"
                />
                {query ? (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    aria-label="Clear filter"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-subtle transition-colors hover:text-ink"
                  >
                    <X className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
              {query ? (
                <p className="mono mt-2 px-1 text-[11.5px] text-ink-subtle">
                  {total} {total === 1 ? "operation" : "operations"}
                </p>
              ) : null}
            </div>

            {grouped.length === 0 ? (
              <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-line py-16 text-center">
                <Terminal className="h-6 w-6 text-ink-subtle" />
                <p className="text-[14px] text-ink">Nothing matches that filter.</p>
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="mono text-[12px] text-accent-strong"
                >
                  Clear it
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-14">
                {grouped.map((group) => (
                  <section key={group.tag} id={`group-${group.tag}`} className="scroll-mt-28">
                    <header className="mb-5 flex flex-col gap-1.5 border-b border-line pb-4">
                      <h2 className="text-[20px] font-semibold tracking-[-0.02em] text-ink">
                        {group.title}
                      </h2>
                      {group.blurb ? (
                        <p className="text-[13.5px] leading-relaxed text-ink-muted">
                          {group.blurb}
                        </p>
                      ) : null}
                    </header>
                    <div className="flex flex-col gap-2.5">
                      {group.operations.map((op) => (
                        <OperationCard key={op.id} op={op} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
