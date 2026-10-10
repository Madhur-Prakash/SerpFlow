"""Regenerate catalog drafts from the SerpApi documentation (section 12).

The authoring method is::

    1. Scrape SerpApi engine documentation
    2. Generate draft YAML per engine (schema, params, cost, locale sensitivity)
    3. Derive dependency edges: which output fields satisfy which required inputs
    4. Derive capability_tags and substitutes by grouping engines by purpose
    5. Human review pass - steps 3 and 4 cannot be fully automated
    6. Commit as versioned files under backend/app/services/catalog/data/

This script does steps 1 and 2 and writes to ``data/_drafts/``. It never
overwrites a committed catalog file, because the committed catalog is the
source of truth and steps 3 and 4 are hand-maintained: a scraper can see that
``google_maps_reviews`` takes a ``data_id``, but only a human knows that
``google_maps.local_results[].data_id`` is the field that satisfies it, or that
Yelp's coverage collapses outside US metros.

    make catalog-build              refresh the drafts
    make catalog-build ARGS=--diff  report what changed against the committed catalog
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import yaml  # noqa: E402

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.services.catalog.loader import DATA_ROOT, load_catalog  # noqa: E402

log = get_logger("serpflow.catalog.build")

DRAFT_DIR = DATA_ROOT / "_drafts"
DOCS_INDEX = "https://serpapi.com/search-api"
USER_AGENT = "serpflow-catalog-build/1.0 (+https://github.com/serpflow/serpflow)"

# Parameter names that imply the engine is locale sensitive.
LOCALE_PARAMS = {
    "hl",
    "gl",
    "location",
    "google_domain",
    "lr",
    "cc",
    "mkt",
    "country",
    "lang",
    "kl",
    "where",
    "vl",
    "yelp_domain",
    "amazon_domain",
    "ebay_domain",
    "yandex_domain",
    "yahoo_domain",
    "geo",
    "currency",
    "ct",
    "store_id",
    "delivery_zip",
}

# Parameter names that are opaque identifiers, and therefore candidates for a
# dependency edge. The human review pass decides which upstream field fills them.
IDENTIFIER_PARAMS = {
    "data_id",
    "place_id",
    "contributor_id",
    "product_id",
    "us_item_id",
    "author_id",
    "patent_id",
    "page_token",
    "next_page_token",
    "departure_token",
    "property_token",
    "result_id",
    "citation_id",
    "asin",
    "id",
    "image_url",
    "url",
    "mid",
}


async def fetch(url: str, client: httpx.AsyncClient) -> str | None:
    try:
        response = await client.get(url, headers={"user-agent": USER_AGENT}, timeout=20.0)
        if response.status_code >= 400:
            return None
        return response.text
    except httpx.HTTPError as exc:
        log.warning(
            "documentation fetch failed",
            extra={"event": "catalog.fetch_failed", "url": url, "error": type(exc).__name__},
        )
        return None


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def discover_engines(html: str) -> dict[str, str]:
    """Engine name -> documentation URL, from the API index page."""
    found: dict[str, str] = {}
    for match in re.finditer(r'href="(/[a-z0-9-]+(?:-api)?)"[^>]*>([^<]{3,80})<', html):
        href, label = match.group(1), match.group(2).strip()
        slug = href.strip("/").removesuffix("-api")
        engine = slug.replace("-", "_")
        if not engine or len(engine) > 60:
            continue
        found[engine] = "https://serpapi.com" + href
        _ = label
    return found


def extract_parameters(html: str) -> tuple[list[str], list[str]]:
    """``(required, optional)`` parameter names from a documentation page."""
    required: list[str] = []
    optional: list[str] = []
    text = html
    for match in re.finditer(
        r'<h3[^>]*id="([a-z0-9_]+)"[^>]*>.*?</h3>(.{0,600}?)(?=<h3|</section)',
        text,
        flags=re.S | re.I,
    ):
        name, body = match.group(1), _strip_tags(match.group(2)).lower()
        if "required" in body[:200] and "optional" not in body[:120]:
            required.append(name)
        else:
            optional.append(name)
    if not required and not optional:
        for match in re.finditer(r"<code>([a-z0-9_]{2,30})</code>", text):
            name = match.group(1)
            if name not in optional:
                optional.append(name)
    return required, optional


def extract_purpose(html: str) -> str:
    match = re.search(r'<meta name="description" content="([^"]{20,300})"', html)
    if match:
        return match.group(1).strip()
    match = re.search(r"<h1[^>]*>(.{5,120}?)</h1>", html, flags=re.S)
    return _strip_tags(match.group(1)) if match else ""


def draft_for(engine: str, url: str, html: str) -> dict[str, Any]:
    required, optional = extract_parameters(html)
    locale_sensitive = sorted({p for p in (required + optional) if p in LOCALE_PARAMS})
    chainable = sorted({p for p in required if p in IDENTIFIER_PARAMS})

    requires: dict[str, Any] = {}
    for name in required:
        entry: dict[str, Any] = {"type": "string", "satisfied_by": []}
        if name in IDENTIFIER_PARAMS:
            entry["description"] = (
                "REVIEW: opaque identifier. Fill satisfied_by with the upstream "
                "field that produces it."
            )
        requires[name] = entry

    return {
        "engine": engine,
        "purpose": extract_purpose(html)[:200],
        # Steps 3 and 4 of the authoring method. A scraper cannot do these.
        "capability_tags": ["REVIEW_ME"],
        "substitutes": [],
        "single_source_note": "REVIEW: state the trade-off, or list substitutes.",
        "requires": requires or {"q": {"type": "string", "satisfied_by": []}},
        "optional": [p for p in optional if p not in required][:24],
        "produces": {},
        "cost": 1,
        "latency_class": "medium",
        "volatility_prior": "7d",
        "locale_sensitive": locale_sensitive,
        "pii_risk": "high" if "review" in engine or "contributor" in engine else "low",
        "docs_url": url,
        "_review": {
            "chainable_params": chainable,
            "notes": (
                "Derive dependency edges (step 3) and capability_tags/substitutes "
                "(step 4) by hand before promoting this draft."
            ),
        },
    }


async def build(limit: int | None = None) -> dict[str, Any]:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        index_html = await fetch(DOCS_INDEX, client)
        if index_html is None:
            return {
                "status": "offline",
                "message": (
                    "Could not reach " + DOCS_INDEX + ". The committed catalog is the "
                    "source of truth and is unaffected; drafts were not regenerated."
                ),
            }

        engines = discover_engines(index_html)
        if limit:
            engines = dict(list(engines.items())[:limit])

        drafts: list[dict[str, Any]] = []
        for engine, url in sorted(engines.items()):
            html = await fetch(url, client)
            if html is None:
                continue
            drafts.append(draft_for(engine, url, html))

    out = DRAFT_DIR / "draft_engines.yaml"
    with out.open("w", encoding="utf-8") as handle:
        handle.write(
            "# AUTOGENERATED DRAFT - not the source of truth.\n"
            "#\n"
            "# Steps 1 and 2 of the section 12 authoring method. Steps 3 (dependency\n"
            "# edges) and 4 (capability tags and substitutes) require a human review\n"
            "# pass; every field marked REVIEW_ME must be resolved before any of this\n"
            "# is promoted into a committed catalog version.\n\n"
        )
        yaml.safe_dump({"engines": drafts}, handle, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "discovered": len(engines), "drafted": len(drafts), "path": str(out)}


def diff_against_committed() -> dict[str, Any]:
    """What the committed catalog covers, and what it is missing."""
    index = load_catalog()
    draft_path = DRAFT_DIR / "draft_engines.yaml"
    if not draft_path.exists():
        return {"status": "no_drafts", "message": "Run `make catalog-build` first."}
    with draft_path.open("r", encoding="utf-8") as handle:
        drafts = yaml.safe_load(handle) or {}
    draft_names = {d["engine"] for d in drafts.get("engines", [])}
    committed = set(index.names())
    return {
        "status": "ok",
        "catalog_version": index.version,
        "committed": len(committed),
        "drafted": len(draft_names),
        "missing_from_catalog": sorted(draft_names - committed),
        "not_in_drafts": sorted(committed - draft_names),
    }


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Regenerate SerpApi catalog drafts.")
    parser.add_argument("--limit", type=int, default=None, help="only the first N engines")
    parser.add_argument(
        "--diff", action="store_true", help="compare drafts against the committed catalog"
    )
    args = parser.parse_args()

    if args.diff:
        result = diff_against_committed()
    else:
        result = asyncio.run(build(limit=args.limit))

    print("")
    for key, value in result.items():
        if isinstance(value, list):
            print(key.ljust(22) + str(len(value)))
            for item in value[:20]:
                print("  " + item)
        else:
            print(key.ljust(22) + str(value))
    print("")
    print("The committed catalog under app/services/catalog/data/ is the source of")
    print("truth. Drafts are a starting point for the human review pass, never a")
    print("replacement for it.")
    return 0 if result.get("status") in ("ok", "offline") else 1


if __name__ == "__main__":
    raise SystemExit(main())
