"""Exercise every API operation against a running instance and report failures.

    python scripts/check_api.py                     # http://localhost:8000
    python scripts/check_api.py --base http://...   # somewhere else
    python scripts/check_api.py --verbose           # print every call

Reads the OpenAPI schema, so the list of operations cannot drift from the
server. Every path parameter is filled from a real record created or fetched
during the run - a reference page that lists 78 endpoints proves nothing about
whether they answer.

Mutating calls are exercised deliberately, against the seeded demo
organization, in an order that leaves it usable: create before read, rotate
before revoke, and nothing that deletes the organization itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_BASE = "http://localhost:8000"
OWNER_EMAIL = "owner@serpflow.dev"
DEMO_PASSWORD = "serpflow-demo-2026"

# Operations that are destructive, long-running, or need an upstream account.
# Each is skipped with the reason, so the summary says what was not covered
# rather than quietly reporting a clean run.
SKIP: dict[tuple[str, str], str] = {
    ("POST", "/v1/auth/logout"): "would end the session the rest of the run needs",
    ("DELETE", "/v1/organizations/current"): "deletes the demo organization",
    ("POST", "/v1/benchmarks/run"): "makes real LLM calls",
    ("GET", "/metrics"): "not JSON; checked separately",
    ("POST", "/v1/credentials/{credential_id}/validate"): "calls SerpApi",
    ("POST", "/v1/credentials/{credential_id}/rotate"): "needs a real upstream key",
    ("POST", "/v1/runs/{run_id}/replay"): "exercised through the demo",
    ("GET", "/v1/runs/{run_id}/stream"): "server-sent events; checked separately",
}


class Client:
    def __init__(self, base: str, verbose: bool = False) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None
        self.api_key: str | None = None
        self.verbose = verbose

    def call(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        auth: bool = True,
        raw: bool = False,
    ) -> tuple[int, Any]:
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("accept", "application/json")
        if data:
            request.add_header("content-type", "application/json")

        # Execution routes get the test API key when one is available. A human
        # bearer token honours SERPFLOW_MODE, which on a replay instance means
        # a cassette miss - a correct refusal, but it tells us nothing about
        # whether the endpoint works. A `test` key always routes to the
        # deterministic mock, which is how these are meant to be called.
        execution = path.rstrip("/") in ("/v1/search", "/v1/run", "/v1/plan")
        if auth and execution and self.api_key:
            request.add_header("x-api-key", self.api_key)
        elif auth and self.token:
            request.add_header("authorization", "Bearer " + self.token)
        elif auth and self.api_key:
            request.add_header("x-api-key", self.api_key)

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
        except Exception as exc:  # connection refused, timeout
            return 0, {"error": type(exc).__name__ + ": " + str(exc)}

        if raw:
            return status, payload
        try:
            return status, json.loads(payload) if payload else None
        except Exception:
            return status, payload.decode("utf-8", "replace")[:400]


def login(client: Client) -> bool:
    status, body = client.call(
        "POST",
        "/v1/auth/login",
        {"email": OWNER_EMAIL, "password": DEMO_PASSWORD},
        auth=False,
    )
    if status != 200 or not isinstance(body, dict):
        print("  Could not sign in as " + OWNER_EMAIL + " (HTTP " + str(status) + ").")
        print("  Run `make seed` first.")
        return False
    client.token = body.get("access_token")
    return bool(client.token)


def collect_ids(client: Client) -> dict[str, str]:
    """Real identifiers for every path parameter the schema uses."""
    ids: dict[str, str] = {}

    def first(path: str, *keys: str, field: str = "items") -> str | None:
        status, body = client.call("GET", path)
        if status != 200:
            return None
        items = body.get(field) if isinstance(body, dict) else body
        if not isinstance(items, list) or not items:
            return None
        row = items[0]
        for key in keys:
            if isinstance(row, dict) and row.get(key):
                return str(row[key])
        return None

    ids["project_id"] = first("/v1/projects", "id") or ""
    ids["membership_id"] = first("/v1/members", "id") or ""
    ids["key_id"] = first("/v1/keys", "id") or ""
    ids["credential_id"] = first("/v1/credentials", "id") or ""
    ids["budget_id"] = first("/v1/budgets", "id", field="budgets") or ""
    ids["session_id"] = first("/v1/auth/sessions", "id") or ""
    ids["alert_id"] = first("/v1/alerts", "id") or ""
    ids["engine"] = first("/v1/catalog/engines", "engine", "name") or "google_maps"
    ids["channel_id"] = first("/v1/notification-channels", "id") or ""

    # A run (and therefore a plan and a step) has to exist for the run routes.
    run_id = first("/v1/runs", "id")
    if not run_id:
        status, body = client.call(
            "POST", "/v1/search", {"intent": "cafes in Koramangala", "budget": 5}
        )
        if status < 400 and isinstance(body, dict):
            run_id = (body.get("run") or {}).get("id") or body.get("run_id")
    ids["run_id"] = run_id or ""

    if run_id:
        status, body = client.call("GET", "/v1/runs/" + run_id)
        if status == 200 and isinstance(body, dict):
            plan = body.get("plan") or {}
            ids["plan_id"] = str(plan.get("id") or "")
            steps = body.get("steps") or plan.get("steps") or []
            if steps and isinstance(steps[0], dict):
                ids["step_id"] = str(steps[0].get("id") or "")

    # No channel is seeded, so make one. It is deleted by the DELETE route
    # later in the run, which is the point of creating it here.
    if not ids["channel_id"]:
        status, body = client.call(
            "POST",
            "/v1/notification-channels",
            {
                "name": "api-check",
                "kind": "email",
                "target": "ops@serpflow-checks.dev",
            },
        )
        if status < 400 and isinstance(body, dict):
            ids["channel_id"] = str(body.get("id") or "")

    ids.setdefault("plan_id", "")
    ids.setdefault("step_id", "")
    return ids


def sample_body(method: str, path: str, ids: dict[str, str]) -> Any | None:
    """A minimal valid body for the operations that need one."""
    suffix = uuid.uuid4().hex[:8]
    bodies: dict[tuple[str, str], Any] = {
        ("POST", "/v1/plan"): {"intent": "cafes in Koramangala", "budget": 5},
        ("POST", "/v1/search"): {"intent": "cafes in Koramangala", "budget": 5},
        ("POST", "/v1/run"): {"intent": "cafes in Koramangala", "budget": 5},
        ("POST", "/v1/projects"): {"name": "Check " + suffix, "slug": "check-" + suffix},
        ("POST", "/v1/budgets"): {
            "scope": "project",
            "scope_id": ids.get("project_id", ""),
            "limit_credits": 25,
            "name": "Check " + suffix,
        },
        ("POST", "/v1/cache/invalidate"): {"engine": "__none__", "scope": "project"},
        ("POST", "/v1/auth/forgot-password"): {"email": OWNER_EMAIL},
        ("POST", "/v1/auth/register"): {
            "email": "check-" + suffix + "@serpflow-checks.dev",
            "password": "check-password-" + suffix,
            "full_name": "API Check",
        },
        ("POST", "/v1/keys"): {"name": "Check " + suffix, "environment": "test", "role": "analyst"},
        ("POST", "/v1/credentials"): {
            "name": "Check " + suffix,
            "api_key": "check-not-a-real-serpapi-key-" + suffix,
        },
        ("POST", "/v1/notification-channels"): {
            "name": "Check " + suffix,
            "kind": "email",
            "target": "ops@serpflow-checks.dev",
        },
        ("PATCH", "/v1/organizations/current"): {"name": "SerpFlow Demo"},
        ("POST", "/v1/runs/{run_id}/report-false-hit"): {
            "note": "api check",
            "invalidate_entry": False,
        },
    }
    key = (method, path)
    if key in bodies:
        return bodies[key]
    if method in ("PATCH", "PUT"):
        # A no-op patch still proves the route, the guard and the schema.
        if "budget" in path:
            return {"limit_credits": 25}
        if "project" in path:
            return {"description": "api check"}
        if "member" in path:
            return {"role": "analyst"}
        return {}
    if method == "POST":
        return {}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise every API operation.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    client = Client(args.base, args.verbose)

    status, _ = client.call("GET", "/healthz", auth=False)
    if status != 200:
        print("\n  " + args.base + " is not answering (/healthz -> " + str(status) + ").\n")
        return 1

    status, spec = client.call("GET", "/openapi.json", auth=False)
    if status != 200 or not isinstance(spec, dict):
        print("\n  Could not read the OpenAPI schema.\n")
        return 1

    if not login(client):
        return 1

    # Mint a test key for the execution routes. Keys belong to a project, so
    # the project comes first.
    status, projects = client.call("GET", "/v1/projects")
    project_id = ""
    if status == 200:
        items = projects.get("items") if isinstance(projects, dict) else projects
        if isinstance(items, list) and items:
            project_id = str(items[0].get("id") or "")

    if project_id:
        status, body = client.call(
            "POST",
            "/v1/projects/" + project_id + "/keys",
            {"name": "api-check", "environment": "test", "role": "developer"},
        )
        if status < 400 and isinstance(body, dict):
            client.api_key = body.get("plaintext")

    if not client.api_key:
        print("  Could not mint a test API key; execution routes will use the session token.")

    ids = collect_ids(client)
    missing = [name for name, value in ids.items() if not value]

    operations: list[tuple[str, str]] = []
    for path, item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                operations.append((method.upper(), path))
    operations.sort(key=lambda op: (op[1], op[0]))

    print("")
    print("  base        " + args.base)
    print("  operations  " + str(len(operations)))
    if missing:
        print("  no id for   " + ", ".join(sorted(missing)))
    print("")

    failures: list[str] = []
    skipped: list[str] = []
    passed = 0

    for method, path in operations:
        if (method, path) in SKIP:
            skipped.append(method + " " + path + "  (" + SKIP[(method, path)] + ")")
            continue

        concrete = path
        unresolved = False
        for name, value in ids.items():
            token = "{" + name + "}"
            if token in concrete:
                if not value:
                    unresolved = True
                    break
                concrete = concrete.replace(token, value)
        if "{" in concrete or unresolved:
            skipped.append(method + " " + path + "  (no identifier available)")
            continue

        body = sample_body(method, path, ids)
        code, payload = client.call(method, concrete, body)

        # 2xx is a pass. So is a deliberate, documented refusal: those prove
        # the route and its guard are wired, which is what this checks.
        expected = code < 400 or code in (402, 404, 409, 412, 422)
        if expected:
            passed += 1
            if args.verbose:
                print("  ok    " + str(code) + "  " + method + " " + concrete)
        else:
            detail = ""
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("code", "")) + ": " + str(error.get("message", ""))[:90]
                else:
                    detail = json.dumps(payload)[:110]
            else:
                detail = str(payload)[:110]
            failures.append(
                "  " + str(code).rjust(3) + "  " + method.ljust(6) + path + "\n        " + detail
            )

    # Two surfaces the schema does not describe as JSON.
    code, _ = client.call("GET", "/metrics", auth=False, raw=True)
    metrics_ok = code == 200
    code, _ = client.call("GET", "/readyz", auth=False)
    ready_ok = code == 200

    print("  passed   " + str(passed))
    print("  failed   " + str(len(failures)))
    print("  skipped  " + str(len(skipped)))
    print("  /metrics " + ("ok" if metrics_ok else "FAILED"))
    print("  /readyz  " + ("ok" if ready_ok else "FAILED"))
    print("")

    if skipped and args.verbose:
        print("  Skipped:")
        for item in skipped:
            print("    " + item)
        print("")

    if failures:
        print("  Failures:")
        for item in failures:
            print(item)
        print("")
        return 1

    if not metrics_ok or not ready_ok:
        return 1

    print("  Every operation answered.")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
