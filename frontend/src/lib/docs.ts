/**
 * The documentation tree, read from the repository's own `docs/` directory.
 *
 * `import.meta.glob` points at `../../docs`, so the published site renders the
 * same markdown that is committed - a page cannot describe a system the repo
 * does not. Each file is a separate dynamic import, so opening one doc does not
 * download the other fifty.
 */

const MODULES = import.meta.glob("../../../docs/**/*.md", {
  query: "?raw",
  import: "default",
}) as Record<string, () => Promise<string>>;

const ROOT_MODULES = import.meta.glob(
  ["../../../README.md", "../../../CONTRIBUTING.md", "../../../SECURITY.md", "../../../CHANGELOG.md"],
  { query: "?raw", import: "default" },
) as Record<string, () => Promise<string>>;

export type DocEntry = {
  /** Route slug, e.g. "architecture/planner". The index is "". */
  slug: string;
  title: string;
  /** Path relative to the repository root, for the "edit this page" link. */
  source: string;
  load: () => Promise<string>;
};

export type DocSection = {
  id: string;
  title: string;
  blurb: string;
  entries: DocEntry[];
};

/** Section order and prose. A file in an unlisted folder still resolves by URL. */
const SECTIONS: { id: string; title: string; blurb: string }[] = [
  { id: "", title: "Overview", blurb: "Start here." },
  {
    id: "architecture",
    title: "Architecture",
    blurb: "How the catalog, planner, cache and executor fit together.",
  },
  { id: "api", title: "API", blurb: "Endpoints, the streaming contract, worked requests." },
  { id: "database", title: "Database", blurb: "Schema, migrations, row-level security." },
  { id: "security", title: "Security", blurb: "Threat model, credentials, keys, secrets." },
  { id: "deployment", title: "Deployment", blurb: "Local, Docker and production." },
  { id: "operations", title: "Operations", blurb: "Bootstrap, email, observability, Kafka, Redis." },
  { id: "product", title: "Product", blurb: "What it is, the benchmark, the demo." },
  { id: "adr", title: "Decisions", blurb: "Architecture decision records." },
];

/** Hand-set titles where the filename alone reads poorly in a sidebar. */
const TITLE_OVERRIDES: Record<string, string> = {
  "": "Documentation",
  "architecture/overview": "Overview",
  "api/overview": "Overview",
  "database/rls": "Row-level security",
  "product/product-overview": "Product overview",
  adr: "Decision records",
  "readme:README": "Project README",
  "readme:CONTRIBUTING": "Contributing",
  "readme:SECURITY": "Security policy",
  "readme:CHANGELOG": "Changelog",
};

function titleFromSlug(slug: string): string {
  if (TITLE_OVERRIDES[slug]) return TITLE_OVERRIDES[slug];
  const last = slug.split("/").pop() ?? slug;
  // ADR filenames carry a number: "0008-coverage-before-price".
  const adr = last.match(/^(\d{4})-(.+)$/);
  const words = (adr ? adr[2] : last).replace(/-/g, " ");
  const cased = words.charAt(0).toUpperCase() + words.slice(1);
  return adr ? `${adr[1]}. ${cased}` : cased;
}

function slugFor(path: string): string {
  // "../../../docs/architecture/planner.md" -> "architecture/planner"
  const rel = path.replace("../../../docs/", "").replace(/\.md$/, "");
  if (rel === "README") return "";
  return rel.replace(/\/README$/, "");
}

const ENTRIES: DocEntry[] = Object.entries(MODULES)
  .map(([path, load]) => ({
    slug: slugFor(path),
    title: titleFromSlug(slugFor(path)),
    source: path.replace("../../../", ""),
    load,
  }))
  .sort((a, b) => a.slug.localeCompare(b.slug));

const ROOT_ENTRIES: DocEntry[] = Object.entries(ROOT_MODULES).map(([path, load]) => {
  const name = path.replace("../../../", "").replace(/\.md$/, "");
  return {
    slug: `readme:${name}`,
    title: TITLE_OVERRIDES[`readme:${name}`] ?? name,
    source: path.replace("../../../", ""),
    load,
  };
});

export const DOC_SECTIONS: DocSection[] = (() => {
  const sections: DocSection[] = [];

  for (const meta of SECTIONS) {
    const entries = ENTRIES.filter((entry) => {
      if (meta.id === "") return entry.slug === "";
      const [head, ...rest] = entry.slug.split("/");
      return head === meta.id && rest.length > 0;
    });

    // An index page at docs/<section>/README.md leads its own section.
    const index = ENTRIES.find((entry) => entry.slug === meta.id && meta.id !== "");
    const all = index ? [index, ...entries] : entries;
    if (all.length) sections.push({ ...meta, entries: all });
  }

  // Anything in a folder this file does not name still has to be reachable.
  const claimed = new Set(sections.flatMap((s) => s.entries.map((e) => e.slug)));
  const orphans = ENTRIES.filter((entry) => !claimed.has(entry.slug));
  if (orphans.length) {
    sections.push({ id: "other", title: "More", blurb: "", entries: orphans });
  }

  sections.push({
    id: "repository",
    title: "Repository",
    blurb: "The files at the root of the project.",
    entries: ROOT_ENTRIES,
  });

  return sections;
})();

/** Every entry in sidebar order, which is what prev/next walks. */
export const DOC_ORDER: DocEntry[] = DOC_SECTIONS.flatMap((section) => section.entries);

export function findDoc(slug: string): DocEntry | undefined {
  const normalised = slug.replace(/^\/+|\/+$/g, "");
  return DOC_ORDER.find((entry) => entry.slug === normalised);
}

export function neighbours(slug: string): { prev?: DocEntry; next?: DocEntry } {
  const index = DOC_ORDER.findIndex((entry) => entry.slug === slug);
  if (index < 0) return {};
  return { prev: DOC_ORDER[index - 1], next: DOC_ORDER[index + 1] };
}

export function sectionOf(slug: string): DocSection | undefined {
  return DOC_SECTIONS.find((section) => section.entries.some((entry) => entry.slug === slug));
}

/**
 * Rewrite a link from a markdown file into something the router can follow.
 *
 * The docs link each other with relative paths like `../database/rls.md`, which
 * are correct on GitHub and meaningless to a single-page app. This resolves
 * them against the current document and maps them onto `/docs/...`, so the same
 * markdown works in both places.
 */
export function resolveDocLink(href: string, fromSlug: string): string | null {
  if (/^[a-z]+:/i.test(href) || href.startsWith("//")) return null;
  if (href.startsWith("#")) return href;

  const base = fromSlug ? fromSlug.split("/").slice(0, -1) : [];
  const [pathPart, hash] = href.split("#");
  const segments = pathPart.split("/");
  const stack = [...base];

  for (const segment of segments) {
    if (!segment || segment === ".") continue;
    if (segment === "..") stack.pop();
    else stack.push(segment);
  }

  let target = stack.join("/");

  // Links that leave docs/ and point at source files stay external.
  if (target.startsWith("backend/") || target.startsWith("frontend/")) {
    return `https://github.com/serpflow/serpflow/blob/main/${target}`;
  }

  target = target.replace(/\.md$/, "");
  if (target === "LICENSE" || target.endsWith("/LICENSE")) {
    return "https://github.com/serpflow/serpflow/blob/main/LICENSE";
  }

  for (const name of ["README", "CONTRIBUTING", "SECURITY", "CHANGELOG"]) {
    if (target === name) return `/docs/readme:${name}${hash ? `#${hash}` : ""}`;
  }

  target = target.replace(/\/README$/, "").replace(/^docs\//, "");
  return `/docs/${target}${hash ? `#${hash}` : ""}`.replace("/docs//", "/docs/");
}
