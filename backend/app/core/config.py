"""Application configuration.

Every value is environment driven. Nothing secret is ever hardcoded; see
``.env.example`` at the repository root for the full list.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ExecutionMode = Literal["live", "record", "replay"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- service identity -------------------------------------------------
    service_name: str = "serpflow"
    environment: Literal["local", "dev", "staging", "production"] = "local"
    debug: bool = True
    api_v1_prefix: str = "/v1"

    # ---- execution mode (section 21) -------------------------------------
    # NOTE: a `test` API key always routes to the deterministic mock no matter
    # what this is set to. See app/services/executor/mode.py.
    serpflow_mode: ExecutionMode = "replay"

    # ---- datastores -------------------------------------------------------
    database_url: str = "postgresql+psycopg://serpflow:serpflow@localhost:5432/serpflow"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    redis_principal_cache_ttl: int = 60  # section 33

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "serpflow"
    kafka_consumer_group: str = "serpflow-workers"
    kafka_enabled: bool = True

    # ---- object storage (section 56) -------------------------------------
    storage_backend: Literal["filesystem", "s3"] = "filesystem"
    storage_local_path: str = "./.serpflow-objects"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "serpflow-payloads"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"

    # ---- security ---------------------------------------------------------
    jwt_secret: str = "change-me-in-production-this-is-a-local-dev-default"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14
    api_key_pepper: str = "change-me-api-key-pepper-local-dev-only"
    # Key-encryption key for the credential vault (section 24). Base64 32 bytes.
    credential_kek: str = "c2VycGZsb3ctbG9jYWwtZGV2LWtlay0zMmJ5dGVzLXh4eA=="
    credential_kek_id: str = "local-dev-kek-v1"
    # NoDecode: the dotenv source would otherwise try to JSON-parse this
    # before the validator below gets to split the comma-separated form.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    rate_limit_per_minute: int = 240
    max_request_body_bytes: int = 1024 * 1024
    # How many reverse proxies in front of the API append to X-Forwarded-For.
    # The bundled nginx is 1. Use 0 when the API is exposed directly, so a
    # client-supplied X-Forwarded-For is never trusted to identify a principal
    # for rate limiting - otherwise anyone can spoof a fresh bucket per request.
    trusted_proxy_hops: int = 1

    # ---- startup bootstrap ------------------------------------------------
    # Apply Alembic migrations when the API starts. Safe with several replicas:
    # guarded by a PostgreSQL advisory lock, so exactly one process migrates
    # and the others wait rather than racing.
    run_migrations_on_startup: bool = False
    # Run the idempotent seed on every API start. Existing records are kept and
    # only missing data is inserted. Refused automatically when `environment`
    # is staging or production - demo accounts with a published password have
    # no business being created there.
    seed_on_startup: bool = False

    # ---- email ------------------------------------------------------------
    # Base URL the action links in outgoing mail point at.
    frontend_url: str = "http://localhost:5173"
    # Base64 of a pickled google.oauth2.credentials.Credentials, produced by
    # `scripts/mint_gmail_token.py`. A secret, and never committed. Sending is
    # all it can do: the token carries the gmail.send scope only, so a leak
    # cannot read the mailbox it sends from. Setting it switches delivery from
    # the console backend to Gmail with no other configuration.
    gmail_credentials_b64: str = ""
    # The mailbox that consented. Gmail sends from the authorised account
    # regardless, so this carries the display name and catches a mismatch early.
    gmail_sender: str = ""
    email_from_name: str = "SerpFlow"
    email_verification_ttl_seconds: int = 60 * 60 * 24
    password_reset_ttl_seconds: int = 60 * 60

    # ---- upstream SerpApi -------------------------------------------------
    # There is no SERPAPI_API_KEY here. SerpApi access is bring-your-own-key:
    # each organization stores its own in the encrypted credential vault, and
    # no code path falls back to a key held by the deployment. A field for one
    # existed and was read by nothing, which read as if the platform might
    # quietly use its own key.
    serpapi_base_url: str = "https://serpapi.com"
    serpapi_timeout_seconds: float = 30.0

    # ---- LLM (Groq) -------------------------------------------------------
    # Also bring-your-own-key: an organization that stores a Groq credential
    # plans through Groq, and one that does not plans deterministically.
    #
    # These two remain for self-hosting, where one operator runs the instance
    # for themselves and would otherwise have to attach a credential to every
    # organization they create. They are the last resort, consulted only when
    # the organization has brought no key - so on a multi-tenant deployment
    # they are left unset and never apply.
    llm_provider: Literal["groq", "mock"] = "mock"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 45.0
    embedding_dim: int = 384

    # ---- planner / cache tuning ------------------------------------------
    planner_retrieval_top_k: int = 8
    planner_max_candidates: int = 6
    planner_max_hops: int = 4
    semantic_similarity_threshold: float = 0.95
    cache_partition_scope: Literal["project", "organization"] = "project"
    adaptive_ttl_min_seconds: int = 300
    adaptive_ttl_max_seconds: int = 60 * 60 * 24 * 90
    default_budget_alert_ratio: float = 0.8

    # ---- record / replay --------------------------------------------------
    cassette_dir: str = "./fixtures/cassettes"

    # ---- retention (section 55) ------------------------------------------
    retention_standard_days: int = 30
    retention_high_pii_days: int = 7

    # ---- observability ----------------------------------------------------
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    log_level: str = "INFO"
    log_json: bool = True
    log_file: str = "logs/serpflow.log"
    log_output: Literal["console", "file", "both", "none"] = "both"
    metrics_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """Alembic / sync tooling URL."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def email_sender(self) -> str:
        """The From header: ``EMAIL_FROM_NAME <GMAIL_SENDER>``.

        Gmail sends from whichever account consented regardless of what is put
        here, so this carries the display name and makes a mismatch visible.
        """
        if self.gmail_sender:
            return self.email_from_name + " <" + self.gmail_sender + ">"
        return self.email_from_name + " <no-reply@serpflow.local>"

    @property
    def email_configured(self) -> bool:
        """True when real delivery is possible. Otherwise mail goes to the log."""
        return bool(self.gmail_credentials_b64)

    @property
    def seeding_permitted(self) -> bool:
        """Seed-on-startup is refused outside development.

        The seed creates demo accounts with a password that is committed to
        this repository. That is correct for a laptop and indefensible in a
        staging or production environment, so the refusal is in the settings
        rather than left to whoever writes the deployment manifest.
        """
        return self.environment in ("local", "dev")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


settings = get_settings()

__all__ = ["ExecutionMode", "Settings", "get_settings", "reload_settings", "settings", "os"]
