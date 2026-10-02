"""Typed dependency graph and multi-hop path finding (section 13, stage D).

The LLM does not invent chains. It picks target capabilities; this module
computes which chains are actually *valid* by walking typed edges backwards
from a target until every required parameter is either supplied by the caller
or produced by an upstream engine.

That distinction is why the planner can reach
``google_maps_contributor_reviews`` - an engine with effectively zero usage in
the SerpApi ecosystem - without any model having seen it chained before.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.catalog.loader import CatalogIndex
from app.services.catalog.schema import DependencyEdge

MAX_PATHS_PER_TARGET = 12
MAX_COMBINATIONS = 24
# A single step never fans out past this, whatever the catalog hints.
MAX_FAN_OUT = 200


@dataclass(slots=True)
class Binding:
    """How one required parameter of one step gets its value."""

    param: str
    # "root": the caller supplied it. "chain": an upstream step produces it.
    source: str
    from_engine: str | None = None
    from_step: int | None = None
    from_field: str | None = None
    value: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "param": self.param,
            "source": self.source,
            "from_engine": self.from_engine,
            "from_step": self.from_step,
            "from_field": self.from_field,
            "value": self.value,
        }


@dataclass(slots=True)
class PathStep:
    engine: str
    depends_on: list[int] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    fan_out: int = 1
    cost: int = 1

    @property
    def total_cost(self) -> int:
        return self.cost * max(1, self.fan_out)

    def clone(self) -> PathStep:
        return PathStep(
            engine=self.engine,
            depends_on=list(self.depends_on),
            bindings=[
                Binding(
                    param=b.param,
                    source=b.source,
                    from_engine=b.from_engine,
                    from_step=b.from_step,
                    from_field=b.from_field,
                    value=b.value,
                )
                for b in self.bindings
            ],
            fan_out=self.fan_out,
            cost=self.cost,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "depends_on": list(self.depends_on),
            "bindings": [b.to_dict() for b in self.bindings],
            "fan_out": self.fan_out,
            "cost": self.cost,
        }


@dataclass(slots=True)
class EnginePath:
    """An ordered, dependency-respecting chain of steps."""

    steps: list[PathStep]
    target: str

    @property
    def engines(self) -> list[str]:
        return [s.engine for s in self.steps]

    @property
    def hops(self) -> int:
        return len(self.steps)

    @property
    def naive_cost(self) -> int:
        return sum(s.total_cost for s in self.steps)

    @property
    def signature(self) -> str:
        return ">".join(self.engines)

    def clone(self) -> EnginePath:
        return EnginePath(steps=[s.clone() for s in self.steps], target=self.target)

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "engines": self.engines,
            "hops": self.hops,
            "naive_cost": self.naive_cost,
            "steps": [s.to_dict() for s in self.steps],
        }


def _reindex(steps: list[PathStep]) -> list[PathStep]:
    """Re-point every chain binding at its producer's current position.

    An engine appears at most once per chain, so engine name is a stable
    handle across merges while positional indices are not.
    """
    position = {s.engine: i for i, s in enumerate(steps)}
    for i, step in enumerate(steps):
        depends: list[int] = []
        for binding in step.bindings:
            if binding.source != "chain" or binding.from_engine is None:
                continue
            idx = position.get(binding.from_engine)
            if idx is None or idx >= i:
                continue
            binding.from_step = idx
            depends.append(idx)
        step.depends_on = sorted(set(depends))
    return steps


def _merge(prefix: list[PathStep], upstream: list[PathStep]) -> list[PathStep]:
    """Union two partial chains, reusing a shared step rather than paying twice.

    Two branches of a fan-in often both need ``google_maps``; executing it once
    is both cheaper and correct, so the merge is a set union over engines.
    """
    merged = [s.clone() for s in prefix]
    present = {s.engine for s in merged}
    for step in upstream:
        if step.engine in present:
            continue
        merged.append(step.clone())
        present.add(step.engine)
    return _reindex(merged)


def _dedupe_producers(index: CatalogIndex, engine: str, group: list[str]) -> list[DependencyEdge]:
    """All edges that can satisfy any member of an alternative group."""
    out: list[DependencyEdge] = []
    seen: set[str] = set()
    for member in group:
        for edge in index.producers_for(engine, member):
            if edge.key in seen:
                continue
            seen.add(edge.key)
            out.append(edge)
    # Prefer cheap, low-fan-out producers first so the cheapest chains surface.
    out.sort(key=lambda e: (index.get(e.from_engine).cost, e.fan_out_hint, e.from_engine))
    return out


def find_paths(
    index: CatalogIndex,
    target: str,
    *,
    available_params: set[str] | None = None,
    max_hops: int = 4,
) -> list[EnginePath]:
    """Every valid chain that ends at ``target``.

    ``available_params`` are the parameter names stage C already bound from the
    intent itself (``q``, ``location``, dates). Anything outside that set must
    be produced by an upstream engine, or the path is discarded - the planner
    never guesses a value it cannot source.
    """
    available = set(available_params or set())
    if not index.has(target):
        return []

    memo: dict[tuple[str, frozenset[str]], list[list[PathStep]]] = {}

    def resolve(engine: str, depth: int, visiting: frozenset[str]) -> list[list[PathStep]]:
        if engine in visiting or depth > max_hops:
            return []
        cache_key = (engine, visiting)
        cached = memo.get(cache_key)
        if cached is not None:
            return [[s.clone() for s in chain] for chain in cached]

        spec = index.engines.get(engine)
        if spec is None:
            return []

        root_bindings: list[Binding] = []
        chain_groups: list[list[DependencyEdge]] = []

        for group in spec.required_groups():
            # Only a genuinely caller-suppliable parameter counts as supplied.
            # Parameter names collide across engines: google.q is the user's
            # query, while google_scholar_cite.q is a Scholar result_id. Taking
            # the name at face value would make the second look satisfied and
            # the chain that actually produces it would never be built.
            supplied = next(
                (
                    member
                    for member in group
                    if member in available and spec.requires[member].is_root_satisfiable
                ),
                None,
            )
            if supplied is not None:
                root_bindings.append(Binding(param=supplied, source="root"))
                continue
            producers = _dedupe_producers(index, engine, group)
            if not producers:
                # Nothing in the catalog can produce this and the caller did not
                # supply it, so no valid chain ends here.
                memo[cache_key] = []
                return []
            chain_groups.append(producers)

        if not chain_groups:
            chain = [PathStep(engine=engine, bindings=root_bindings, cost=spec.cost, fan_out=1)]
            memo[cache_key] = [[s.clone() for s in chain]]
            return chain and [chain] or []

        combos: list[tuple[list[PathStep], list[Binding]]] = [([], list(root_bindings))]
        for producers in chain_groups:
            next_combos: list[tuple[list[PathStep], list[Binding]]] = []
            for edge in producers:
                for upstream in resolve(edge.from_engine, depth + 1, visiting | {engine}):
                    for prefix_steps, bindings in combos:
                        merged = _merge(prefix_steps, upstream)
                        next_combos.append(
                            (
                                merged,
                                [
                                    *bindings,
                                    Binding(
                                        param=edge.satisfies_param,
                                        source="chain",
                                        from_engine=edge.from_engine,
                                        from_field=edge.produces_field,
                                    ),
                                ],
                            )
                        )
                        if len(next_combos) >= MAX_COMBINATIONS:
                            break
                    if len(next_combos) >= MAX_COMBINATIONS:
                        break
                if len(next_combos) >= MAX_COMBINATIONS:
                    break
            if not next_combos:
                memo[cache_key] = []
                return []
            combos = next_combos

        chains: list[list[PathStep]] = []
        for prefix_steps, bindings in combos:
            step = PathStep(engine=engine, bindings=bindings, cost=spec.cost)
            full = _reindex([*(s.clone() for s in prefix_steps), step])
            _apply_fan_out(index, full)
            chains.append(full)

        memo[cache_key] = [[s.clone() for s in chain] for chain in chains]
        return chains

    raw = resolve(target, 0, frozenset())

    best: dict[str, EnginePath] = {}
    for chain in raw:
        if not chain:
            continue
        path = EnginePath(steps=chain, target=target)
        current = best.get(path.signature)
        if current is None or path.naive_cost < current.naive_cost:
            best[path.signature] = path

    ordered = sorted(best.values(), key=lambda p: (p.naive_cost, p.hops, p.signature))
    return ordered[:MAX_PATHS_PER_TARGET]


def _apply_fan_out(index: CatalogIndex, steps: list[PathStep]) -> None:
    """Propagate fan-out down the chain.

    A step that consumes a list-valued upstream field runs once per element, so
    fan-out multiplies along the chain. This is what makes the reference demo's
    101-credit full-scale projection a computed number rather than a guess:

        google_maps                           1 call           1 credit
        google_maps_reviews x 20              20 calls        20 credits
        google_maps_contributor_reviews x 80  80 calls        80 credits
    """
    for i, step in enumerate(steps):
        fan = 1
        for binding in step.bindings:
            if binding.source != "chain" or binding.from_step is None:
                continue
            producer = steps[binding.from_step]
            edge = _edge_between(index, producer.engine, step.engine, binding.param)
            hint = edge.fan_out_hint if edge else 1
            fan = max(fan, producer.fan_out * max(1, hint))
        step.fan_out = min(MAX_FAN_OUT, max(1, fan))
        _ = i


def _edge_between(
    index: CatalogIndex, from_engine: str, to_engine: str, param: str
) -> DependencyEdge | None:
    for edge in index.producers_for(to_engine, param):
        if edge.from_engine == from_engine:
            return edge
    return None


def apply_fan_out_caps(path: EnginePath, caps: dict[int, int]) -> EnginePath:
    """Copy of ``path`` with per-step fan-out capped (section 16 reductions)."""
    out = path.clone()
    for i, step in enumerate(out.steps):
        if i in caps:
            step.fan_out = max(1, min(step.fan_out, caps[i]))
    return out


def reachable_targets(index: CatalogIndex, root_params: set[str], max_hops: int = 4) -> list[str]:
    """Engines reachable from a set of caller-supplied parameters. Backs the
    Catalog Explorer reachability view and benchmark sanity checks."""
    return [
        name
        for name in index.names()
        if find_paths(index, name, available_params=root_params, max_hops=max_hops)
    ]


def describe_path(index: CatalogIndex, path: EnginePath) -> list[str]:
    """Human-readable chain explanation for the Plan Inspector."""
    lines: list[str] = []
    for i, step in enumerate(path.steps):
        chained = [b for b in step.bindings if b.source == "chain"]
        if not chained:
            lines.append(
                str(i + 1) + ". " + step.engine + " - entry point, parameters supplied directly"
            )
            continue
        parts = [
            b.param + " from " + (b.from_field or "upstream")
            for b in chained
            if b.from_field or b.param
        ]
        suffix = " (x" + str(step.fan_out) + ")" if step.fan_out > 1 else ""
        lines.append(str(i + 1) + ". " + step.engine + suffix + " - " + "; ".join(parts))
    _ = index
    return lines


__all__ = [
    "MAX_COMBINATIONS",
    "MAX_FAN_OUT",
    "MAX_PATHS_PER_TARGET",
    "Binding",
    "EnginePath",
    "PathStep",
    "apply_fan_out_caps",
    "describe_path",
    "find_paths",
    "reachable_targets",
]
