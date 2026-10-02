"""Catalog Explorer API (section 49).

Substitute relationships are returned separately from dependency edges so the
UI can render them as visually distinct things - they mean different things:
dependency edges describe how engines CHAIN, substitutes describe how they
COMPETE.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import require
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.schemas.planning import (
    CatalogEdgeView,
    CatalogEngineView,
    CatalogResponse,
    SubstituteView,
)
from app.services.auth.service import Principal
from app.services.catalog.graph import find_paths
from app.services.catalog.loader import available_versions, load_catalog

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _engine_view(index, name: str) -> CatalogEngineView:
    spec = index.get(name)
    return CatalogEngineView(
        engine=spec.engine,
        purpose=spec.purpose,
        capability_tags=spec.capability_tags,
        substitutes=[
            SubstituteView(
                engine=s.substitute_engine,
                coverage=s.coverage,
                note=s.note,
                shared_tags=s.shared_tags,
            )
            for s in index.substitutes_for(name)
        ],
        single_source_note=spec.single_source_note,
        requires={k: v.model_dump() for k, v in spec.requires.items()},
        optional=spec.optional,
        produces={k: v.model_dump() for k, v in spec.produces.items()},
        cost=spec.cost,
        latency_class=spec.latency_class,
        volatility_prior=spec.volatility_prior,
        locale_sensitive=spec.locale_sensitive,
        pii_risk=spec.pii_risk,
        docs_url=spec.docs_url,
        depends_on=index.dependencies_of(name),
        dependents=index.dependents_of(name),
    )


@router.get("", response_model=CatalogResponse)
async def get_catalog(
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
    version: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> CatalogResponse:
    index = load_catalog(version)
    names = index.names()
    if tag:
        names = [n for n in names if tag in index.get(n).capability_tags]
    if search:
        needle = search.lower()
        names = [n for n in names if needle in index.get(n).search_text()]

    return CatalogResponse(
        version=index.version,
        released=index.meta.released,
        source=index.meta.source,
        notes=index.meta.notes,
        engine_count=len(index.engines),
        edge_count=len(index.edges),
        substitute_count=len(index.substitutes),
        capability_tags=index.meta.capability_tags,
        engines=[_engine_view(index, n) for n in names],
        edges=[
            CatalogEdgeView(
                from_engine=e.from_engine,
                to_engine=e.to_engine,
                produces_field=e.produces_field,
                satisfies_param=e.satisfies_param,
                param_type=e.param_type,
                fan_out_hint=e.fan_out_hint,
            )
            for e in index.edges
        ],
        substitute_edges=[
            {
                "engine": s.engine,
                "substitute_engine": s.substitute_engine,
                "coverage": s.coverage,
                "note": s.note,
                "shared_tags": s.shared_tags,
            }
            for s in index.substitutes
        ],
    )


@router.get("/versions")
async def list_versions(
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
) -> dict:
    versions = []
    for directory in available_versions():
        index = load_catalog(directory)
        versions.append(
            {
                "directory": directory,
                "version": index.version,
                "released": index.meta.released,
                "checksum": index.checksum,
                **index.stats(),
            }
        )
    return {"versions": versions, "active": load_catalog().version}


@router.get("/engines/{engine}", response_model=CatalogEngineView)
async def get_engine(
    engine: str,
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
    version: Annotated[str | None, Query()] = None,
) -> CatalogEngineView:
    index = load_catalog(version)
    if not index.has(engine):
        raise NotFoundError("Engine " + engine + " is not in catalog " + index.version + ".")
    return _engine_view(index, engine)


@router.get("/engines/{engine}/paths")
async def engine_paths(
    engine: str,
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
    version: Annotated[str | None, Query()] = None,
    params: Annotated[str, Query(description="Comma-separated available parameters")] = "q",
) -> dict:
    """Every valid chain that reaches ``engine`` from the supplied parameters.

    This is the graph the Plan Inspector draws, exposed directly so the Catalog
    Explorer can show what is reachable before anything is planned.
    """
    index = load_catalog(version)
    if not index.has(engine):
        raise NotFoundError("Engine " + engine + " is not in catalog " + index.version + ".")
    available = {p.strip() for p in params.split(",") if p.strip()}
    available |= {
        "q",
        "query",
        "text",
        "search_query",
        "term",
        "p",
        "k",
        "_nkw",
        "find_desc",
        "mauthors",
    }
    paths = find_paths(index, engine, available_params=available)
    return {
        "engine": engine,
        "catalog_version": index.version,
        "available_params": sorted(available),
        "path_count": len(paths),
        "paths": [p.to_dict() for p in paths],
    }


@router.get("/tags")
async def list_tags(
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
) -> dict:
    """Capability tags and their members. Engines sharing a tag compete."""
    index = load_catalog()
    return {
        "catalog_version": index.version,
        "tags": [
            {
                "tag": tag,
                "description": index.meta.capability_tags.get(tag, ""),
                "engines": index.by_tag(tag),
                "competing": len(index.by_tag(tag)) > 1,
            }
            for tag in index.tags()
        ],
    }


@router.get("/graph")
async def catalog_graph(
    principal: Annotated[Principal, Depends(require(Permission.CATALOG_READ))],
    version: Annotated[str | None, Query()] = None,
) -> dict:
    """Nodes plus both edge kinds, ready for the GSAP dependency graph."""
    index = load_catalog(version)
    return {
        "catalog_version": index.version,
        "nodes": [
            {
                "id": name,
                "purpose": index.get(name).purpose,
                "tags": index.get(name).capability_tags,
                "cost": index.get(name).cost,
                "pii_risk": index.get(name).pii_risk,
                "volatility_prior": index.get(name).volatility_prior,
                "latency_class": index.get(name).latency_class,
                "in_degree": len(index.edges_into(name)),
                "out_degree": len(index.edges_from(name)),
            }
            for name in index.names()
        ],
        "dependency_edges": [
            {
                "source": e.from_engine,
                "target": e.to_engine,
                "param": e.satisfies_param,
                "field": e.produces_field,
                "fan_out_hint": e.fan_out_hint,
                "kind": "dependency",
            }
            for e in index.edges
        ],
        "substitute_edges": [
            {
                "source": s.engine,
                "target": s.substitute_engine,
                "coverage": s.coverage,
                "note": s.note,
                "kind": "substitute",
            }
            for s in index.substitutes
        ],
    }


__all__ = ["router"]
