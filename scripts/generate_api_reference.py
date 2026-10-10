"""Generate the frontend's API reference data from the live OpenAPI schema.

    python scripts/generate_api_reference.py              # from a running API
    python scripts/generate_api_reference.py --offline    # from the app, no server

Writes ``frontend/src/lib/api-reference.generated.ts``.

The reference page is generated rather than written because a hand-maintained
list of 78 operations is a list that goes stale. The schema is the source of
truth; this turns it into something a React page can render without shipping a
400 KB spec to the browser, and ``make api-reference`` reruns it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "lib" / "api-reference.generated.ts"
DEFAULT_URL = "http://localhost:8000/openapi.json"

METHODS = ("get", "post", "put", "patch", "delete")

#: Tag order and presentation. A tag missing here still renders, at the end -
#: a new router should appear in the reference without this file being edited.
GROUPS: list[dict[str, str]] = [
    {
        "tag": "search",
        "title": "Search and planning",
        "blurb": "Plan without spending, execute, and stream a run as it happens.",
    },
    {
        "tag": "runs",
        "title": "Runs",
        "blurb": "Run history, the Run Inspector payload, replay and false-hit reports.",
    },
    {
        "tag": "catalog",
        "title": "Catalog",
        "blurb": "Engines, capability tags, the typed graph, and the paths that reach an engine.",
    },
    {
        "tag": "governance",
        "title": "Governance",
        "blurb": "Budgets, cache administration, analytics, benchmarks, the audit log and alerts.",
    },
    {
        "tag": "auth",
        "title": "Authentication",
        "blurb": "Registration, sessions, email verification and password reset.",
    },
    {
        "tag": "organizations",
        "title": "Organizations",
        "blurb": "Projects, members, API keys and organization settings.",
    },
    {
        "tag": "credentials",
        "title": "Upstream credentials",
        "blurb": "The encrypted SerpApi credential vault: attach, validate, rotate, revoke.",
    },
    {
        "tag": "infrastructure",
        "title": "Infrastructure",
        "blurb": "Liveness, readiness and Prometheus metrics.",
    },
]


def fetch(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read())


def build_offline() -> dict[str, Any]:
    """Import the app and ask FastAPI for the schema, with no server running."""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app  # noqa: PLC0415 - import cost is the point of --offline

    return app.openapi()


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def type_label(schema: dict[str, Any] | None) -> str:
    """A short human type for a parameter or field."""
    if not schema:
        return "any"
    if "$ref" in schema:
        return ref_name(schema["$ref"])
    if "anyOf" in schema or "oneOf" in schema:
        parts = [type_label(s) for s in schema.get("anyOf") or schema.get("oneOf") or []]
        parts = [p for p in parts if p != "null"]
        return " | ".join(dict.fromkeys(parts)) or "any"
    if schema.get("enum"):
        return " | ".join(json.dumps(v) for v in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        return type_label(schema.get("items")) + "[]"
    if kind == "null":
        return "null"
    return str(kind or "object")


def first_line(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split("\n\n")[0].split())


def collect(spec: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for path, item in spec.get("paths", {}).items():
        for method in METHODS:
            op = item.get(method)
            if not op:
                continue

            params = []
            for param in list(item.get("parameters", [])) + list(op.get("parameters", [])):
                if "$ref" in param:
                    continue
                params.append(
                    {
                        "name": param.get("name", ""),
                        "location": param.get("in", "query"),
                        "required": bool(param.get("required")),
                        "type": type_label(param.get("schema")),
                        "description": first_line(param.get("description")),
                    }
                )

            body = None
            request = op.get("requestBody")
            if request:
                content = (request.get("content") or {}).get("application/json") or {}
                schema = content.get("schema") or {}
                body = {
                    "type": type_label(schema),
                    "required": bool(request.get("required")),
                }

            responses = []
            for status, response in sorted((op.get("responses") or {}).items()):
                content = (response.get("content") or {}).get("application/json") or {}
                responses.append(
                    {
                        "status": status,
                        "description": first_line(response.get("description")),
                        "type": type_label(content.get("schema")) if content else "",
                    }
                )

            operations.append(
                {
                    "id": op.get("operationId") or f"{method}_{path}",
                    "method": method.upper(),
                    "path": path,
                    "tag": (op.get("tags") or ["other"])[0],
                    "summary": first_line(op.get("summary")) or op.get("operationId", ""),
                    "description": first_line(op.get("description")),
                    "deprecated": bool(op.get("deprecated")),
                    "parameters": params,
                    "body": body,
                    "responses": responses,
                }
            )
    return operations


def render(spec: dict[str, Any], operations: list[dict[str, Any]]) -> str:
    seen = {op["tag"] for op in operations}
    groups = [g for g in GROUPS if g["tag"] in seen]
    groups += [
        {"tag": tag, "title": tag.replace("_", " ").title(), "blurb": ""}
        for tag in sorted(seen - {g["tag"] for g in GROUPS})
    ]

    info = spec.get("info", {})
    header = f"""/**
 * API reference data, generated from the OpenAPI schema.
 *
 * Do not edit by hand: run `make api-reference` (or
 * `python scripts/generate_api_reference.py`) after changing a router. A
 * hand-maintained list of {len(operations)} operations is a list that goes stale.
 */

export type ApiParameter = {{
  name: string;
  location: string;
  required: boolean;
  type: string;
  description: string;
}};

export type ApiResponse = {{ status: string; description: string; type: string }};

export type ApiOperation = {{
  id: string;
  method: string;
  path: string;
  tag: string;
  summary: string;
  description: string;
  deprecated: boolean;
  parameters: ApiParameter[];
  body: {{ type: string; required: boolean }} | null;
  responses: ApiResponse[];
}};

export type ApiGroup = {{ tag: string; title: string; blurb: string }};

export const API_TITLE = {json.dumps(info.get("title", "SerpFlow"))};
export const API_VERSION = {json.dumps(info.get("version", "1.0.0"))};
export const API_OPERATION_COUNT = {len(operations)};
export const API_PATH_COUNT = {len(spec.get("paths", {}))};

export const API_GROUPS: ApiGroup[] = {json.dumps(groups, indent=2)};

export const API_OPERATIONS: ApiOperation[] = {json.dumps(operations, indent=2)};
"""
    return header


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the API reference data.")
    parser.add_argument("--url", default=DEFAULT_URL, help="where to read the schema from")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="import the app and build the schema instead of calling a server",
    )
    args = parser.parse_args()

    if args.offline:
        spec = build_offline()
        source = "app.main:app"
    else:
        try:
            spec = fetch(args.url)
            source = args.url
        except Exception as exc:
            print(
                f"Could not read {args.url} ({type(exc).__name__}).\n"
                "Start the API, or pass --offline to build the schema from the app.",
                file=sys.stderr,
            )
            return 1

    operations = collect(spec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(spec, operations), encoding="utf-8")

    print("")
    print("  source      " + source)
    print("  paths       " + str(len(spec.get("paths", {}))))
    print("  operations  " + str(len(operations)))
    print("  written     " + str(OUT.relative_to(ROOT)))
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
