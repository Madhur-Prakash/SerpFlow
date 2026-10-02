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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check documentation links.")
    parser.add_argument(
        "--anchors", action="store_true", help="also verify #fragments resolve to a heading"
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
