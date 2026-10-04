"""Credential providers.

SerpFlow is bring-your-own-key. An organization supplies the keys for the
upstream services it uses, and this module is the list of which services those
are plus the one cheap call that proves a key works.

The vault itself (envelope encryption, rotation, grace windows, fingerprints)
is already provider-agnostic: ``UpstreamCredential`` has carried a ``provider``
column since the first migration. What was hardcoded was validation, which
called SerpApi for every credential regardless of what the key was for. This
registry replaces that with one entry per provider.

Adding a provider means adding a ``Provider`` here and nothing else. In
particular it needs no schema change and no new table - which is the point of
having stored ``provider`` from the start.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings

SERPAPI = "serpapi"
GROQ = "groq"


class Validator(Protocol):
    async def __call__(self, secret: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Provider:
    """One upstream service an organization brings a key for."""

    id: str
    label: str
    #: What the key is used for, in the words shown next to the input.
    purpose: str
    #: Where to get one. Rendered as a link in the console.
    console_url: str
    #: A hint, not a validation rule - key formats change without notice and
    #: refusing a key on a prefix guess would be a support ticket, not safety.
    key_hint: str
    #: What happens when an organization has not supplied this key.
    absent_behaviour: str
    #: Whether a search can run at all without it.
    required: bool
    validate: Validator


async def _validate_serpapi(secret: str) -> dict[str, Any]:
    # Imported here: app.integrations.serpapi imports settings, and importing
    # it at module scope makes this module part of that cycle.
    from app.integrations.serpapi import SerpApiClient

    return await SerpApiClient(secret).validate()


async def _validate_groq(secret: str) -> dict[str, Any]:
    """List models - the cheapest authenticated call Groq exposes.

    It consumes no tokens, so validating a key costs the organization nothing.
    """
    url = settings.groq_base_url.rstrip("/") + "/models"
    async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
        response = await client.get(url, headers={"Authorization": "Bearer " + secret})
    if response.status_code == 401:
        raise PermissionError("Groq rejected this key.")
    response.raise_for_status()
    body = response.json()
    models = [m.get("id") for m in body.get("data", []) if isinstance(m, dict)]
    return {
        "models_available": len(models),
        # Surfaced so an operator can see whether the configured model is one
        # this key may actually call - entitlements differ between accounts.
        "configured_model_available": settings.groq_model in models,
    }


PROVIDERS: dict[str, Provider] = {
    SERPAPI: Provider(
        id=SERPAPI,
        label="SerpApi",
        purpose="Runs the searches. Every credit SerpFlow reports spent is spent here.",
        console_url="https://serpapi.com/manage-api-key",
        key_hint="64 hexadecimal characters",
        absent_behaviour=(
            "Searches cannot execute live. Planning, replay and any test API key "
            "still work and cost nothing."
        ),
        required=True,
        validate=_validate_serpapi,
    ),
    GROQ: Provider(
        id=GROQ,
        label="Groq",
        purpose=(
            "Chooses which engines answer an intent. Optional: without it the "
            "deterministic planner decides instead."
        ),
        console_url="https://console.groq.com/keys",
        key_hint="starts with gsk_",
        absent_behaviour=(
            "Planning uses the deterministic selector, which costs nothing and "
            "returns the same plan for the same intent every time."
        ),
        required=False,
        validate=_validate_groq,
    ),
}

PROVIDER_IDS = tuple(PROVIDERS)


def get_provider(provider_id: str) -> Provider:
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(
            "Unknown credential provider " + repr(provider_id) + ". "
            "Expected one of " + ", ".join(PROVIDER_IDS) + "."
        ) from None


__all__ = ["GROQ", "PROVIDER_IDS", "PROVIDERS", "SERPAPI", "Provider", "get_provider"]
