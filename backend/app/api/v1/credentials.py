"""Upstream credentials (sections 23-27).

SerpFlow is bring-your-own-key. Every key an organization needs is stored
here, encrypted per credential, and nothing in the platform falls back to
a key belonging to the deployment.

Every response here is built by ``credentials.public_view``, which has no code
path that could emit the secret. The request model accepts it; no response
model has a field for it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import SessionDep, client_ip, require
from app.core.permissions import Permission
from app.schemas.common import OkResponse
from app.schemas.identity import (
    CredentialCreate,
    CredentialResponse,
    CredentialRotate,
    ProviderView,
)
from app.services.audit.service import AuditService
from app.services.auth.service import Principal
from app.services.credentials.providers import PROVIDERS
from app.services.credentials.service import CredentialService, public_view
from app.workers import kafka

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_READ))],
) -> list[CredentialResponse]:
    rows = await CredentialService(session, org_id=principal.org_id).list()
    return [CredentialResponse(**public_view(r)) for r in rows]


@router.get("/providers", response_model=list[ProviderView])
async def list_providers(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_READ))],
) -> list[ProviderView]:
    """Which keys this organization needs to bring, and whether it has.

    The console builds its credential screen from this, so adding a provider
    to the registry adds it to the interface without a frontend change.
    """
    service = CredentialService(session, org_id=principal.org_id)
    rows = await service.list()
    have = {r.provider for r in rows if r.revoked_at is None}
    return [
        ProviderView(
            id=spec.id,
            label=spec.label,
            purpose=spec.purpose,
            console_url=spec.console_url,
            key_hint=spec.key_hint,
            absent_behaviour=spec.absent_behaviour,
            required=spec.required,
            configured=spec.id in have,
        )
        for spec in PROVIDERS.values()
    ]


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    payload: CredentialCreate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_WRITE))],
) -> CredentialResponse:
    """Encrypt, validate with one cheap upstream call, store the fingerprint.

    The plaintext key exists only inside this handler's local scope and inside
    the vault's encryption call. It is never written to the response, the audit
    log or any log sink.
    """
    service = CredentialService(session, org_id=principal.org_id)
    credential = await service.create(
        name=payload.name,
        secret=payload.api_key,
        provider=payload.provider,
        project_id=payload.project_id,
        validate=payload.validate_now,
        set_as_org_default=payload.set_as_org_default,
    )
    await AuditService(session, org_id=principal.org_id).record(
        action="credential.created",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="credential",
        resource_id=credential.id,
        project_id=payload.project_id,
        # Fingerprint only. It is sha256(key)[:8] and non-reversible.
        after={
            "name": credential.name,
            "provider": credential.provider,
            "fingerprint": credential.fingerprint,
        },
        ip=client_ip(request),
    )
    return CredentialResponse(**public_view(credential))


@router.post("/{credential_id}/validate", response_model=CredentialResponse)
async def validate_credential(
    credential_id: str,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_WRITE))],
) -> CredentialResponse:
    service = CredentialService(session, org_id=principal.org_id)
    credential = await service.get(credential_id)
    await service.validate(credential)
    return CredentialResponse(**public_view(credential))


@router.post("/{credential_id}/rotate", response_model=CredentialResponse)
async def rotate_credential(
    credential_id: str,
    payload: CredentialRotate,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_ROTATE))],
) -> CredentialResponse:
    """Encrypt, validate, atomically swap, grace the old, then destroy it."""
    service = CredentialService(session, org_id=principal.org_id)
    replacement = await service.rotate(
        credential_id, new_secret=payload.api_key, grace_minutes=payload.grace_minutes
    )
    await AuditService(session, org_id=principal.org_id).record(
        action="credential.rotated",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="credential",
        resource_id=replacement.id,
        before={"credential_id": credential_id},
        after={
            "credential_id": replacement.id,
            "fingerprint": replacement.fingerprint,
            "grace_minutes": payload.grace_minutes,
        },
        ip=client_ip(request),
    )
    return CredentialResponse(**public_view(replacement))


@router.delete("/{credential_id}", response_model=OkResponse)
async def revoke_credential(
    credential_id: str,
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_ROTATE))],
) -> OkResponse:
    """Revoke immediately.

    Any run holding this credential fails loudly rather than returning partial
    results (section 27).
    """
    service = CredentialService(session, org_id=principal.org_id)
    credential = await service.revoke(credential_id, immediate=True)
    await AuditService(session, org_id=principal.org_id).record(
        action="credential.revoked",
        actor_id=principal.id,
        actor_type=principal.type,
        actor_label=principal.display or principal.id,
        resource_type="credential",
        resource_id=credential.id,
        after={"fingerprint": credential.fingerprint},
        ip=client_ip(request),
    )
    return OkResponse(
        message=(
            "Credential revoked and its ciphertext destroyed. In-flight runs using it "
            "will fail rather than return partial results."
        )
    )


@router.post("/reconcile-quota", response_model=OkResponse)
async def trigger_reconcile(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_READ))],
) -> OkResponse:
    """Queue an upstream quota reconciliation (section 40)."""
    published = await kafka.publish(
        kafka.TOPIC_QUOTA_RECONCILE, {"org_id": principal.org_id}, key=principal.org_id
    )
    return OkResponse(
        ok=published,
        message=(
            "Reconciliation queued."
            if published
            else "Kafka is unavailable; reconciliation was not queued."
        ),
    )


@router.post("/revalidate", response_model=OkResponse)
async def trigger_revalidate(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.CREDENTIAL_WRITE))],
) -> OkResponse:
    published = await kafka.publish(
        kafka.TOPIC_CREDENTIALS_VALIDATE, {"org_id": principal.org_id}, key=principal.org_id
    )
    return OkResponse(
        ok=published,
        message=(
            "Background validation queued."
            if published
            else "Kafka is unavailable; validation was not queued."
        ),
    )


__all__ = ["router"]
