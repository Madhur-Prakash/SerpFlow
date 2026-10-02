"""Typed application errors.

Every error carries a stable machine code (section 74). Stack traces are never
returned to clients; the handler in ``app/api/middleware.py`` turns these into
the canonical envelope.
"""

from __future__ import annotations

from typing import Any


class SerpFlowError(Exception):
    """Base class for all SerpFlow application errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_envelope(self, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        if request_id:
            error["request_id"] = request_id
        return {"error": error}


# --- authn / authz --------------------------------------------------------
class AuthenticationError(SerpFlowError):
    code = "UNAUTHENTICATED"
    status_code = 401
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code = "INVALID_CREDENTIALS"
    message = "Email or password is incorrect."


class InvalidApiKeyError(AuthenticationError):
    code = "INVALID_API_KEY"
    message = "The supplied API key is invalid, revoked, or expired."


class PermissionDeniedError(SerpFlowError):
    code = "PERMISSION_DENIED"
    status_code = 403
    message = "The current principal is not permitted to perform this action."


class TenantIsolationError(SerpFlowError):
    code = "TENANT_ISOLATION_VIOLATION"
    status_code = 403
    message = "Resource belongs to a different organization."


# --- resources ------------------------------------------------------------
class NotFoundError(SerpFlowError):
    code = "NOT_FOUND"
    status_code = 404
    message = "The requested resource does not exist."


class ConflictError(SerpFlowError):
    code = "CONFLICT"
    status_code = 409
    message = "The resource already exists or is in a conflicting state."


class ValidationError(SerpFlowError):
    code = "VALIDATION_ERROR"
    status_code = 422
    message = "The request payload failed validation."


class RateLimitedError(SerpFlowError):
    code = "RATE_LIMITED"
    status_code = 429
    message = "Too many requests."


# --- budgets (section 39 - these two must never be conflated) -------------
class BudgetExhaustedError(SerpFlowError):
    """The user-configured SerpFlow cap is exhausted. Fix: raise the budget."""

    code = "BUDGET_EXHAUSTED"
    status_code = 402
    message = (
        "The configured SerpFlow budget has been exhausted. "
        "Raise the configured budget to continue."
    )


class UpstreamQuotaExhaustedError(SerpFlowError):
    """The SerpApi account itself has no quota. Fix: add upstream capacity."""

    code = "UPSTREAM_QUOTA_EXHAUSTED"
    status_code = 402
    message = (
        "The upstream SerpApi account has no remaining search quota. "
        "Add upstream capacity on your SerpApi account."
    )


class BudgetInfeasibleError(SerpFlowError):
    code = "BUDGET_INFEASIBLE"
    status_code = 422
    message = "No candidate plan fits within the supplied budget, even after reduction."


# --- credentials ----------------------------------------------------------
class NoUpstreamCredentialError(SerpFlowError):
    code = "NO_UPSTREAM_CREDENTIAL"
    status_code = 412
    message = (
        "No upstream SerpApi credential is configured for this project or its "
        "organization. Attach a credential, or use a test API key."
    )


class CredentialValidationError(SerpFlowError):
    code = "CREDENTIAL_VALIDATION_FAILED"
    status_code = 422
    message = "The supplied SerpApi credential failed upstream validation."


class CredentialRevokedError(SerpFlowError):
    code = "CREDENTIAL_REVOKED"
    status_code = 409
    message = "The credential was revoked while the run was in flight. The run failed."


# --- planner / executor ---------------------------------------------------
class NoViablePlanError(SerpFlowError):
    code = "NO_VIABLE_PLAN"
    status_code = 422
    message = "The planner could not construct a valid plan for this intent."


class CatalogError(SerpFlowError):
    code = "CATALOG_ERROR"
    status_code = 500
    message = "The engine catalog is invalid or unavailable."


class ReplayMissError(SerpFlowError):
    """Replay mode must never silently reach the network (section 21)."""

    code = "REPLAY_CASSETTE_MISS"
    status_code = 503
    message = "No cassette recorded for this request and SERPFLOW_MODE=replay."


class UpstreamError(SerpFlowError):
    code = "UPSTREAM_ERROR"
    status_code = 502
    message = "The upstream SerpApi call failed."


class EngineNotAllowedError(SerpFlowError):
    code = "ENGINE_NOT_ALLOWED"
    status_code = 403
    message = "The engine is excluded by this project's engine policy."


class SessionCapExceededError(SerpFlowError):
    code = "SESSION_CAP_EXCEEDED"
    status_code = 429
    message = "The service principal session cap has been reached."


__all__ = [n for n in dir() if n.endswith("Error")]
