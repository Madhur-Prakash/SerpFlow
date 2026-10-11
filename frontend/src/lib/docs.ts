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

const REPO_BLOB = "https://github.com/Madhur-Prakash/SerpFlow/blob/main/";
const ROOT_DOCS = ["README", "CONTRIBUTING", "SECURITY", "CHANGELOG"];

/** The file a slug was loaded from, relative to the repository root. */
function sourceOf(slug: string): string {
  if (slug.startsWith("readme:")) return `${slug.slice("readme:".length)}.md`;
  return findDoc(slug)?.source ?? `docs/${slug || "README"}.md`;
}

/**
 * Rewrite a link from a markdown file into something the router can follow.
 *
 * The docs link each other with relative paths like `../database/rls.md`, which
 * are correct on GitHub and meaningless to a single-page app. This resolves
 * them against the file the link is written in, in repository coordinates, and
 * maps pages under docs/ onto `/docs/...`, so the same markdown works in both
 * places. The file matters, not the slug: "adr" is `docs/adr/README.md`, so its
 * links resolve from `docs/adr/`, and `../README.md` from a section page is the
 * docs index, not the project README.
 */
export function resolveDocLink(href: string, fromSlug: string): string | null {
  if (/^[a-z]+:/i.test(href) || href.startsWith("//")) return null;
  if (href.startsWith("#")) return href;

  const [pathPart, hash] = href.split("#");
  const fragment = hash ? `#${hash}` : "";
  const stack = sourceOf(fromSlug).split("/").slice(0, -1);

  for (const segment of pathPart.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") stack.pop();
    else stack.push(segment);
  }

  const target = stack.join("/");

  // A page (or a section folder) under docs/ opens in the docs browser.
  const last = stack[stack.length - 1] ?? "";
  if (stack[0] === "docs" && (last.endsWith(".md") || !last.includes("."))) {
    const slug = target
      .replace(/^docs\/?/, "")
      .replace(/\.md$/, "")
      .replace(/(^|\/)README$/, "");
    return `/docs${slug ? `/${slug}` : ""}${fragment}`;
  }

  // The project's root markdown files are in the sidebar too.
  for (const name of ROOT_DOCS) {
    if (target === `${name}.md`) return `/docs/readme:${name}${fragment}`;
  }

  // Everything else is source: backend/, frontend/, sdk/, scripts/, docker/,
  // .env.example, the Makefile, the licence. Those open on GitHub.
  return `${REPO_BLOB}${target}${fragment}`;
}
