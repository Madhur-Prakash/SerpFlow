/**
 * A markdown renderer for this repository's documentation.
 *
 * Deliberately not a general-purpose parser. It covers exactly the subset the
 * docs use - headings, paragraphs, lists, tables, fenced code, blockquotes,
 * rules, and inline emphasis, code and links - which is why it is 300 lines
 * instead of a dependency plus a sanitizer.
 *
 * Nothing is rendered as raw HTML. Inline markup is parsed into React elements,
 * so a stray `<script>` in a document is text, not script, by construction
 * rather than by filtering.
 */

import { Check, Copy, Link2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { resolveDocLink } from "@/lib/docs";
import { cn } from "@/lib/utils";

export type Heading = { id: string; text: string; level: number };

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/`/g, "")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

// --------------------------------------------------------------------------
// Inline
// --------------------------------------------------------------------------

/**
 * Parse inline markdown into React nodes.
 *
 * One pass, longest-marker-first, so `**bold**` is not mistaken for two
 * italics. Code spans are matched before everything else because their
 * contents must stay literal.
 */
function inline(text: string, fromSlug: string, keyPrefix = ""): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern =
    /(`[^`]+`)|(\[[^\]]*\]\([^)\s]+(?:\s+"[^"]*")?\))|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\n]+\*)|(~~[^~]+~~)/g;

  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;

    if (token.startsWith("`")) {
      nodes.push(
        <code
          key={key}
          className="mono [overflow-wrap:anywhere] rounded border border-line bg-surface-sunken px-[0.35em] py-[0.12em] text-[0.88em] text-ink"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[")) {
      const link = token.match(/^\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)$/);
      if (link) {
        nodes.push(
          <MarkdownLink key={key} href={link[2]} fromSlug={fromSlug}>
            {inline(link[1], fromSlug, key)}
          </MarkdownLink>,
        );
      } else {
        nodes.push(token);
      }
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(
        <strong key={key} className="font-semibold text-ink">
          {inline(token.slice(2, -2), fromSlug, key)}
        </strong>,
      );
    } else if (token.startsWith("~~")) {
      nodes.push(
        <del key={key} className="text-ink-subtle">
          {inline(token.slice(2, -2), fromSlug, key)}
        </del>,
      );
    } else {
      nodes.push(
        <em key={key} className="italic">
          {inline(token.slice(1, -1), fromSlug, key)}
        </em>,
      );
    }
    last = pattern.lastIndex;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function MarkdownLink({
  href,
  fromSlug,
  children,
}: {
  href: string;
  fromSlug: string;
  children: React.ReactNode;
}) {
  const resolved = resolveDocLink(href, fromSlug);

  if (resolved === null || resolved.startsWith("http")) {
    return (
      <a
        href={resolved ?? href}
        target="_blank"
        rel="noreferrer noopener"
        className="link-underline [overflow-wrap:anywhere] text-accent-strong transition-colors hover:text-accent"
      >
        {children}
      </a>
    );
  }
  if (resolved.startsWith("#")) {
    return (
      <a href={resolved} className="link-underline text-accent-strong">
        {children}
      </a>
    );
  }
  return (
    <Link to={resolved} className="link-underline text-accent-strong transition-colors hover:text-accent">
      {children}
    </Link>
  );
}

// --------------------------------------------------------------------------
// Code
// --------------------------------------------------------------------------

/**
 * Minimal highlighting for the languages the docs use.
 *
 * Comment and string first, because a keyword inside either is not a keyword.
 * The result is spans, not HTML, so nothing escapes.
 */
function highlight(code: string, lang: string): React.ReactNode[] {
  const rules: { pattern: RegExp; cls: string }[] = [];

  if (["bash", "sh", "shell", "console"].includes(lang)) {
    rules.push(
      { pattern: /#[^\n]*/g, cls: "tok-comment" },
      { pattern: /"[^"\n]*"|'[^'\n]*'/g, cls: "tok-string" },
      { pattern: /\$\w+|\$\{[^}]+\}/g, cls: "tok-key" },
    );
  } else if (["json", "jsonc"].includes(lang)) {
    rules.push(
      { pattern: /\/\/[^\n]*/g, cls: "tok-comment" },
      { pattern: /"(?:[^"\\]|\\.)*"(?=\s*:)/g, cls: "tok-key" },
      { pattern: /"(?:[^"\\]|\\.)*"/g, cls: "tok-string" },
      { pattern: /\b-?\d+(?:\.\d+)?\b/g, cls: "tok-number" },
      { pattern: /\b(?:true|false|null)\b/g, cls: "tok-literal" },
    );
  } else if (["python", "py"].includes(lang)) {
    rules.push(
      { pattern: /#[^\n]*/g, cls: "tok-comment" },
      { pattern: /"""[\s\S]*?"""|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: "tok-string" },
      {
        pattern:
          /\b(?:async|await|def|class|return|import|from|if|elif|else|for|while|try|except|finally|with|as|raise|yield|lambda|not|and|or|in|is|None|True|False|self)\b/g,
        cls: "tok-key",
      },
      { pattern: /\b\d+(?:\.\d+)?\b/g, cls: "tok-number" },
    );
  } else if (["sql"].includes(lang)) {
    rules.push(
      { pattern: /--[^\n]*/g, cls: "tok-comment" },
      { pattern: /'(?:[^'\\]|\\.)*'/g, cls: "tok-string" },
      {
        pattern:
          /\b(?:SELECT|FROM|WHERE|CREATE|TABLE|INDEX|USING|ALTER|POLICY|GRANT|ON|AND|OR|NOT|NULL|UNIQUE|RETURNS|BEGIN|END|IF|THEN|RAISE|EXCEPTION|TRIGGER|FUNCTION|EXTENSION|UNION|ALL|ORDER|BY|SET|ROW|LEVEL|SECURITY|ENABLE|COUNT|INSERT|UPDATE|DELETE|ROLE|LOGIN|PASSWORD|SCHEMA|USAGE|TO|AS)\b/gi,
        cls: "tok-key",
      },
      { pattern: /\b\d+\b/g, cls: "tok-number" },
    );
  } else if (["typescript", "ts", "javascript", "js", "tsx"].includes(lang)) {
    rules.push(
      { pattern: /\/\/[^\n]*/g, cls: "tok-comment" },
      { pattern: /`(?:[^`\\]|\\.)*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: "tok-string" },
      {
        pattern:
          /\b(?:const|let|var|function|return|import|from|export|async|await|for|of|in|if|else|try|catch|finally|new|class|extends|type|interface|null|undefined|true|false)\b/g,
        cls: "tok-key",
      },
      { pattern: /\b\d+(?:\.\d+)?\b/g, cls: "tok-number" },
    );
  } else if (["yaml", "yml"].includes(lang)) {
    rules.push(
      { pattern: /#[^\n]*/g, cls: "tok-comment" },
      { pattern: /^[ \t-]*[\w.-]+(?=:)/gm, cls: "tok-key" },
      { pattern: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: "tok-string" },
      { pattern: /\b(?:true|false|null)\b/g, cls: "tok-literal" },
    );
  } else if (["http", "nginx", "dockerfile"].includes(lang)) {
    rules.push(
      { pattern: /#[^\n]*/g, cls: "tok-comment" },
      { pattern: /"(?:[^"\\]|\\.)*"/g, cls: "tok-string" },
      {
        pattern: /^(?:GET|POST|PUT|PATCH|DELETE|FROM|RUN|COPY|CMD|ENV|LABEL|EXPOSE|USER|WORKDIR)\b/gm,
        cls: "tok-key",
      },
    );
  }

  if (!rules.length) return [code];

  // Claim ranges in rule order; an already-claimed span is never re-matched,
  // which is what keeps a keyword inside a string from being re-coloured.
  type Span = { start: number; end: number; cls: string };
  const spans: Span[] = [];
  const taken = (start: number, end: number) =>
    spans.some((s) => start < s.end && end > s.start);

  for (const rule of rules) {
    rule.pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = rule.pattern.exec(code)) !== null) {
      if (match[0].length === 0) {
        rule.pattern.lastIndex += 1;
        continue;
      }
      const start = match.index;
      const end = start + match[0].length;
      if (!taken(start, end)) spans.push({ start, end, cls: rule.cls });
    }
  }

  spans.sort((a, b) => a.start - b.start);
  const out: React.ReactNode[] = [];
  let cursor = 0;
  spans.forEach((span, index) => {
    if (span.start > cursor) out.push(code.slice(cursor, span.start));
    out.push(
      <span key={index} className={span.cls}>
        {code.slice(span.start, span.end)}
      </span>,
    );
    cursor = span.end;
  });
  if (cursor < code.length) out.push(code.slice(cursor));
  return out;
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = React.useState(false);

  const copy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be denied; the code is selectable either way.
    }
  }, [code]);

  return (
    <div className="group/code relative my-5 overflow-hidden rounded-xl border border-line bg-[oklch(0.125_0.006_265)]">
      <div className="flex items-center justify-between border-b border-line/60 px-4 py-2">
        <span className="mono text-[10.5px] uppercase tracking-[0.14em] text-ink-subtle">
          {lang || "text"}
        </span>
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? "Copied" : "Copy code"}
          className="inline-flex items-center gap-1.5 rounded px-1.5 py-1 text-[11px] text-ink-subtle opacity-0 transition-[opacity,color] duration-300 hover:text-ink focus-visible:opacity-100 group-hover/code:opacity-100"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-warm" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="code-block overflow-x-auto p-4 text-[oklch(0.9_0.004_265)]">
        <code>{highlight(code, lang)}</code>
      </pre>
    </div>
  );
}

// --------------------------------------------------------------------------
// HTML
// --------------------------------------------------------------------------

/**
 * The README files open with a centred block of raw HTML - a heading, badge
 * images and a row of links - because that is the only way to centre anything
 * on GitHub. Markdown has no syntax for it, so without this the whole header
 * renders as literal angle brackets.
 *
 * This parses a deliberately small subset into React elements. Nothing is ever
 * passed to `dangerouslySetInnerHTML`: a tag outside the whitelist renders as
 * its text content, and an attribute outside the whitelist is dropped, so the
 * output cannot contain markup this file did not construct.
 */
const ALLOWED_TAGS = new Set([
  "div", "p", "span", "br", "hr",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "a", "img", "picture", "source",
  "strong", "b", "em", "i", "code", "sub", "sup", "small",
  "ul", "ol", "li", "blockquote",
  "table", "thead", "tbody", "tr", "th", "td",
  "details", "summary",
]);

const VOID_TAGS = new Set(["br", "hr", "img", "source", "input", "meta", "link"]);
const ALLOWED_ATTRS = new Set(["href", "src", "alt", "align", "title", "width", "height"]);

type HtmlNode =
  | { type: "text"; value: string }
  | { type: "element"; tag: string; attrs: Record<string, string>; children: HtmlNode[] };

function decodeEntities(text: string): string {
  const named: Record<string, string> = {
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: "\u00a0",
    middot: "\u00b7", bull: "\u2022", copy: "\u00a9", mdash: "\u2014", ndash: "\u2013",
    hellip: "\u2026", times: "\u00d7", laquo: "\u00ab", raquo: "\u00bb",
  };
  return text.replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (whole, code: string) => {
    if (code[0] === "#") {
      const value = code[1] === "x" || code[1] === "X"
        ? parseInt(code.slice(2), 16)
        : parseInt(code.slice(1), 10);
      return Number.isFinite(value) ? String.fromCodePoint(value) : whole;
    }
    return named[code.toLowerCase()] ?? whole;
  });
}

function parseAttrs(raw: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  const pattern = /([a-zA-Z-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(raw)) !== null) {
    const name = match[1].toLowerCase();
    if (!ALLOWED_ATTRS.has(name)) continue;
    attrs[name] = decodeEntities(match[2] ?? match[3] ?? match[4] ?? "");
  }
  return attrs;
}

/** Build a node tree from a run of HTML. Unbalanced tags are tolerated. */
function parseHtml(source: string): HtmlNode[] {
  const root: HtmlNode = { type: "element", tag: "#root", attrs: {}, children: [] };
  const stack: HtmlNode[] = [root];
  const pattern = /<\/?([a-zA-Z][a-zA-Z0-9]*)((?:\s+[^<>]*?)?)\/?>/g;

  let cursor = 0;
  let match: RegExpExecArray | null;

  const push = (node: HtmlNode) => {
    const parent = stack[stack.length - 1];
    if (parent.type === "element") parent.children.push(node);
  };

  while ((match = pattern.exec(source)) !== null) {
    if (match.index > cursor) {
      const text = source.slice(cursor, match.index);
      if (text.trim()) push({ type: "text", value: decodeEntities(text) });
    }
    cursor = pattern.lastIndex;

    const tag = match[1].toLowerCase();
    const closing = match[0][1] === "/";
    const selfClosing = match[0].endsWith("/>") || VOID_TAGS.has(tag);

    if (closing) {
      // Unwind to the matching open tag, if there is one.
      for (let i = stack.length - 1; i > 0; i -= 1) {
        const node = stack[i];
        if (node.type === "element" && node.tag === tag) {
          stack.length = i;
          break;
        }
      }
      continue;
    }

    const node: HtmlNode = { type: "element", tag, attrs: parseAttrs(match[2] || ""), children: [] };
    push(node);
    if (!selfClosing) stack.push(node);
  }

  if (cursor < source.length) {
    const text = source.slice(cursor);
    if (text.trim()) push({ type: "text", value: decodeEntities(text) });
  }

  return (root as Extract<HtmlNode, { type: "element" }>).children;
}

const HTML_HEADING: Record<string, string> = {
  h1: "mt-0 mb-4 text-[clamp(1.9rem,3.4vw,2.6rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-ink",
  h2: "mt-10 mb-3 scroll-mt-28 text-[1.45rem] font-semibold tracking-[-0.02em] text-ink",
  h3: "mt-8 mb-2.5 scroll-mt-28 text-[1.12rem] font-semibold text-ink",
  h4: "mt-6 mb-2 text-[0.98rem] font-semibold text-ink",
  h5: "mt-5 mb-2 text-[0.92rem] font-semibold text-ink-muted",
  h6: "mt-4 mb-2 text-[0.88rem] font-semibold text-ink-subtle",
};

function renderHtmlNodes(nodes: HtmlNode[], slug: string, keyPrefix: string): React.ReactNode[] {
  return nodes.map((node, index) => {
    const key = `${keyPrefix}-${index}`;

    if (node.type === "text") return node.value;

    const { tag, attrs, children } = node;
    if (!ALLOWED_TAGS.has(tag)) {
      // Not markup we understand: keep whatever it was wrapping.
      return <React.Fragment key={key}>{renderHtmlNodes(children, slug, key)}</React.Fragment>;
    }

    const centred = attrs.align === "center";
    const inner = renderHtmlNodes(children, slug, key);

    switch (tag) {
      case "br":
        return <br key={key} />;
      case "hr":
        return <hr key={key} className="my-8 border-line" />;

      case "img": {
        const src = attrs.src || "";
        // Only http(s) sources; a data: or javascript: URL has no business here.
        if (!/^https?:\/\//i.test(src)) return null;
        return (
          <img
            key={key}
            src={src}
            alt={attrs.alt || ""}
            loading="lazy"
            className="inline-block h-5 max-w-full align-middle"
          />
        );
      }

      case "a": {
        const href = attrs.href || "";
        if (!href || /^javascript:/i.test(href)) {
          return <React.Fragment key={key}>{inner}</React.Fragment>;
        }
        return (
          <MarkdownLink key={key} href={href} fromSlug={slug}>
            {inner}
          </MarkdownLink>
        );
      }

      case "h1":
      case "h2":
      case "h3":
      case "h4":
      case "h5":
      case "h6": {
        const Tag = tag as "h1";
        const text = nodeText(node);
        return (
          <Tag key={key} id={slugify(text)} className={cn(HTML_HEADING[tag], centred && "text-center")}>
            {inner}
          </Tag>
        );
      }

      case "p":
        return (
          <p
            key={key}
            className={cn("my-3 text-pretty [overflow-wrap:anywhere]", centred && "text-center")}
          >
            {inner}
          </p>
        );

      case "div":
        return (
          <div key={key} className={cn(centred && "text-center [&_p]:justify-center")}>
            {inner}
          </div>
        );

      case "sub":
      case "small":
        return (
          <span key={key} className="text-[0.86em] text-ink-subtle">
            {inner}
          </span>
        );

      case "sup":
        return <sup key={key}>{inner}</sup>;

      case "strong":
      case "b":
        return (
          <strong key={key} className="font-semibold text-ink">
            {inner}
          </strong>
        );

      case "em":
      case "i":
        return (
          <em key={key} className="italic">
            {inner}
          </em>
        );

      case "code":
        return (
          <code
            key={key}
            className="mono [overflow-wrap:anywhere] rounded border border-line bg-surface-sunken px-[0.35em] py-[0.12em] text-[0.88em] text-ink"
          >
            {inner}
          </code>
        );

      case "details":
        return (
          <details key={key} className="my-4 rounded-xl border border-line bg-surface px-4 py-3">
            {inner}
          </details>
        );

      case "summary":
        return (
          <summary key={key} className="cursor-pointer text-[14px] font-medium text-ink">
            {inner}
          </summary>
        );

      case "ul":
        return (
          <ul key={key} className="my-3 flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-subtle">
            {inner}
          </ul>
        );

      case "ol":
        return (
          <ol key={key} className="my-3 flex list-decimal flex-col gap-1.5 pl-5 marker:text-ink-subtle">
            {inner}
          </ol>
        );

      case "li":
        return <li key={key}>{inner}</li>;

      case "blockquote":
        return (
          <blockquote
            key={key}
            className="my-4 rounded-r-lg border-l-2 border-accent bg-accent-ghost/35 py-2.5 pl-4 pr-4"
          >
            {inner}
          </blockquote>
        );

      case "table":
        return (
          <div key={key} className="my-5 overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full border-collapse text-left text-[13.5px]">{inner}</table>
          </div>
        );
      case "thead":
        return <thead key={key}>{inner}</thead>;
      case "tbody":
        return <tbody key={key}>{inner}</tbody>;
      case "tr":
        return (
          <tr key={key} className="border-b border-line last:border-0">
            {inner}
          </tr>
        );
      case "th":
        return (
          <th key={key} className="mono px-4 py-2.5 text-[11px] uppercase tracking-[0.1em] text-ink-subtle">
            {inner}
          </th>
        );
      case "td":
        return (
          <td key={key} className="px-4 py-2.5 align-top text-ink-muted">
            {inner}
          </td>
        );

      case "picture":
      case "source":
      case "span":
      default:
        return <span key={key}>{inner}</span>;
    }
  });
}

function nodeText(node: HtmlNode): string {
  if (node.type === "text") return node.value;
  return node.children.map(nodeText).join("");
}

/** Headings inside an HTML block, so the on-page contents still finds them. */
function htmlHeadings(source: string): Heading[] {
  const out: Heading[] = [];
  const walk = (nodes: HtmlNode[]) => {
    for (const node of nodes) {
      if (node.type !== "element") continue;
      if (/^h[1-6]$/.test(node.tag)) {
        const level = Number(node.tag[1]);
        const text = nodeText(node).trim();
        if (text && (level === 2 || level === 3)) {
          out.push({ id: slugify(text), text, level });
        }
      }
      walk(node.children);
    }
  };
  walk(parseHtml(source));
  return out;
}

// --------------------------------------------------------------------------
// Block
// --------------------------------------------------------------------------

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; lang: string; code: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "table"; head: string[]; align: string[]; rows: string[][] }
  | { kind: "html"; source: string }
  | { kind: "rule" };

function splitRow(line: string): string[] {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function parse(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    // A run of raw HTML. Collected whole, because its tags span blank lines:
    // the README headers are a <div align="center"> wrapping several
    // paragraphs. Depth counting is what tells us where the run ends.
    const htmlStart = line.match(/^\s*<([a-zA-Z][a-zA-Z0-9]*)\b/);
    if (htmlStart && ALLOWED_TAGS.has(htmlStart[1].toLowerCase())) {
      const body: string[] = [];
      let depth = 0;
      while (i < lines.length) {
        const current = lines[i];
        body.push(current);
        i += 1;
        for (const tagMatch of current.matchAll(/<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(\/?)>/g)) {
          const tag = tagMatch[2].toLowerCase();
          if (VOID_TAGS.has(tag) || tagMatch[3] === "/") continue;
          depth += tagMatch[1] === "/" ? -1 : 1;
        }
        if (depth <= 0) break;
      }
      blocks.push({ kind: "html", source: body.join("\n") });
      continue;
    }

    // Fenced code. The closing fence has to match the opening one's length so
    // a ``` inside a ```` block does not end it early.
    const fence = line.match(/^(\s*)(`{3,}|~{3,})\s*(\S*)/);
    if (fence) {
      const marker = fence[2];
      const lang = (fence[3] || "").toLowerCase();
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(marker.slice(0, 3))) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ kind: "code", lang, code: body.join("\n").replace(/\n+$/, "") });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2].trim() });
      i += 1;
      continue;
    }

    if (/^\s*(?:---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
      i += 1;
      continue;
    }

    // Table: a header row followed by a delimiter row.
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      const head = splitRow(line);
      const align = splitRow(lines[i + 1]).map((cell) =>
        cell.endsWith(":") ? (cell.startsWith(":") ? "center" : "right") : "left",
      );
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", head, align, rows });
      continue;
    }

    const bullet = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (bullet) {
      const ordered = /\d/.test(bullet[2]);
      const items: string[] = [];
      while (i < lines.length) {
        const item = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (!item) {
          // A plain indented line continues the previous item.
          if (items.length && /^\s{2,}\S/.test(lines[i]) && lines[i].trim()) {
            items[items.length - 1] += " " + lines[i].trim();
            i += 1;
            continue;
          }
          break;
        }
        items.push(item[3].trim());
        i += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    if (line.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        body.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "quote", text: body.join(" ").trim() });
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|>|\s*```|\s*~~~)/.test(lines[i])) {
      const next = lines[i];
      if (/^(\s*)([-*+]|\d+[.)])\s+/.test(next) && paragraph.length) break;
      paragraph.push(next.trim());
      i += 1;
      if (i < lines.length && lines[i].includes("|") && /^\s*\|?[\s:|-]+\|/.test(lines[i])) break;
    }
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    else i += 1;
  }

  return blocks;
}

/** Headings, for the on-page table of contents. */
export function extractHeadings(markdown: string): Heading[] {
  return parse(markdown).flatMap((block) => {
    if (block.kind === "html") return htmlHeadings(block.source);
    if (block.kind !== "heading") return [];
    if (block.level !== 2 && block.level !== 3) return [];
    return [
      {
        id: slugify(block.text),
        text: block.text.replace(/`/g, ""),
        level: block.level,
      },
    ];
  });
}

const HEADING_CLASS: Record<number, string> = {
  1: "mt-0 mb-5 text-[clamp(1.9rem,3.4vw,2.6rem)] font-semibold leading-[1.1] tracking-[-0.03em]",
  2: "mt-12 mb-4 scroll-mt-28 text-[1.45rem] font-semibold leading-tight tracking-[-0.02em]",
  3: "mt-9 mb-3 scroll-mt-28 text-[1.12rem] font-semibold leading-snug",
  4: "mt-7 mb-2.5 scroll-mt-28 text-[0.98rem] font-semibold",
  5: "mt-6 mb-2 text-[0.92rem] font-semibold text-ink-muted",
  6: "mt-5 mb-2 text-[0.88rem] font-semibold text-ink-subtle",
};

export function Markdown({ source, slug }: { source: string; slug: string }) {
  const blocks = React.useMemo(() => parse(source), [source]);

  return (
    <div className="min-w-0 text-[15px] leading-[1.78] text-ink-muted">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "heading": {
            const id = slugify(block.text);
            const Tag = `h${Math.min(6, block.level)}` as "h1";
            return (
              <Tag key={index} id={id} className={cn("group text-ink", HEADING_CLASS[block.level])}>
                {inline(block.text, slug, `h${index}`)}
                {block.level > 1 ? (
                  <a
                    href={`#${id}`}
                    aria-label={`Link to ${block.text}`}
                    className="ml-2 inline-flex align-middle text-ink-subtle opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                  >
                    <Link2 className="h-3.5 w-3.5" />
                  </a>
                ) : null}
              </Tag>
            );
          }

          case "paragraph":
            return (
              <p key={index} className="my-4 text-pretty [overflow-wrap:anywhere]">
                {inline(block.text, slug, `p${index}`)}
              </p>
            );

          case "code":
            return <CodeBlock key={index} code={block.code} lang={block.lang} />;

          case "list": {
            const Tag = block.ordered ? "ol" : "ul";
            return (
              <Tag
                key={index}
                className={cn(
                  "my-4 flex flex-col gap-2 pl-5",
                  block.ordered ? "list-decimal" : "list-disc",
                  "marker:text-ink-subtle",
                )}
              >
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="pl-1 text-pretty [overflow-wrap:anywhere]">
                    {inline(item, slug, `l${index}-${itemIndex}`)}
                  </li>
                ))}
              </Tag>
            );
          }

          case "quote":
            return (
              <blockquote
                key={index}
                className="my-5 rounded-r-lg border-l-2 border-accent bg-accent-ghost/35 py-3 pl-4 pr-4 text-ink-muted"
              >
                {inline(block.text, slug, `q${index}`)}
              </blockquote>
            );

          case "table":
            return (
              <div
                key={index}
                className="my-6 overflow-x-auto rounded-xl border border-line bg-surface"
              >
                <table className="w-full border-collapse text-left text-[13.5px]">
                  <thead>
                    <tr className="border-b border-line bg-surface-sunken">
                      {block.head.map((cell, cellIndex) => (
                        <th
                          key={cellIndex}
                          style={{ textAlign: block.align[cellIndex] as "left" }}
                          className="mono px-4 py-2.5 text-[11px] uppercase tracking-[0.1em] text-ink-subtle"
                        >
                          {inline(cell, slug, `th${index}-${cellIndex}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rowIndex) => (
                      <tr
                        key={rowIndex}
                        className="border-b border-line transition-colors duration-200 last:border-0 hover:bg-surface-sunken"
                      >
                        {row.map((cell, cellIndex) => (
                          <td
                            key={cellIndex}
                            style={{ textAlign: block.align[cellIndex] as "left" }}
                            className="px-4 py-2.5 align-top text-ink-muted"
                          >
                            {inline(cell, slug, `td${index}-${rowIndex}-${cellIndex}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );

          case "html":
            return (
              <React.Fragment key={index}>
                {renderHtmlNodes(parseHtml(block.source), slug, `html${index}`)}
              </React.Fragment>
            );

          case "rule":
            return <hr key={index} className="my-10 border-line" />;

          default:
            return null;
        }
      })}
    </div>
  );
}
