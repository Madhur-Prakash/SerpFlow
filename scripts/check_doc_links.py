"""Verify that every relative link in every markdown file resolves.

    python scripts/check_doc_links.py          # all markdown
    python scripts/check_doc_links.py --anchors  # also check #fragments

Section 79 of the specification: "All documentation must link to real
implementation paths. No dead documentation." This is what enforces it, and
`make docs-check` runs it.

Three kinds of reference are checked:

  * markdown links to another file, resolved relative to the linking file
  * backticked repository paths such as `backend/app/core/security.py`
  * backticked backend-relative paths such as `app/services/planner/cost.py`

The last two matter because a doc that *names* a file it does not link is just
as wrong when that file is renamed, and those are the references a link checker
normally misses.

    python scripts/check_doc_links.py --interlinks  # also check the docs are woven together

With `--interlinks`, every page under docs/ must also end with a `## Related`
(or, for a decision record, `## See also`) section of at least three links,
and must be linked from the body of at least one other page. Every folder must
have a README.md section index that links every page in the folder. The generated
badge header, breadcrumb and previous / next footer do not count: a page that
is reachable only by pressing Next is an orphan. Related links that are not
returned are listed, as a prompt rather than a failure.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    # Local render workspace for the product film: gitignored, and full of
    # third-party package READMEs that are not this project's documentation.
    "videos",
}

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REPO_PATH = re.compile(r"`((?:backend|frontend|docs|docker|scripts|sdk)/[A-Za-z0-9_./-]+)`")
BACKEND_PATH = re.compile(r"`((?:app|tests|alembic|fixtures)/[A-Za-z0-9_./-]+\.[a-z]{2,4})`")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def slugify(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text.strip())


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.parts)
    )


def anchors_in(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    found = {slugify(match.group(2)) for match in HEADING.finditer(text)}
    # Explicit anchors, e.g. <a id="..."> or <a name="...">.
    found |= set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))
    return found


RELATED = re.compile(r"^## (?:Related|See also)\s*$", re.MULTILINE)
DOCS = ROOT / "docs"


def doc_links(body: str, page: Path) -> set[Path]:
    """The docs pages a page's body links to, excluding itself."""
    found = set()
    for target in LINK.findall(body):
        path_part = target.partition("#")[0]
        if not path_part or target.startswith(("http://", "https://", "mailto:", "//")):
            continue
        resolved = (page.parent / path_part).resolve()
        if resolved.suffix == ".md" and resolved.is_relative_to(DOCS) and resolved != page:
            found.add(resolved)
    return found


def check_interlinks() -> tuple[list[str], list[str], int]:
    """Pages without a closing Related section, orphans, and one-way Related links."""
    from build_docs_nav import strip_generated  # same directory; strips the generated blocks

    index = DOCS / "README.md"
    pages = sorted(p.resolve() for p in DOCS.rglob("*.md") if p.resolve() != index.resolve())
    bodies = {p: strip_generated(p.read_text(encoding="utf-8"))[1] for p in pages}
    related: dict[Path, set[Path]] = {}
    problems: list[str] = []

    for page, body in bodies.items():
        match = None
        for match in RELATED.finditer(body):
            pass
        section = body[match.end():] if match else ""
        related[page] = doc_links(section, page)
        if len(LINK.findall(section)) < 3:
            problems.append(f"{page.relative_to(ROOT)}  no closing Related / See also section of 3+ links")

    inbound = {page: 0 for page in pages}
    total = 0
    for page, body in bodies.items():
        for target in doc_links(body, page):
            total += 1
            if target in inbound:
                inbound[target] += 1
    problems += [f"{p.relative_to(ROOT)}  orphan: no other page links to it" for p, n in inbound.items() if not n]

    # A folder's README.md is its section index: it must list every page beside it.
    for folder in sorted(d for d in DOCS.iterdir() if d.is_dir()):
        section_index = (folder / "README.md").resolve()
        if section_index not in bodies:
            problems.append(f"{folder.relative_to(ROOT)}  has no README.md section index")
            continue
        listed = doc_links(bodies[section_index], section_index)
        problems += [
            f"{section_index.relative_to(ROOT)}  does not link {p.name}, a page in its folder"
            for p in sorted(folder.glob("*.md"))
            if p.resolve() != section_index and p.resolve() not in listed
        ]

    one_way = sorted(
        f"{a.relative_to(DOCS).as_posix()} -> {b.relative_to(DOCS).as_posix()}"
        for a, targets in related.items()
        for b in targets
        if b in related and a not in related[b] and a not in doc_links(bodies[b], b)
    )
    return problems, one_way, total


def main() -> int:
    parser = argparse.ArgumentParser(description="Check documentation links.")
    parser.add_argument(
        "--anchors", action="store_true", help="also verify #fragments resolve to a heading"
    )
    parser.add_argument(
        "--interlinks", action="store_true", help="also require Related sections and no orphan pages"
    )
    args = parser.parse_args()

    files = markdown_files()
    anchor_cache: dict[Path, set[str]] = {}
    broken: list[str] = []
    link_count = 0
    path_count = 0

    for file in files:
        text = file.read_text(encoding="utf-8")
        lines = text.splitlines()

        for number, line in enumerate(lines, 1):
            for match in LINK.finditer(line):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "//")):
                    continue
                link_count += 1

                path_part, _, fragment = target.partition("#")
                if not path_part:
                    # A same-page anchor.
                    if args.anchors:
                        anchor_cache.setdefault(file, anchors_in(file))
                        if fragment and slugify(fragment) not in anchor_cache[file]:
                            broken.append(
                                f"{file.relative_to(ROOT)}:{number}  #{fragment} (no such heading)"
                            )
                    continue

                resolved = (file.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append(f"{file.relative_to(ROOT)}:{number}  ->  {target}")
                    continue

                if args.anchors and fragment and resolved.suffix == ".md":
                    anchor_cache.setdefault(resolved, anchors_in(resolved))
                    if slugify(fragment) not in anchor_cache[resolved]:
                        broken.append(
                            f"{file.relative_to(ROOT)}:{number}  ->  {target} (no such heading)"
                        )

            for match in REPO_PATH.finditer(line):
                candidate = match.group(1).rstrip(".")
                path_count += 1
                if not (ROOT / candidate).exists():
                    broken.append(f"{file.relative_to(ROOT)}:{number}  `{candidate}` does not exist")

            for match in BACKEND_PATH.finditer(line):
                candidate = match.group(1)
                path_count += 1
                if not (ROOT / "backend" / candidate).exists():
                    broken.append(
                        f"{file.relative_to(ROOT)}:{number}  `{candidate}` does not exist"
                    )

    print("")
    print("  markdown files   " + str(len(files)))
    print("  relative links   " + str(link_count))
    print("  cited paths      " + str(path_count))
    if args.anchors:
        print("  anchors          checked")
    if args.interlinks:
        problems, one_way, cross_links = check_interlinks()
        broken += problems
        print("  page cross-links " + str(cross_links))
        if one_way:
            print("")
            print("  " + str(len(one_way)) + " Related link(s) not returned (the target never links back):")
            for item in one_way:
                print("    " + item)
    print("")

    if broken:
        print("  " + str(len(broken)) + " broken reference(s):")
        for item in broken:
            print("    " + item)
        print("")
        return 1

    print("  Every reference resolves.")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
