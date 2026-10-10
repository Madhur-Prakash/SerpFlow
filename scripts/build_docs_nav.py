"""Give every page in docs/ the same badge header, breadcrumb and footer.

    python scripts/build_docs_nav.py           # rewrite pages in place
    python scripts/build_docs_nav.py --check   # exit 1 if any page is stale

Directly under its title, each page gets:

  * a row of shields.io badges: the section, facts about the page's subject,
    the stack it covers, the main source file and an estimated reading time
  * a breadcrumb back to the index, with the page's place in the reading order

and, at the very end, a previous / index / next table in reading order, so the
whole set reads end to end.

Both blocks are generated: running this again replaces them rather than
appending, so it is safe after every edit. The breadcrumb and footer are plain
markdown links, which `make docs-check` verifies. The badges are an HTML block
because the docs browser in the app has no inline-image syntax.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Reading order, start to finish. Every page in docs/ except the index.
ORDER = [
    "product/product-overview.md",
    "product/demo.md",
    "product/execution-modes.md",
    "product/benchmark.md",
    "deployment/installation.md",
    "deployment/local.md",
    "deployment/docker.md",
    "deployment/deployment-guide.md",
    "deployment/production.md",
    "architecture/overview.md",
    "architecture/catalog.md",
    "architecture/planner.md",
    "architecture/marginal-replanning.md",
    "architecture/caching.md",
    "architecture/executor.md",
    "architecture/backend.md",
    "architecture/frontend.md",
    "architecture/web.md",
    "api/overview.md",
    "api/streaming.md",
    "api/examples.md",
    "database/schema.md",
    "database/migrations.md",
    "database/rls.md",
    "security/threat-model.md",
    "security/byok.md",
    "security/credentials.md",
    "security/api-keys.md",
    "security/secrets.md",
    "operations/bootstrap.md",
    "operations/email.md",
    "operations/observability.md",
    "operations/kafka.md",
    "operations/redis.md",
    "operations/troubleshooting.md",
    "adr/README.md",
    *[f"adr/{p.name}" for p in sorted((DOCS / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))],
]

# Section id -> (breadcrumb label, anchor on the index page, badge colour)
SECTIONS = {
    "product": ("Product", "product", "2F6BFF"),
    "deployment": ("Deployment", "deployment", "2496ED"),
    "architecture": ("Architecture", "architecture", "2F6BFF"),
    "api": ("API", "api", "009688"),
    "database": ("Database", "database", "4169E1"),
    "security": ("Security", "security", "6E40C9"),
    "operations": ("Operations", "operations", "E6522C"),
    "adr": ("Decisions", "decisions", "555555"),
}

# The stack, as badges: label, message, colour, simple-icons logo, logo colour.
TECH = {
    "python": ("Python", "3.13", "3776AB", "python", "white"),
    "uv": ("uv", "venv", "DE5FE9", "uv", "white"),
    "fastapi": ("FastAPI", "0.118", "009688", "fastapi", "white"),
    "pydantic": ("Pydantic", "v2", "E92063", "pydantic", "white"),
    "sqlalchemy": ("SQLAlchemy", "2", "D71F00", "sqlalchemy", "white"),
    "alembic": ("Alembic", "migrations", "6BA81E", None, None),
    "postgres": ("PostgreSQL", "17 + pgvector", "4169E1", "postgresql", "white"),
    "redis": ("Redis", "7", "DC382D", "redis", "white"),
    "kafka": ("Kafka", "4.0 KRaft", "231F20", "apachekafka", "white"),
    "react": ("React", "19", "61DAFB", "react", "black"),
    "typescript": ("TypeScript", "5.9", "3178C6", "typescript", "white"),
    "vite": ("Vite", "6", "646CFF", "vite", "white"),
    "tailwind": ("Tailwind CSS", "4", "06B6D4", "tailwindcss", "white"),
    "gsap": ("GSAP", "ScrollTrigger", "88CE02", "greensock", "black"),
    "docker": ("Docker", "Compose", "2496ED", "docker", "white"),
    "nginx": ("nginx", "1.27", "009639", "nginx", "white"),
    "node": ("Node", "22", "5FA04E", "nodedotjs", "white"),
    "prometheus": ("Prometheus", "metrics", "E6522C", "prometheus", "white"),
    "grafana": ("Grafana", "dashboards", "F46800", "grafana", "white"),
    "otel": ("OpenTelemetry", "traces", "425CC7", "opentelemetry", "white"),
    "openapi": ("OpenAPI", "3.1", "6BA539", "openapiinitiative", "white"),
    "sse": ("SSE", "streaming", "555555", None, None),
    "jwt": ("JWT", "HS256", "000000", "jsonwebtokens", "white"),
    "argon2": ("Argon2id", "passwords", "6E40C9", None, None),
    "hmac": ("HMAC", "SHA-256", "6E40C9", None, None),
    "aes": ("AES", "256-GCM", "6E40C9", None, None),
    "gmail": ("Gmail", "API", "EA4335", "gmail", "white"),
    "serpapi": ("SerpApi", "54 engines", "2F6BFF", None, None),
    "groq": ("Groq", "BYOK", "F55036", None, None),
    "mcp": ("MCP", "server", "555555", None, None),
    "pytest": ("pytest", "216 passing", "0A9EDC", "pytest", "white"),
    "minio": ("MinIO", "S3", "C72E49", "minio", "white"),
    "yaml": ("YAML", "catalog v1.0.0", "CB171E", "yaml", "white"),
}

# Per page: facts about its subject (label, message, colour) and its stack.
# Every number here is checked against the code, not copied from prose.
PAGES: dict[str, dict] = {
    "product/product-overview.md": {"facts": [("thesis", "marginal-cost replanning", "2F6BFF")], "tech": ["serpapi"]},
    "product/demo.md": {"facts": [("make demo", "PROVEN", "3fcf8e"), ("naive", "101 to 0 credits", "3fcf8e")], "tech": ["python"]},
    "product/execution-modes.md": {"facts": [("modes", "live · record · replay", "2F6BFF"), ("test keys", "always mock", "3fcf8e")], "tech": ["serpapi"]},
    "product/benchmark.md": {"facts": [("routing accuracy", "38.3%", "3fcf8e"), ("tasks", "120", "2F6BFF")], "tech": ["groq"]},
    "deployment/installation.md": {"facts": [("API keys", "not required", "3fcf8e"), ("paths", "dev · docker", "2496ED")], "tech": ["python", "uv", "node", "docker"]},
    "deployment/local.md": {"facts": [("API keys", "not required", "3fcf8e")], "tech": ["python", "uv", "node", "docker"]},
    "deployment/docker.md": {"facts": [("services", "8", "2496ED")], "tech": ["docker", "nginx", "postgres", "redis", "kafka"]},
    "deployment/deployment-guide.md": {"facts": [("steps", "15", "2496ED"), ("TLS", "Caddy", "1F88C0")], "tech": ["docker", "nginx", "postgres", "prometheus"]},
    "deployment/production.md": {"facts": [("bootstrap", "advisory-locked", "3fcf8e")], "tech": ["docker", "postgres", "otel"]},
    "architecture/overview.md": {"facts": [], "tech": ["fastapi", "postgres", "redis", "kafka", "react"]},
    "architecture/catalog.md": {"facts": [("engines", "54", "2F6BFF"), ("dependency edges", "30", "2F6BFF"), ("substitutes", "69", "2F6BFF"), ("capability tags", "28", "2F6BFF")], "tech": ["yaml"]},
    "architecture/planner.md": {"facts": [("stages", "4", "2F6BFF")], "tech": ["python", "groq"]},
    "architecture/marginal-replanning.md": {"facts": [("thesis", "marginal cost", "3fcf8e")], "tech": ["python"]},
    "architecture/caching.md": {"facts": [("layers", "4", "2F6BFF")], "tech": ["redis", "postgres"]},
    "architecture/executor.md": {"facts": [("cache layers", "exact · semantic · archive · live", "2F6BFF")], "tech": ["python", "serpapi"]},
    "architecture/backend.md": {"facts": [], "tech": ["python", "fastapi", "sqlalchemy", "pydantic"]},
    "architecture/frontend.md": {"facts": [], "tech": ["react", "typescript", "vite", "tailwind"]},
    "architecture/web.md": {"facts": [], "tech": ["react", "gsap", "tailwind"]},
    "api/overview.md": {"facts": [("operations", "85", "009688"), ("paths", "74", "009688")], "tech": ["fastapi", "openapi", "jwt"]},
    "api/streaming.md": {"facts": [("stages", "11", "009688")], "tech": ["sse", "fastapi"]},
    "api/examples.md": {"facts": [], "tech": ["python", "typescript", "mcp"]},
    "database/schema.md": {"facts": [("tables", "33", "4169E1")], "tech": ["postgres", "sqlalchemy"]},
    "database/migrations.md": {"facts": [("revisions", "4", "4169E1")], "tech": ["alembic", "postgres"]},
    "database/rls.md": {"facts": [("RLS tables", "24", "4169E1")], "tech": ["postgres"]},
    "security/threat-model.md": {"facts": [], "tech": ["argon2", "hmac", "aes"]},
    "security/byok.md": {"facts": [("platform keys", "none", "3fcf8e")], "tech": ["serpapi", "groq"]},
    "security/credentials.md": {"facts": [], "tech": ["aes"]},
    "security/api-keys.md": {"facts": [("roles", "5 built-in + custom", "6E40C9")], "tech": ["hmac", "argon2"]},
    "security/secrets.md": {"facts": [], "tech": ["jwt", "aes"]},
    "operations/bootstrap.md": {"facts": [("bootstrap", "advisory-locked", "3fcf8e")], "tech": ["alembic", "postgres"]},
    "operations/email.md": {"facts": [], "tech": ["gmail"]},
    "operations/observability.md": {"facts": [("metrics", "22", "E6522C")], "tech": ["otel", "prometheus", "grafana"]},
    "operations/kafka.md": {"facts": [], "tech": ["kafka"]},
    "operations/redis.md": {"facts": [("authoritative", "never", "555555")], "tech": ["redis"]},
    "operations/troubleshooting.md": {"facts": [], "tech": ["docker", "postgres", "redis", "kafka"]},
    "adr/README.md": {"facts": [("records", "14", "555555"), ("status", "all accepted", "3fcf8e")], "tech": []},
}

HEADER_MARK = "img.shields.io/badge/docs-"
FOOTER_HEAD = "| ← Previous | Index | Next → |"
SOURCE_DIRS = ("backend", "frontend", "scripts", "sdk", "docker")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)\s]*)?\)")


def esc(text: str) -> str:
    """Escape a badge label or message the way shields.io expects."""
    return quote(text.replace("-", "--").replace("_", "__"), safe="")


def badge(label: str, message: str, color: str, logo: str | None = None, logo_color: str | None = None,
          href: str | None = None) -> str:
    url = f"https://img.shields.io/badge/{esc(label)}-{esc(message)}-{color}"
    if logo:
        url += f"?logo={logo}&logoColor={logo_color or 'white'}"
    img = f'<img alt="{label}: {message}" src="{url}">'
    return f'  <a href="{href}">{img}</a>' if href else f"  {img}"


def link_to(target_rel_docs: str, page_rel_docs: str) -> str:
    """A relative link from one docs page to another (paths relative to docs/)."""
    depth = len(Path(page_rel_docs).parent.parts)
    return ("../" * depth) + target_rel_docs


def title_of(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError("page has no H1")


def short_title(rel_docs: str) -> str:
    title = title_of((DOCS / rel_docs).read_text(encoding="utf-8"))
    if rel_docs.startswith("adr/") and rel_docs != "adr/README.md":
        number, _, rest = title.partition(". ")
        title = f"ADR {number}: {rest}"
    return title if len(title) <= 52 else title[:50].rstrip() + "…"


def reading_minutes(body: str) -> int:
    prose = re.sub(r"```.*?```", "", body, flags=re.S)
    words = len(re.findall(r"[A-Za-z0-9_']+", prose))
    return max(1, math.ceil(words / 200))


def source_badge(body: str, page: Path) -> str | None:
    for target in LINK.findall(body):
        if target.startswith(("http:", "https:", "mailto:")):
            continue
        resolved = (page.parent / target).resolve()
        try:
            parts = resolved.relative_to(ROOT).parts
        except ValueError:
            continue
        if parts and parts[0] in SOURCE_DIRS and resolved.exists():
            shown = "/".join(parts[-2:]) if len(parts) > 2 else "/".join(parts)
            return badge("source", shown, "3fcf8e", "github", "white", href=target)
    return None


def strip_generated(text: str) -> tuple[str, str]:
    """Split a page into its H1 line and its hand-written body."""
    lines = text.replace("\r\n", "\n").split("\n")
    h1 = next(i for i, line in enumerate(lines) if line.startswith("# "))
    head, rest = lines[: h1 + 1], lines[h1 + 1 :]

    def skip_blank(xs: list[str]) -> list[str]:
        while xs and not xs[0].strip():
            xs = xs[1:]
        return xs

    rest = skip_blank(rest)
    if rest and rest[0].strip() == "<p>" and any(HEADER_MARK in x for x in rest[:12]):
        end = next(i for i, x in enumerate(rest) if x.strip() == "</p>")
        rest = skip_blank(rest[end + 1 :])
    if rest and rest[0].startswith("[Docs]("):
        rest = skip_blank(rest[1:])

    body = "\n".join(rest).rstrip()
    if FOOTER_HEAD in body:
        cut = body.rfind(FOOTER_HEAD)
        before = body[:cut].rstrip()
        if before.endswith("---"):
            before = before[:-3].rstrip()
        body = before
    return "\n".join(head), body


def render(rel_docs: str, index: int) -> str:
    page = DOCS / rel_docs
    head, body = strip_generated(page.read_text(encoding="utf-8"))
    section = rel_docs.split("/")[0]
    label, anchor, color = SECTIONS[section]
    meta = PAGES.get(rel_docs, {"facts": [("status", "accepted", "3fcf8e")], "tech": []})
    index_link = link_to("README.md", rel_docs)

    rows = [badge("docs", label, color, "readthedocs", "white", href=f"{index_link}#{anchor}")]
    rows += [badge(lab, msg, col) for lab, msg, col in meta["facts"]]
    rows += [badge(*TECH[key]) for key in meta["tech"]]
    src = source_badge(body, page)
    if src:
        rows.append(src)
    rows.append(badge("read", f"{reading_minutes(body)} min", "555555"))

    total = len(ORDER)
    crumb = (f"[Docs]({index_link}) › [{label}]({index_link}#{anchor}) › **{title_of(head)}**"
             f" · page {index + 1} of {total}")

    prev_rel = ORDER[index - 1] if index > 0 else None
    next_rel = ORDER[index + 1] if index + 1 < total else None
    prev_cell = f"[{short_title(prev_rel)}]({link_to(prev_rel, rel_docs)})" if prev_rel else f"[Docs index]({index_link})"
    next_cell = f"[{short_title(next_rel)}]({link_to(next_rel, rel_docs)})" if next_rel else f"[Back to the start]({index_link})"
    footer = "\n".join([
        "---",
        "",
        FOOTER_HEAD,
        "| :--- | :---: | ---: |",
        f"| {prev_cell} | [Docs index]({index_link}) | {next_cell} |",
    ])

    return "\n".join([head, "", "<p>", *rows, "</p>", "", crumb, "", body, "", footer, ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report stale pages, change nothing")
    args = parser.parse_args()

    on_disk = sorted(p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md") if p.name != "README.md" or p.parent != DOCS)
    missing = sorted(set(on_disk) - set(ORDER))
    if missing:
        print("pages missing from the reading order in scripts/build_docs_nav.py:")
        for m in missing:
            print(f"  docs/{m}")
        return 1

    stale = []
    for i, rel_docs in enumerate(ORDER):
        page = DOCS / rel_docs
        new = render(rel_docs, i)
        if page.read_text(encoding="utf-8").replace("\r\n", "\n") != new:
            stale.append(rel_docs)
            if not args.check:
                page.write_text(new, encoding="utf-8", newline="\n")

    if args.check:
        for s in stale:
            print(f"  stale  docs/{s}")
        return 1 if stale else 0
    print(f"  {len(ORDER)} pages, {len(stale)} rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
