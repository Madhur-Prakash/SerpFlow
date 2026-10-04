"""Resolve the planning adapter for one organization (bring-your-own-key).

Which adapter plans a search is a property of the organization, not of the
deployment. An organization that has supplied a Groq key gets Groq; one that
has not gets the deterministic planner. Nothing here reaches for a key that
belongs to the deployment.

``LLM_PROVIDER`` and ``GROQ_API_KEY`` remain as a self-hosting fallback: they
apply only when the organization has brought no key of its own, which on the
hosted platform is never, because no such key is set there. A self-hoster
running SerpFlow for themselves can still point the whole instance at one key
rather than attaching a credential to every organization they create.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decrypt_credential
from app.db.models.identity import Project
from app.integrations.llm import LLMAdapter, get_llm
from app.integrations.llm.groq import GroqLLMAdapter
from app.services.credentials.providers import GROQ

log = get_logger("serpflow.credentials.llm")


async def resolve_llm(
    session: AsyncSession,
    *,
    org_id: str,
    project: Project | None = None,
) -> LLMAdapter:
    """The adapter this organization's plans should run through.

    Decryption happens here and the plaintext is handed straight to the
    adapter, which holds it for the lifetime of one request. It is never
    written to a column, a log or a response - the same rule the SerpApi
    credential follows in ``ExecutorService``.
    """
    # Imported late: CredentialService imports this module's siblings, and at
    # module scope the two would import each other.
    from app.services.credentials.service import CredentialService

    service = CredentialService(session, org_id=org_id)
    credential = await service.resolve_optional(project, GROQ)

    if credential is not None:
        try:
            secret = decrypt_credential(credential.ciphertext, credential.encrypted_dek)
        except Exception:
            # A credential that cannot be decrypted - a rotated KEK, a
            # corrupted row - must not take planning down with it. The
            # deterministic planner answers instead, and the plan says so.
            log.warning(
                "groq credential could not be decrypted, planning deterministically",
                extra={"event": "llm.credential_undecryptable", "credential_id": credential.id},
            )
            return get_llm("mock")
        return GroqLLMAdapter(api_key=secret)

    # No key of this organization's own. On the hosted platform this is where
    # every organization lands until it brings one.
    return get_llm()


__all__ = ["resolve_llm"]
