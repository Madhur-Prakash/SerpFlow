"""All ORM models. Importing this package registers every table on the
declarative metadata, which is what Alembic autogenerate reads."""

from app.db.base import Base, metadata
from app.db.models.benchmark import BenchmarkRun, BenchmarkTask, RoutingEval
from app.db.models.caching import (
    ArchiveRef,
    CacheEntry,
    FalseHitReport,
    SemanticGuardRejection,
    TTLObservation,
)
from app.db.models.catalog import (
    CatalogEdge,
    CatalogEngine,
    CatalogSubstitute,
    CatalogVersion,
)
from app.db.models.governance import (
    Alert,
    AuditLogEntry,
    Budget,
    BudgetLedgerEntry,
    NotificationChannel,
    WebhookDelivery,
)
from app.db.models.identity import (
    AuthSession,
    Membership,
    Organization,
    Project,
    ProjectMember,
    ServicePrincipalSession,
    User,
)
from app.db.models.keys import ApiKey, UpstreamCredential, UpstreamQuotaSnapshot
from app.db.models.planning import Plan, PlanCandidate, Run, Step

__all__ = [
    "Alert",
    "ApiKey",
    "ArchiveRef",
    "AuditLogEntry",
    "AuthSession",
    "Base",
    "BenchmarkRun",
    "BenchmarkTask",
    "Budget",
    "BudgetLedgerEntry",
    "CacheEntry",
    "CatalogEdge",
    "CatalogEngine",
    "CatalogSubstitute",
    "CatalogVersion",
    "FalseHitReport",
    "Membership",
    "NotificationChannel",
    "Organization",
    "Plan",
    "PlanCandidate",
    "Project",
    "ProjectMember",
    "RoutingEval",
    "Run",
    "SemanticGuardRejection",
    "ServicePrincipalSession",
    "Step",
    "TTLObservation",
    "UpstreamCredential",
    "UpstreamQuotaSnapshot",
    "User",
    "WebhookDelivery",
    "metadata",
]
