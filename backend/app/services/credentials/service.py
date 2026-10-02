"""Upstream SerpApi credential vault (sections 23-27).

Resolution order, exactly as specified::

    project.credential_id
            v if absent
    org.default_credential_id
            v if absent
    NO_UPSTREAM_CREDENTIAL

Small organizations configure one org-level credential; organizations with
several SerpApi accounts override per project or cost centre.

The secret is never returned by this service. ``resolve`` hands back the ORM
row carrying ciphertext; only ``ExecutorService`` decrypts it, and no Pydantic
response model in ``app/schemas`` contains the field at all - not excluded,
absent, because excluded fields leak through serialisation bugs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    CredentialValidationError,
    NotFoundError,
    NoUpstreamCredentialError,
)
from app.core.logging import get_logger
from app.core.security import credential_fingerprint, encrypt_credential
from app.db.models.identity import Organization, Project
from app.db.models.keys import UpstreamCredential, UpstreamQuotaSnapshot
from app.integrations.serpapi import SerpApiClient

log = get_logger("serpflow.credentials")

VALIDATION_PENDING = "pending"
VALIDATION_VALID = "valid"
VALIDATION_FAILED = "failed"


class CredentialService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self.session = session
        self.org_id = org_id

    # ---------------------------------------------------------- resolution
    async def resolve(self, project: Project | None) -> UpstreamCredential:
        """Project credential, then organization default, then refuse."""
        if project is not None and project.credential_id:
            credential = await self.session.get(UpstreamCredential, project.credential_id)
            if (
                credential is not None
                and credential.org_id == self.org_id
                and self._usable(credential)
            ):
                return credential

        org = await self.session.get(Organization, self.org_id)
        if org is not None and org.default_credential_id:
            credential = await self.session.get(UpstreamCredential, org.default_credential_id)
            if credential is not None and self._usable(credential):
                return credential

        raise NoUpstreamCredentialError(
            "No upstream SerpApi credential is configured for project "
            + (project.name if project else "(unknown)")
            + " or for its organization. Attach a credential in Settings, or use a "
            + "test API key to run against the deterministic mock at zero cost.",
            details={
                "project_id": project.id if project else None,
                "org_id": self.org_id,
                "resolution_order": ["project.credential_id", "org.default_credential_id"],
            },
        )

    async def resolve_optional(self, project: Project | None) -> UpstreamCredential | None:
        try:
            return await self.resolve(project)
        except NoUpstreamCredentialError:
            return None

    @staticmethod
    def _usable(credential: UpstreamCredential) -> bool:
        if credential.revoked_at is None:
            return True
        # A revoked credential stays usable until its grace window closes, so
        # in-flight runs finish instead of failing halfway.
        return bool(credential.grace_until and credential.grace_until > datetime.now(UTC))

    # ------------------------------------------------------------- lifecycle
    async def create(
        self,
        *,
        name: str,
        secret: str,
        project_id: str | None = None,
        validate: bool = True,
        set_as_org_default: bool = False,
    ) -> UpstreamCredential:
        """Encrypt, validate with one cheap upstream call, record, never return."""
        fingerprint = credential_fingerprint(secret)
        existing = await self.session.scalar(
            select(UpstreamCredential).where(
                UpstreamCredential.org_id == self.org_id,
                UpstreamCredential.fingerprint == fingerprint,
                UpstreamCredential.revoked_at.is_(None),
            )
        )
        if existing is not None:
            raise ConflictError(
                "That credential is already attached to this organization as " + existing.name + "."
            )

        envelope = encrypt_credential(secret)
        credential = UpstreamCredential(
            org_id=self.org_id,
            project_id=project_id,
            name=name,
            ciphertext=envelope.ciphertext,
            encrypted_dek=envelope.encrypted_dek,
            kek_id=envelope.kek_id,
            algo=envelope.algo,
            fingerprint=envelope.fingerprint,
        )
        self.session.add(credential)
        await self.session.flush()

        if validate:
            await self.validate(credential, secret=secret)

        if project_id:
            project = await self.session.get(Project, project_id)
            if project is not None and project.org_id == self.org_id:
                project.credential_id = credential.id

        if set_as_org_default or not await self._has_default():
            org = await self.session.get(Organization, self.org_id)
            if org is not None:
                org.default_credential_id = credential.id

        return credential

    async def _has_default(self) -> bool:
        org = await self.session.get(Organization, self.org_id)
        return bool(org and org.default_credential_id)

    async def validate(
        self, credential: UpstreamCredential, *, secret: str | None = None
    ) -> dict[str, Any]:
        """One cheap upstream call proving the credential works (section 26)."""
        from app.core.security import decrypt_credential

        plaintext = secret or decrypt_credential(credential.ciphertext, credential.encrypted_dek)
        try:
            result = await SerpApiClient(plaintext).validate()
        except Exception as exc:
            credential.validation_status = VALIDATION_FAILED
            # Only the exception class name is recorded. The message could
            # echo the key back, and this column is read by the UI.
            credential.validation_error = type(exc).__name__
            credential.last_validated_at = datetime.now(UTC)
            log.warning(
                "credential validation failed",
                extra={
                    "event": "credential.validation_failed",
                    "credential_id": credential.id,
                    "fingerprint": credential.fingerprint,
                    "error": type(exc).__name__,
                },
            )
            raise CredentialValidationError(
                "SerpApi rejected this credential or could not be reached ("
                + type(exc).__name__
                + ")."
            ) from exc
        finally:
            plaintext = ""

        credential.validation_status = VALIDATION_VALID
        credential.validation_error = None
        credential.last_validated_at = datetime.now(UTC)
        credential.upstream_plan = result.get("plan_name")
        credential.upstream_searches_left = result.get("searches_left")
        credential.upstream_checked_at = datetime.now(UTC)
        return result

    async def rotate(
        self, credential_id: str, *, new_secret: str, grace_minutes: int = 15
    ) -> UpstreamCredential:
        """Encrypt, validate, atomically swap, grace the old, then destroy it."""
        old = await self.get(credential_id)
        envelope = encrypt_credential(new_secret)
        replacement = UpstreamCredential(
            org_id=self.org_id,
            project_id=old.project_id,
            name=old.name,
            ciphertext=envelope.ciphertext,
            encrypted_dek=envelope.encrypted_dek,
            kek_id=envelope.kek_id,
            algo=envelope.algo,
            fingerprint=envelope.fingerprint,
            rotated_from_id=old.id,
        )
        self.session.add(replacement)
        await self.session.flush()

        await self.validate(replacement, secret=new_secret)

        # Atomic swap: every pointer moves to the replacement in one
        # transaction, then the old credential enters its grace window.
        projects = (
            await self.session.scalars(select(Project).where(Project.credential_id == old.id))
        ).all()
        for project in projects:
            project.credential_id = replacement.id
        org = await self.session.get(Organization, self.org_id)
        if org is not None and org.default_credential_id == old.id:
            org.default_credential_id = replacement.id

        old.revoked_at = datetime.now(UTC)
        old.rotated_at = datetime.now(UTC)
        old.grace_until = datetime.now(UTC) + timedelta(minutes=grace_minutes)
        return replacement

    async def destroy_expired_rotations(self) -> int:
        """Erase the ciphertext of credentials whose grace window has closed."""
        now = datetime.now(UTC)
        rows = (
            await self.session.scalars(
                select(UpstreamCredential).where(
                    UpstreamCredential.org_id == self.org_id,
                    UpstreamCredential.grace_until.is_not(None),
                    UpstreamCredential.grace_until < now,
                    UpstreamCredential.ciphertext != "",
                )
            )
        ).all()
        for row in rows:
            row.ciphertext = ""
            row.encrypted_dek = ""
        return len(rows)

    async def revoke(self, credential_id: str, *, immediate: bool = True) -> UpstreamCredential:
        credential = await self.get(credential_id)
        credential.revoked_at = datetime.now(UTC)
        if immediate:
            credential.grace_until = None
            credential.ciphertext = ""
            credential.encrypted_dek = ""
        return credential

    async def get(self, credential_id: str) -> UpstreamCredential:
        credential = await self.session.get(UpstreamCredential, credential_id)
        if credential is None or credential.org_id != self.org_id:
            raise NotFoundError("Credential not found.")
        return credential

    async def list(self) -> list[UpstreamCredential]:
        return list(
            (
                await self.session.scalars(
                    select(UpstreamCredential)
                    .where(UpstreamCredential.org_id == self.org_id)
                    .order_by(UpstreamCredential.created_at.desc())
                )
            ).all()
        )

    # --------------------------------------------- quota reconciliation (40)
    async def reconcile_quota(
        self, credential: UpstreamCredential, *, internal_spend_since_last: int = 0
    ) -> UpstreamQuotaSnapshot:
        """Compare SerpFlow's ledger against the SerpApi account endpoint.

        The two diverge the moment the credential is used outside SerpFlow. The
        dashboard shows the divergence rather than implying the internal ledger
        is the upstream truth.
        """
        from app.core.security import decrypt_credential

        plaintext = decrypt_credential(credential.ciphertext, credential.encrypted_dek)
        try:
            account = await SerpApiClient(plaintext).account()
        finally:
            plaintext = ""

        searches_left = account.get("total_searches_left") or account.get("plan_searches_left")
        previous = await self.session.scalar(
            select(UpstreamQuotaSnapshot)
            .where(UpstreamQuotaSnapshot.credential_id == credential.id)
            .order_by(UpstreamQuotaSnapshot.created_at.desc())
            .limit(1)
        )
        upstream_spend = None
        divergence = None
        if (
            previous is not None
            and previous.searches_left is not None
            and searches_left is not None
        ):
            upstream_spend = previous.searches_left - searches_left
            divergence = internal_spend_since_last - upstream_spend

        snapshot = UpstreamQuotaSnapshot(
            org_id=self.org_id,
            credential_id=credential.id,
            fingerprint=credential.fingerprint,
            plan_name=account.get("plan_name"),
            searches_left=searches_left,
            total_searches_left=account.get("total_searches_left"),
            this_month_usage=account.get("this_month_usage"),
            internal_spend_since_last=internal_spend_since_last,
            upstream_spend_since_last=upstream_spend,
            divergence=divergence,
            raw={k: v for k, v in account.items() if k != "api_key"},
        )
        self.session.add(snapshot)

        credential.upstream_plan = account.get("plan_name")
        credential.upstream_searches_left = searches_left
        credential.upstream_total_searches = account.get("searches_per_month")
        credential.upstream_checked_at = datetime.now(UTC)
        return snapshot


def public_view(credential: UpstreamCredential) -> dict[str, Any]:
    """Everything a client may see. The secret is structurally absent.

    Renders as ``...a3f9 - added Sep 12 - validated 2h ago``.
    """
    return {
        "id": credential.id,
        "name": credential.name,
        "provider": credential.provider,
        "project_id": credential.project_id,
        "fingerprint": credential.fingerprint,
        "display": "..." + credential.fingerprint[-4:],
        "kek_id": credential.kek_id,
        "algo": credential.algo,
        "validation_status": credential.validation_status,
        "validation_error": credential.validation_error,
        "last_validated_at": (
            credential.last_validated_at.isoformat() if credential.last_validated_at else None
        ),
        "created_at": credential.created_at.isoformat(),
        "rotated_at": credential.rotated_at.isoformat() if credential.rotated_at else None,
        "revoked_at": credential.revoked_at.isoformat() if credential.revoked_at else None,
        "upstream_plan": credential.upstream_plan,
        "upstream_searches_left": credential.upstream_searches_left,
        "upstream_checked_at": (
            credential.upstream_checked_at.isoformat() if credential.upstream_checked_at else None
        ),
    }


__all__ = [
    "VALIDATION_FAILED",
    "VALIDATION_PENDING",
    "VALIDATION_VALID",
    "CredentialService",
    "public_view",
]
