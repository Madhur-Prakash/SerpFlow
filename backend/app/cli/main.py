"""SerpFlow CLI (section 60).

    serpflow search "flights from Hyderabad to Da Nang in late November"
    serpflow plan --budget 20 "review rings among Koramangala cafes"
    serpflow catalog explore google_maps
    serpflow replay run_01JQ...
    serpflow benchmark run

Everything goes through the public API client layer, so the CLI exercises the
same code path a user's integration would. ``--local`` runs against the service
layer in-process instead, which is what the Makefile targets use.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="serpflow",
    help="SerpFlow - a search control plane for SerpApi.",
    no_args_is_help=True,
    add_completion=False,
)
catalog_app = typer.Typer(help="Explore the engine catalog.", no_args_is_help=True)
benchmark_app = typer.Typer(help="Run and inspect the routing benchmark.", no_args_is_help=True)
cache_app = typer.Typer(help="Inspect and invalidate the cache.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(cache_app, name="cache")

console = Console()

DEFAULT_BASE_URL = os.environ.get("SERPFLOW_BASE_URL", "http://localhost:8000")


def _client(base_url: str, api_key: str | None) -> httpx.Client:
    key = api_key or os.environ.get("SERPFLOW_API_KEY")
    if not key:
        console.print(
            "[red]No API key.[/red] Set SERPFLOW_API_KEY or pass --api-key. "
            "A test key routes to the deterministic mock and costs nothing."
        )
        raise typer.Exit(2)
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"X-API-Key": key, "content-type": "application/json"},
        timeout=120.0,
    )


def _fail(response: httpx.Response) -> None:
    try:
        body = response.json()
        error = body.get("error", {})
        console.print(
            Panel(
                str(error.get("message", response.text))
                + (
                    "\n\nrequest_id: " + str(error.get("request_id"))
                    if error.get("request_id")
                    else ""
                ),
                title="[red]" + str(error.get("code", response.status_code)) + "[/red]",
                border_style="red",
            )
        )
    except ValueError:
        console.print("[red]HTTP " + str(response.status_code) + "[/red] " + response.text[:400])
    raise typer.Exit(1)


def _mode_badge(mode: str) -> str:
    colors = {"LIVE": "green", "MOCK": "cyan", "REPLAY": "yellow", "RECORD": "magenta"}
    color = colors.get(mode.upper(), "white")
    return "[" + color + "]" + mode.upper() + "[/" + color + "]"


def _render_plan(plan: dict[str, Any]) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", width=3)
    table.add_column("engine")
    table.add_column("fan-out", justify="right")
    table.add_column("freshness")
    table.add_column("cache", justify="left")
    for step in plan.get("steps", []):
        state = step.get("cache_state") or {}
        layer = state.get("layer", "miss")
        warm = "[green]warm[/green]" if step.get("warm") else "[dim]cold[/dim]"
        table.add_row(
            str(step.get("index")),
            step.get("engine", ""),
            "x" + str(step.get("fan_out", 1)),
            step.get("freshness_requirement", "stable"),
            layer + " " + warm,
        )
    console.print(table)

    naive = plan.get("naive_cost", 0)
    marginal = plan.get("marginal_cost", 0)
    console.print("")
    console.print(
        "  naive execution   [bold]" + str(naive) + "[/bold] credits\n"
        "  marginal execution [bold]" + str(marginal) + "[/bold] credits\n"
        "  saved              [bold green]"
        + str(max(0, naive - marginal))
        + "[/bold green] credits"
    )
    if plan.get("projected_full_scale_cost"):
        console.print(
            "  full-scale         "
            + str(plan["projected_full_scale_cost"])
            + " credits [dim](projection only, never executed live)[/dim]"
        )
    console.print("")
    console.print(
        "  candidates "
        + str(plan.get("candidate_count", 0))
        + "   catalog "
        + str(plan.get("catalog_version", ""))
        + "   confidence "
        + str(round(plan.get("confidence", 0), 3))
    )
    if plan.get("single_candidate_reason"):
        console.print("  [yellow]single candidate:[/yellow] " + plan["single_candidate_reason"])

    if plan.get("marginal_replan_changed_selection"):
        console.print("")
        console.print(
            Panel(
                plan.get("replan_explanation", ""),
                title="[bold green]Marginal replanning changed the selected plan[/bold green]",
                border_style="green",
            )
        )

    rejected = plan.get("rejected_alternatives") or []
    if rejected:
        console.print("")
        console.print("[bold]Rejected alternatives[/bold]")
        for alternative in rejected[:6]:
            console.print(
                "  "
                + alternative.get("plan", "")
                + "  [dim]cold "
                + str(alternative.get("naive_cost"))
                + " / marginal "
                + str(alternative.get("marginal_cost"))
                + "  "
                + str(alternative.get("coverage"))
                + "[/dim]"
            )
            if alternative.get("reason"):
                console.print("    [dim]" + alternative["reason"] + "[/dim]")

    reduction = plan.get("budget_reduction")
    if reduction and reduction.get("reductions"):
        console.print("")
        console.print("[bold yellow]Budget reductions[/bold yellow]")
        for item in reduction["reductions"]:
            console.print(
                "  step "
                + str(item["step"])
                + " "
                + item.get("engine", "")
                + ": "
                + str(item["original"])
                + " -> "
                + str(item["reduced"])
            )
            console.print("    [dim]" + item["impact_note"] + "[/dim]")


@app.command()
def plan(
    intent: Annotated[str, typer.Argument(help="What you want to search for.")],
    budget: Annotated[int | None, typer.Option(help="Credit budget for this plan.")] = None,
    project: Annotated[str | None, typer.Option(help="Project id.")] = None,
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Raw JSON output.")] = False,
) -> None:
    """Plan without executing. Costs no SerpApi credits."""
    with _client(base_url, api_key) as client:
        response = client.post(
            "/v1/plan",
            json={"intent": intent, "budget": budget, "project_id": project},
        )
    if response.status_code >= 400:
        _fail(response)
    payload = response.json()
    if as_json:
        console.print_json(json.dumps(payload))
        return
    console.print(Panel(intent, title="Intent", border_style="blue"))
    _render_plan(payload)


@app.command()
def search(
    intent: Annotated[str, typer.Argument(help="What you want to search for.")],
    budget: Annotated[int | None, typer.Option(help="Credit budget for this run.")] = None,
    project: Annotated[str | None, typer.Option(help="Project id.")] = None,
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Raw JSON output.")] = False,
) -> None:
    """Plan with cache-aware replanning, then execute."""
    with _client(base_url, api_key) as client:
        response = client.post(
            "/v1/search",
            json={"intent": intent, "budget": budget, "project_id": project},
        )
    if response.status_code >= 400:
        _fail(response)
    payload = response.json()
    if as_json:
        console.print_json(json.dumps(payload))
        return

    run = payload["run"]
    mode = payload.get("mode", {})
    console.print(
        Panel(
            intent + "\n\n[dim]" + str(mode.get("reason", "")) + "[/dim]",
            title="Intent  " + _mode_badge(str(mode.get("label", run.get("mode", "")))),
            border_style="blue",
        )
    )
    _render_plan(payload["plan"])

    console.print("")
    console.print(
        "  run "
        + run["id"]
        + "   status "
        + run["status"]
        + "   spent [bold]"
        + str(run["credits_spent"])
        + "[/bold]"
        + "   saved [bold green]"
        + str(run["credits_saved"])
        + "[/bold green]"
    )

    summary = (payload.get("results") or {}).get("summary") or {}
    items = summary.get("items") or []
    if items:
        console.print("")
        results = Table(show_header=True, header_style="bold", box=None)
        results.add_column("title")
        results.add_column("detail")
        for item in items[:8]:
            results.add_row(
                str(item.get("title") or "")[:70],
                str(item.get("snippet") or item.get("link") or item.get("price") or "")[:70],
            )
        console.print(results)


@app.command()
def replay(
    run_id: Annotated[str, typer.Argument(help="Run id to replay.")],
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
) -> None:
    """Re-run an intent against current cache state."""
    with _client(base_url, api_key) as client:
        response = client.post("/v1/runs/" + run_id + "/replay")
    if response.status_code >= 400:
        _fail(response)
    payload = response.json()
    console.print(
        Panel(
            "replaying " + run_id,
            title="Replay  " + _mode_badge(str(payload["mode"]["label"])),
            border_style="blue",
        )
    )
    _render_plan(payload["plan"])


@app.command()
def runs(
    limit: Annotated[int, typer.Option(help="How many runs to list.")] = 20,
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
) -> None:
    """List recent runs."""
    with _client(base_url, api_key) as client:
        response = client.get("/v1/runs", params={"limit": limit})
    if response.status_code >= 400:
        _fail(response)
    table = Table(show_header=True, header_style="bold", box=None)
    for column in ("run", "status", "mode", "naive", "marginal", "spent", "intent"):
        table.add_column(column)
    for row in response.json()["items"]:
        table.add_row(
            row["id"][:18],
            row["status"],
            row["mode"],
            str(row["naive_cost"]),
            str(row["marginal_cost"]),
            str(row["credits_spent"]),
            row["intent"][:52],
        )
    console.print(table)


@catalog_app.command("explore")
def catalog_explore(
    engine: Annotated[str, typer.Argument(help="Engine name, for example google_maps.")],
) -> None:
    """Show one engine: schema, dependencies, substitutes, costs."""
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    if not index.has(engine):
        console.print("[red]Unknown engine[/red] " + engine)
        raise typer.Exit(1)
    spec = index.get(engine)

    console.print(
        Panel(
            spec.purpose + "\n\n[dim]" + spec.docs_url + "[/dim]",
            title="[bold]" + spec.engine + "[/bold]  " + index.version,
            border_style="blue",
        )
    )
    console.print(
        "  cost "
        + str(spec.cost)
        + "   latency "
        + spec.latency_class
        + "   volatility "
        + spec.volatility_prior
        + "   PII risk "
        + spec.pii_risk
    )
    console.print("  tags " + ", ".join(spec.capability_tags))
    console.print("")

    required = Table(title="Required parameters", show_header=True, box=None)
    required.add_column("param")
    required.add_column("type")
    required.add_column("satisfied by")
    for name, requirement in spec.requires.items():
        required.add_row(
            name,
            requirement.type,
            "\n".join(requirement.satisfied_by) or "[dim]caller supplies[/dim]",
        )
    console.print(required)

    if spec.produces:
        produces = Table(title="Produces", show_header=True, box=None)
        produces.add_column("field")
        produces.add_column("feeds")
        for field, produced in spec.produces.items():
            produces.add_row(field, "\n".join(produced.feeds) or "[dim]terminal[/dim]")
        console.print(produces)

    substitutes = index.substitutes_for(engine)
    if substitutes:
        table = Table(title="Substitutes (engines that COMPETE)", show_header=True, box=None)
        table.add_column("engine")
        table.add_column("coverage")
        table.add_column("trade-off")
        for sub in substitutes:
            table.add_row(sub.substitute_engine, sub.coverage, sub.note[:90])
        console.print(table)
    elif spec.single_source_note:
        console.print(Panel(spec.single_source_note, title="No substitutes", border_style="yellow"))

    console.print("")
    console.print("  depends on  " + (", ".join(index.dependencies_of(engine)) or "nothing"))
    console.print("  feeds       " + (", ".join(index.dependents_of(engine)) or "nothing"))


@catalog_app.command("list")
def catalog_list(
    tag: Annotated[str | None, typer.Option(help="Filter by capability tag.")] = None,
) -> None:
    """List catalog engines."""
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    names = index.by_tag(tag) if tag else index.names()
    table = Table(show_header=True, header_style="bold", box=None)
    for column in ("engine", "cost", "volatility", "PII", "tags", "purpose"):
        table.add_column(column)
    for name in names:
        spec = index.get(name)
        table.add_row(
            name,
            str(spec.cost),
            spec.volatility_prior,
            spec.pii_risk,
            ", ".join(spec.capability_tags[:2]),
            spec.purpose[:54],
        )
    console.print(table)
    console.print("")
    console.print("  " + str(len(names)) + " engines   catalog " + index.version)


@catalog_app.command("paths")
def catalog_paths(
    engine: Annotated[str, typer.Argument(help="Target engine.")],
    params: Annotated[str, typer.Option(help="Comma-separated available params.")] = "q,location",
) -> None:
    """Every valid dependency chain that reaches an engine."""
    from app.services.catalog.graph import describe_path, find_paths
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    available = {p.strip() for p in params.split(",") if p.strip()}
    available |= {"q", "query", "text", "term", "search_query", "find_desc", "_nkw", "k", "p"}
    if "location" in available:
        available |= {"find_loc", "l"}
    paths = find_paths(index, engine, available_params=available)
    if not paths:
        console.print("[yellow]No valid path reaches " + engine + " from " + params + "[/yellow]")
        raise typer.Exit(1)
    for path in paths:
        console.print(
            "[bold]" + path.signature + "[/bold]  " + str(path.naive_cost) + " credits cold"
        )
        for line in describe_path(index, path):
            console.print("    [dim]" + line + "[/dim]")
        console.print("")


@catalog_app.command("validate")
def catalog_validate() -> None:
    """Lint the committed catalog."""
    from app.services.catalog.loader import load_catalog, validate_catalog

    index = load_catalog()
    problems = validate_catalog(index)
    stats = index.stats()
    console.print(
        "catalog "
        + index.version
        + "   engines "
        + str(stats["engines"])
        + "   dependency edges "
        + str(stats["edges"])
        + "   substitute edges "
        + str(stats["substitutes"])
        + "   tags "
        + str(stats["capability_tags"])
    )
    if not problems:
        console.print("[green]No problems found.[/green]")
        return
    for problem in problems:
        console.print("[yellow]  " + problem + "[/yellow]")
    raise typer.Exit(1)


@benchmark_app.command("run")
def benchmark_run(
    system: Annotated[
        str, typer.Option(help="serpflow | unaided_llm | embedding_only")
    ] = "serpflow",
    limit: Annotated[int | None, typer.Option(help="Run only the first N tasks.")] = None,
    write: Annotated[
        bool, typer.Option(help="Commit the report under fixtures/benchmark/results.")
    ] = True,
) -> None:
    """Run the routing benchmark. Makes real LLM calls; not part of CI."""
    from app.services.benchmark.service import BenchmarkHarness, write_report

    async def _run() -> dict[str, Any]:
        harness = BenchmarkHarness()
        return await harness.run(system=system, limit=limit, persist=False)

    report = asyncio.run(_run())
    console.print(
        Panel(
            "accuracy        [bold]" + str(round(report["accuracy"] * 100, 1)) + "%[/bold]\n"
            "engine accuracy " + str(round(report["engine_accuracy"] * 100, 1)) + "%\n"
            "param accuracy  " + str(round(report["param_accuracy"] * 100, 1)) + "%\n"
            "freshness       " + str(round(report["freshness_accuracy"] * 100, 1)) + "%\n"
            "tasks           " + str(report["task_count"]) + "\n"
            "catalog         " + report["catalog_version"] + "\n"
            "model           " + report["llm_model"],
            title="[bold]" + system + "[/bold]",
            border_style="blue",
        )
    )
    table = Table(title="By category", show_header=True, box=None)
    table.add_column("category")
    table.add_column("correct", justify="right")
    table.add_column("total", justify="right")
    table.add_column("accuracy", justify="right")
    for name, bucket in sorted(report["by_category"].items()):
        table.add_row(
            name,
            str(bucket["correct"]),
            str(bucket["total"]),
            str(round(bucket["accuracy"] * 100, 1)) + "%",
        )
    console.print(table)

    if report["failure_modes"]:
        console.print("")
        console.print("[bold]Failure modes[/bold]")
        for mode, count in sorted(report["failure_modes"].items(), key=lambda kv: -kv[1]):
            console.print("  " + mode.replace("_", " ") + "  " + str(count))
        console.print("")
        console.print("[dim]" + report["error_analysis"] + "[/dim]")

    if write:
        path = write_report(report)
        console.print("")
        console.print("report written to " + str(path))


@benchmark_app.command("compare")
def benchmark_compare(
    limit: Annotated[int | None, typer.Option(help="Run only the first N tasks.")] = None,
) -> None:
    """Run all three systems and print the comparison."""
    from app.services.benchmark.service import (
        SYSTEM_EMBEDDING,
        SYSTEM_SERPFLOW,
        SYSTEM_UNAIDED,
        BenchmarkHarness,
        write_report,
    )

    async def _run() -> list[dict[str, Any]]:
        harness = BenchmarkHarness()
        return [
            await harness.run(system=s, limit=limit, persist=False)
            for s in (SYSTEM_UNAIDED, SYSTEM_EMBEDDING, SYSTEM_SERPFLOW)
        ]

    reports = asyncio.run(_run())
    table = Table(show_header=True, header_style="bold", box=None)
    for column in ("system", "accuracy", "engines", "params", "freshness", "tasks"):
        table.add_column(column)
    for report in reports:
        table.add_row(
            report["system"],
            str(round(report["accuracy"] * 100, 1)) + "%",
            str(round(report["engine_accuracy"] * 100, 1)) + "%",
            str(round(report["param_accuracy"] * 100, 1)) + "%",
            str(round(report["freshness_accuracy"] * 100, 1)) + "%",
            str(report["task_count"]),
        )
        write_report(report)
    console.print(table)
    console.print("")
    console.print("[dim]Reports committed under backend/fixtures/benchmark/results.[/dim]")


@cache_app.command("stats")
def cache_stats(
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
) -> None:
    """Cache hit rate, layer distribution and guard rejections."""
    with _client(base_url, api_key) as client:
        response = client.get("/v1/cache")
    if response.status_code >= 400:
        _fail(response)
    data = response.json()
    console.print(
        "hit rate   [bold]" + str(round(data["hit_rate"] * 100, 1)) + "%[/bold]\n"
        "entries    " + str(data["entries"]) + "\n"
        "stored     " + str(round(data["bytes_stored"] / 1024, 1)) + " KiB"
    )
    table = Table(title="Layers", show_header=True, box=None)
    table.add_column("layer")
    table.add_column("lookups", justify="right")
    for layer, count in data["layers"].items():
        table.add_row(layer, str(count))
    console.print(table)
    guard = data.get("guard_rejections", {})
    if guard.get("total"):
        console.print("")
        console.print("[bold]Entity/numeral guard rejections[/bold] " + str(guard["total"]))
        for reason, count in (guard.get("by_reason") or {}).items():
            console.print("  " + reason + "  " + str(count))


@cache_app.command("invalidate")
def cache_invalidate(
    engine: Annotated[str | None, typer.Option(help="Only this engine.")] = None,
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
    api_key: Annotated[str | None, typer.Option(envvar="SERPFLOW_API_KEY")] = None,
) -> None:
    """Invalidate cache entries for the active project."""
    with _client(base_url, api_key) as client:
        response = client.post("/v1/cache/invalidate", json={"engine": engine})
    if response.status_code >= 400:
        _fail(response)
    console.print(response.json()["message"])


@app.command()
def health(
    base_url: Annotated[str, typer.Option(envvar="SERPFLOW_BASE_URL")] = DEFAULT_BASE_URL,
) -> None:
    """Check the service and all of its dependencies."""
    try:
        response = httpx.get(base_url.rstrip("/") + "/readyz", timeout=10.0)
    except httpx.HTTPError as exc:
        console.print("[red]unreachable[/red] " + base_url + " (" + type(exc).__name__ + ")")
        raise typer.Exit(1) from exc
    data = response.json()
    colour = {"ok": "green", "degraded": "yellow", "error": "red"}.get(data["status"], "white")
    console.print(
        "["
        + colour
        + "]"
        + data["status"].upper()
        + "[/"
        + colour
        + "]"
        + "   "
        + data["service"]
        + " "
        + data["version"]
        + "   mode "
        + data["mode"]
        + "   catalog "
        + data["catalog_version"]
    )
    for name, check in (data.get("checks") or {}).items():
        console.print("  " + name.ljust(16) + str(check))
    if data["status"] == "error":
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Print the SerpFlow version and the active catalog version."""
    from app import __version__
    from app.services.catalog.loader import load_catalog

    index = load_catalog()
    console.print("serpflow " + __version__ + "   catalog " + index.version)


if __name__ == "__main__":
    app()
