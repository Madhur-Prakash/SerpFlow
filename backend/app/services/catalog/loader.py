"""Load the committed YAML catalog into an in-memory index.

The committed files are the source of truth, not a runtime scrape (section 12).
This module reads them once per process, validates them, derives both edge
kinds, and exposes the index the planner retrieves against.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import CatalogError
from app.core.logging import get_logger
from app.services.catalog.schema import (
    COVERAGE_PENALTY,
    CatalogMeta,
    DependencyEdge,
    EngineSpec,
    SubstituteEdge,
    checksum,
    parse_field_ref,
)

log = get_logger("serpflow.catalog")

DATA_ROOT = Path(__file__).parent / "data"


@dataclass(slots=True)
class CatalogIndex:
    """Everything the planner needs about the catalog, resolved once."""

    version: str
    meta: CatalogMeta
    engines: dict[str, EngineSpec]
    edges: list[DependencyEdge]
    substitutes: list[SubstituteEdge]
    checksum: str

    _edges_from: dict[str, list[DependencyEdge]] = field(default_factory=dict)
    _edges_to: dict[str, list[DependencyEdge]] = field(default_factory=dict)
    _by_tag: dict[str, list[str]] = field(default_factory=dict)
    _subs_for: dict[str, list[SubstituteEdge]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for edge in self.edges:
            self._edges_from.setdefault(edge.from_engine, []).append(edge)
            self._edges_to.setdefault(edge.to_engine, []).append(edge)
        for name, spec in self.engines.items():
            for tag in spec.capability_tags:
                self._by_tag.setdefault(tag, []).append(name)
        for sub in self.substitutes:
            self._subs_for.setdefault(sub.engine, []).append(sub)

    # --- lookups ----------------------------------------------------------
    def get(self, engine: str) -> EngineSpec:
        spec = self.engines.get(engine)
        if spec is None:
            raise CatalogError(
                "Unknown engine: " + engine, details={"catalog_version": self.version}
            )
        return spec

    def has(self, engine: str) -> bool:
        return engine in self.engines

    def names(self) -> list[str]:
        return sorted(self.engines)

    def by_tag(self, tag: str) -> list[str]:
        return list(self._by_tag.get(tag, []))

    def tags(self) -> list[str]:
        return sorted(self._by_tag)

    def edges_from(self, engine: str) -> list[DependencyEdge]:
        return list(self._edges_from.get(engine, []))

    def edges_into(self, engine: str) -> list[DependencyEdge]:
        return list(self._edges_to.get(engine, []))

    def substitutes_for(self, engine: str) -> list[SubstituteEdge]:
        """Declared substitutes, plus any engine sharing a capability tag.

        Tag-sharing is what guarantees a competitor set even where an author
        forgot to declare one explicitly.
        """
        declared = {s.substitute_engine: s for s in self._subs_for.get(engine, [])}
        spec = self.engines.get(engine)
        if spec is None:
            return list(declared.values())
        for tag in spec.capability_tags:
            for peer in self._by_tag.get(tag, []):
                if peer == engine or peer in declared:
                    continue
                declared[peer] = SubstituteEdge(
                    engine=engine,
                    substitute_engine=peer,
                    coverage="partial",
                    note=(
                        "Shares the "
                        + tag.replace("_", " ")
                        + " capability. No explicit trade-off was authored, so "
                        + "coverage is assumed partial."
                    ),
                    shared_tags=[tag],
                    confidence_penalty=COVERAGE_PENALTY["partial"],
                )
        return sorted(declared.values(), key=lambda s: (s.coverage != "full", s.substitute_engine))

    def dependents_of(self, engine: str) -> list[str]:
        return sorted({e.to_engine for e in self.edges_from(engine)})

    def dependencies_of(self, engine: str) -> list[str]:
        return sorted({e.from_engine for e in self.edges_into(engine)})

    def producers_for(self, engine: str, param: str) -> list[DependencyEdge]:
        return [e for e in self.edges_into(engine) if e.satisfies_param == param]

    def stats(self) -> dict[str, int]:
        return {
            "engines": len(self.engines),
            "edges": len(self.edges),
            "substitutes": len(self.substitutes),
            "capability_tags": len(self._by_tag),
        }


def _read_yaml(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except Exception as exc:  # pragma: no cover - surfaced as CatalogError
        raise CatalogError("Failed to read catalog file " + path.name + ": " + str(exc)) from exc


def _derive_edges(engines: dict[str, EngineSpec]) -> list[DependencyEdge]:
    """Derive typed dependency edges from both directions of the declaration.

    ``produces[*].feeds`` and ``requires[*].satisfied_by`` are two views of the
    same relationship. Authors maintain whichever is natural; both are read and
    the union is deduplicated, so a one-sided declaration still produces a
    usable edge.
    """
    edges: dict[str, DependencyEdge] = {}

    def remember(edge: DependencyEdge) -> None:
        """Keep the widest declaration of a relationship.

        One engine can satisfy the same downstream parameter from several
        fields - ``google_maps`` yields ``data_id`` from both
        ``local_results[]`` and ``place_results``. They are the same edge, but
        the list-valued field carries the fan-out that drives cost projection,
        so the richer hint wins rather than whichever was parsed last.
        """
        existing = edges.get(edge.key)
        if existing is None or edge.fan_out_hint > existing.fan_out_hint:
            edges[edge.key] = edge

    for name, spec in engines.items():
        # direction 1: produces[...].feeds -> "<engine>.<param>"
        for field_path, produced in spec.produces.items():
            for target in produced.feeds:
                parsed = parse_field_ref(target)
                if parsed is None:
                    continue
                to_engine, param = parsed
                if to_engine not in engines:
                    log.warning("catalog edge target missing", extra={"target": target})
                    continue
                edge = DependencyEdge(
                    from_engine=name,
                    to_engine=to_engine,
                    produces_field=name + "." + field_path,
                    satisfies_param=param,
                    param_type=produced.type,
                    fan_out_hint=max(1, produced.fan_out_hint),
                )
                remember(edge)

        # direction 2: requires[param].satisfied_by -> "<engine>.<field path>"
        for param, requirement in spec.requires.items():
            for source in requirement.satisfied_by:
                parsed = parse_field_ref(source)
                if parsed is None:
                    continue
                from_engine, field_path = parsed
                if from_engine not in engines:
                    log.warning("catalog edge source missing", extra={"source": source})
                    continue
                producer = engines[from_engine].produces.get(field_path)
                edge = DependencyEdge(
                    from_engine=from_engine,
                    to_engine=name,
                    produces_field=source,
                    satisfies_param=param,
                    param_type=requirement.type,
                    fan_out_hint=max(1, producer.fan_out_hint if producer else 1),
                )
                remember(edge)

    return sorted(edges.values(), key=lambda e: (e.from_engine, e.to_engine, e.satisfies_param))


def _derive_substitutes(engines: dict[str, EngineSpec]) -> list[SubstituteEdge]:
    out: list[SubstituteEdge] = []
    for name, spec in engines.items():
        for sub in spec.substitutes:
            if sub.engine not in engines:
                log.warning(
                    "catalog substitute target missing",
                    extra={"engine": name, "substitute": sub.engine},
                )
                continue
            shared = sorted(set(spec.capability_tags) & set(engines[sub.engine].capability_tags))
            out.append(
                SubstituteEdge(
                    engine=name,
                    substitute_engine=sub.engine,
                    coverage=sub.coverage,
                    note=sub.note,
                    shared_tags=shared,
                    confidence_penalty=COVERAGE_PENALTY[sub.coverage],
                )
            )
    return out


def validate_catalog(index: CatalogIndex) -> list[str]:
    """Author-time lint. Returned problems are warnings, not hard failures,
    except where ``load_catalog`` already refused to build the index."""
    problems: list[str] = []
    for name, spec in index.engines.items():
        if not spec.capability_tags:
            problems.append(name + ": no capability_tags, so it can never be a substitute")
        if not spec.substitutes and not spec.single_source_note:
            problems.append(
                name
                + ": no substitutes and no single_source_note. Section 11 requires one or the"
                + " other so the planner can explain why no alternative exists."
            )
        if not spec.purpose:
            problems.append(name + ": missing purpose")
        if not spec.requires:
            problems.append(name + ": declares no required parameters")
        for param, requirement in spec.requires.items():
            for ref in requirement.satisfied_by:
                if parse_field_ref(ref) is None:
                    problems.append(name + "." + param + ": malformed satisfied_by ref " + ref)
    return problems


def _describe(exc: PydanticValidationError, filename: str, engine: str) -> str:
    """Turn a pydantic error into one line an operator can act on."""
    problems = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        problems.append((location or "<root>") + ": " + str(error.get("msg", "invalid")))
    detail = "; ".join(problems)
    if len(exc.errors()) > 3:
        detail += " (and " + str(len(exc.errors()) - 3) + " more)"
    return (
        "Engine '" + engine + "' in " + filename + " does not match the catalog schema - " + detail
    )


def _load_version(version_dir: Path) -> CatalogIndex:
    meta_path = version_dir / "_meta.yaml"
    if not meta_path.exists():
        raise CatalogError("Catalog version directory has no _meta.yaml: " + str(version_dir))
    try:
        meta = CatalogMeta.model_validate(_read_yaml(meta_path))
    except PydanticValidationError as exc:
        raise CatalogError(_describe(exc, meta_path.name, "_meta")) from exc

    engines: dict[str, EngineSpec] = {}
    for path in sorted(version_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        payload = _read_yaml(path)
        for raw in payload.get("engines", []) or []:
            try:
                spec = EngineSpec.model_validate(raw)
            except PydanticValidationError as exc:
                # A raw pydantic error here reaches the API as a bare 500 with
                # no hint, which is a long afternoon for whoever has to work
                # out that one engine has a field the model does not know. Name
                # the file, the engine and the field instead.
                raise CatalogError(
                    _describe(exc, path.name, str(raw.get("engine", "<unnamed>")))
                ) from exc
            if spec.engine in engines:
                raise CatalogError("Duplicate engine in catalog: " + spec.engine)
            engines[spec.engine] = spec

    if not engines:
        raise CatalogError("Catalog version " + meta.version + " contains no engines")

    edges = _derive_edges(engines)
    substitutes = _derive_substitutes(engines)
    digest = checksum(
        {
            "engines": {k: v.model_dump() for k, v in sorted(engines.items())},
            "version": meta.version,
        }
    )
    index = CatalogIndex(
        version=meta.version,
        meta=meta,
        engines=engines,
        edges=edges,
        substitutes=substitutes,
        checksum=digest,
    )
    for problem in validate_catalog(index):
        log.warning("catalog lint", extra={"problem": problem, "catalog_version": index.version})
    return index


def available_versions() -> list[str]:
    if not DATA_ROOT.exists():
        return []
    return sorted(p.name for p in DATA_ROOT.iterdir() if p.is_dir() and not p.name.startswith("_"))


@functools.lru_cache(maxsize=8)
def load_catalog(version_dir: str | None = None) -> CatalogIndex:
    """Load (and memoise) a catalog version. ``None`` means the newest."""
    versions = available_versions()
    if not versions:
        raise CatalogError("No catalog versions found under " + str(DATA_ROOT))
    chosen = version_dir or versions[-1]
    if chosen not in versions:
        raise CatalogError("Unknown catalog version directory: " + chosen)
    index = _load_version(DATA_ROOT / chosen)
    log.info(
        "catalog loaded",
        extra={
            "event": "catalog.loaded",
            "catalog_version": index.version,
            **index.stats(),
        },
    )
    return index


def reload_catalog() -> CatalogIndex:
    load_catalog.cache_clear()
    return load_catalog()


def iter_specs(index: CatalogIndex, engines: Iterable[str]):
    for name in engines:
        if index.has(name):
            yield index.get(name)


__all__ = [
    "DATA_ROOT",
    "CatalogIndex",
    "available_versions",
    "iter_specs",
    "load_catalog",
    "reload_catalog",
    "validate_catalog",
]
