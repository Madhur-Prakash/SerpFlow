"""Initial SerpFlow schema.

Creates every table in section 81, the pgvector column and HNSW index backing
the semantic cache layer (section 17), and the row-level security policies
that enforce tenant isolation (section 36).

Revision ID: 0001_initial
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every tenant-scoped table carries org_id and is additionally protected by
# RLS. Application guards in app/api/deps.py enforce the same boundary
# independently; RLS is the backstop, not the only check.
RLS_TABLES = (
    "projects",
    "project_members",
    "memberships",
    "api_keys",
    "upstream_credentials",
    "upstream_quota_snapshots",
    "service_sessions",
    "budgets",
    "budget_ledger",
    "plans",
    "plan_candidates",
    "runs",
    "steps",
    "cache_entries",
    "archive_refs",
    "ttl_observations",
    "semantic_guard_rejections",
    "false_hit_reports",
    "audit_log",
    "alerts",
    "notification_channels",
    "webhook_deliveries",
)


def upgrade() -> None:
    # pgvector is also created by docker/postgres/init, but a hand-provisioned
    # database may not have run that, and the semantic cache cannot work
    # without it.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table('benchmark_runs',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=True),
    sa.Column('suite_version', sa.String(length=20), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('system', sa.String(length=32), nullable=False),
    sa.Column('llm_model', sa.String(length=80), nullable=False),
    sa.Column('task_count', sa.Integer(), nullable=False),
    sa.Column('correct_count', sa.Integer(), nullable=False),
    sa.Column('partial_count', sa.Integer(), nullable=False),
    sa.Column('accuracy', sa.Float(), nullable=False),
    sa.Column('engine_accuracy', sa.Float(), nullable=False),
    sa.Column('param_accuracy', sa.Float(), nullable=False),
    sa.Column('freshness_accuracy', sa.Float(), nullable=False),
    sa.Column('mean_confidence', sa.Float(), nullable=False),
    sa.Column('mean_latency_ms', sa.Float(), nullable=False),
    sa.Column('by_category', sa.JSON(), nullable=False),
    sa.Column('failure_modes', sa.JSON(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_benchmark_runs'))
    )
    op.create_index(op.f('ix_benchmark_runs_catalog_version'), 'benchmark_runs', ['catalog_version'], unique=False)
    op.create_index(op.f('ix_benchmark_runs_created_at'), 'benchmark_runs', ['created_at'], unique=False)
    op.create_index(op.f('ix_benchmark_runs_org_id'), 'benchmark_runs', ['org_id'], unique=False)
    op.create_index(op.f('ix_benchmark_runs_system'), 'benchmark_runs', ['system'], unique=False)
    op.create_table('benchmark_tasks',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('task_key', sa.String(length=40), nullable=False),
    sa.Column('suite_version', sa.String(length=20), nullable=False),
    sa.Column('intent', sa.Text(), nullable=False),
    sa.Column('expected_engines', sa.JSON(), nullable=False),
    sa.Column('acceptable_alternatives', sa.JSON(), nullable=False),
    sa.Column('expected_params', sa.JSON(), nullable=False),
    sa.Column('expected_freshness', sa.String(length=16), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('difficulty', sa.String(length=12), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_benchmark_tasks')),
    sa.UniqueConstraint('task_key', 'suite_version', name='uq_benchmark_tasks_key_version')
    )
    op.create_index(op.f('ix_benchmark_tasks_created_at'), 'benchmark_tasks', ['created_at'], unique=False)
    op.create_index(op.f('ix_benchmark_tasks_task_key'), 'benchmark_tasks', ['task_key'], unique=False)
    op.create_table('catalog_edges',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('from_engine', sa.String(length=80), nullable=False),
    sa.Column('to_engine', sa.String(length=80), nullable=False),
    sa.Column('produces_field', sa.String(length=200), nullable=False),
    sa.Column('satisfies_param', sa.String(length=80), nullable=False),
    sa.Column('param_type', sa.String(length=40), nullable=False),
    sa.Column('fan_out_hint', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_edges'))
    )
    op.create_index(op.f('ix_catalog_edges_created_at'), 'catalog_edges', ['created_at'], unique=False)
    op.create_index('ix_catalog_edges_from', 'catalog_edges', ['catalog_version', 'from_engine'], unique=False)
    op.create_index('ix_catalog_edges_to', 'catalog_edges', ['catalog_version', 'to_engine'], unique=False)
    op.create_table('catalog_engines',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('capability_tags', sa.JSON(), nullable=False),
    sa.Column('requires', sa.JSON(), nullable=False),
    sa.Column('optional_params', sa.JSON(), nullable=False),
    sa.Column('produces', sa.JSON(), nullable=False),
    sa.Column('cost', sa.Integer(), nullable=False),
    sa.Column('latency_class', sa.String(length=16), nullable=False),
    sa.Column('volatility_prior', sa.String(length=16), nullable=False),
    sa.Column('locale_sensitive', sa.JSON(), nullable=False),
    sa.Column('pii_risk', sa.String(length=12), nullable=False),
    sa.Column('docs_url', sa.String(length=300), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_engines')),
    sa.UniqueConstraint('catalog_version', 'engine', name='uq_catalog_engines_version_engine')
    )
    op.create_index(op.f('ix_catalog_engines_created_at'), 'catalog_engines', ['created_at'], unique=False)
    op.create_index(op.f('ix_catalog_engines_engine'), 'catalog_engines', ['engine'], unique=False)
    op.create_index('ix_catalog_engines_version', 'catalog_engines', ['catalog_version'], unique=False)
    op.create_table('catalog_substitutes',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('substitute_engine', sa.String(length=80), nullable=False),
    sa.Column('coverage', sa.String(length=12), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('shared_tags', sa.JSON(), nullable=False),
    sa.Column('confidence_penalty', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_substitutes'))
    )
    op.create_index('ix_catalog_subs_engine', 'catalog_substitutes', ['catalog_version', 'engine'], unique=False)
    op.create_index('ix_catalog_subs_sub', 'catalog_substitutes', ['catalog_version', 'substitute_engine'], unique=False)
    op.create_index(op.f('ix_catalog_substitutes_created_at'), 'catalog_substitutes', ['created_at'], unique=False)
    op.create_table('catalog_versions',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('version', sa.String(length=40), nullable=False),
    sa.Column('engine_count', sa.Integer(), nullable=False),
    sa.Column('edge_count', sa.Integer(), nullable=False),
    sa.Column('substitute_count', sa.Integer(), nullable=False),
    sa.Column('capability_tag_count', sa.Integer(), nullable=False),
    sa.Column('checksum', sa.String(length=80), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_versions'))
    )
    op.create_index(op.f('ix_catalog_versions_created_at'), 'catalog_versions', ['created_at'], unique=False)
    op.create_index(op.f('ix_catalog_versions_version'), 'catalog_versions', ['version'], unique=True)
    op.create_table('organizations',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('plan_tier', sa.String(length=40), nullable=False),
    sa.Column('default_credential_id', sa.String(length=40), nullable=True),
    sa.Column('cache_scope', sa.String(length=20), nullable=False),
    sa.Column('settings_json', sa.JSON(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    # FK added after upstream_credentials exists; see below.
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations'))
    )
    op.create_index(op.f('ix_organizations_created_at'), 'organizations', ['created_at'], unique=False)
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)
    op.create_table('upstream_credentials',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('encrypted_dek', sa.Text(), nullable=False),
    sa.Column('kek_id', sa.String(length=80), nullable=False),
    sa.Column('algo', sa.String(length=40), nullable=False),
    sa.Column('fingerprint', sa.String(length=16), nullable=False),
    sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('validation_status', sa.String(length=24), nullable=False),
    sa.Column('validation_error', sa.String(length=300), nullable=True),
    sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rotated_from_id', sa.String(length=40), nullable=True),
    sa.Column('grace_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('upstream_plan', sa.String(length=80), nullable=True),
    sa.Column('upstream_searches_left', sa.Integer(), nullable=True),
    sa.Column('upstream_total_searches', sa.Integer(), nullable=True),
    sa.Column('upstream_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_upstream_credentials_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_upstream_credentials'))
    )
    op.create_index(op.f('ix_upstream_credentials_created_at'), 'upstream_credentials', ['created_at'], unique=False)
    op.create_index(op.f('ix_upstream_credentials_fingerprint'), 'upstream_credentials', ['fingerprint'], unique=False)
    op.create_index('ix_upstream_credentials_org_active', 'upstream_credentials', ['org_id', 'revoked_at'], unique=False)
    op.create_index(op.f('ix_upstream_credentials_org_id'), 'upstream_credentials', ['org_id'], unique=False)
    op.create_index(op.f('ix_upstream_credentials_project_id'), 'upstream_credentials', ['project_id'], unique=False)
    # Close the organizations -> upstream_credentials cycle now that both
    # tables exist (section 23: an org names a default credential, and every
    # credential belongs to an org).
    op.create_foreign_key(
        op.f('fk_organizations_default_credential_id_upstream_credentials'),
        'organizations',
        'upstream_credentials',
        ['default_credential_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_table('users',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('email_verification_token_hash', sa.String(length=80), nullable=True),
    sa.Column('password_reset_token_hash', sa.String(length=80), nullable=True),
    sa.Column('password_reset_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mfa_enabled', sa.Boolean(), nullable=False),
    sa.Column('mfa_secret', sa.String(length=120), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_ip', sa.String(length=64), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_created_at'), 'users', ['created_at'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('alerts',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=True),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('severity', sa.String(length=12), nullable=False),
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.Column('acknowledged_by', sa.String(length=40), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dedupe_key', sa.String(length=160), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_alerts_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index(op.f('ix_alerts_created_at'), 'alerts', ['created_at'], unique=False)
    op.create_index(op.f('ix_alerts_dedupe_key'), 'alerts', ['dedupe_key'], unique=False)
    op.create_index(op.f('ix_alerts_kind'), 'alerts', ['kind'], unique=False)
    op.create_index(op.f('ix_alerts_org_id'), 'alerts', ['org_id'], unique=False)
    op.create_index('ix_alerts_org_status', 'alerts', ['org_id', 'status'], unique=False)
    op.create_index(op.f('ix_alerts_project_id'), 'alerts', ['project_id'], unique=False)
    op.create_table('archive_refs',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('partition_key', sa.String(length=60), nullable=False),
    sa.Column('search_id', sa.String(length=80), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('request_hash', sa.String(length=80), nullable=False),
    sa.Column('normalized_request', sa.JSON(), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('credential_fingerprint', sa.String(length=16), nullable=True),
    sa.Column('payload_ref', sa.String(length=200), nullable=True),
    sa.Column('reuse_count', sa.Integer(), nullable=False),
    sa.Column('serpapi_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_archive_refs_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_archive_refs'))
    )
    op.create_index(op.f('ix_archive_refs_created_at'), 'archive_refs', ['created_at'], unique=False)
    op.create_index(op.f('ix_archive_refs_engine'), 'archive_refs', ['engine'], unique=False)
    op.create_index('ix_archive_refs_lookup', 'archive_refs', ['partition_key', 'request_hash'], unique=False)
    op.create_index(op.f('ix_archive_refs_org_id'), 'archive_refs', ['org_id'], unique=False)
    op.create_index(op.f('ix_archive_refs_project_id'), 'archive_refs', ['project_id'], unique=False)
    op.create_index('ix_archive_refs_search_id', 'archive_refs', ['search_id'], unique=True)
    op.create_table('audit_log',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.String(length=40), nullable=True),
    sa.Column('actor_type', sa.String(length=20), nullable=False),
    sa.Column('actor_label', sa.String(length=200), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('resource_type', sa.String(length=60), nullable=False),
    sa.Column('resource_id', sa.String(length=60), nullable=True),
    sa.Column('project_id', sa.String(length=40), nullable=True),
    sa.Column('before', sa.JSON(), nullable=True),
    sa.Column('after', sa.JSON(), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=400), nullable=False),
    sa.Column('request_id', sa.String(length=60), nullable=True),
    sa.Column('prev_hash', sa.String(length=80), nullable=False),
    sa.Column('entry_hash', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_audit_log_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index('ix_audit_actor', 'audit_log', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_created_at'), 'audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_log_org_id'), 'audit_log', ['org_id'], unique=False)
    op.create_index(op.f('ix_audit_log_project_id'), 'audit_log', ['project_id'], unique=False)
    op.create_index('ix_audit_org_created', 'audit_log', ['org_id', 'created_at'], unique=False)
    op.create_index('ix_audit_resource', 'audit_log', ['resource_type', 'resource_id'], unique=False)
    op.create_table('auth_sessions',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.String(length=40), nullable=False),
    sa.Column('refresh_token_hash', sa.String(length=80), nullable=False),
    sa.Column('user_agent', sa.String(length=400), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rotated_from', sa.String(length=40), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_sessions'))
    )
    op.create_index(op.f('ix_auth_sessions_created_at'), 'auth_sessions', ['created_at'], unique=False)
    op.create_index(op.f('ix_auth_sessions_refresh_token_hash'), 'auth_sessions', ['refresh_token_hash'], unique=False)
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)
    op.create_table('budget_ledger',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('beneficiary_project_id', sa.String(length=40), nullable=True),
    sa.Column('run_id', sa.String(length=40), nullable=True),
    sa.Column('step_id', sa.String(length=40), nullable=True),
    sa.Column('api_key_id', sa.String(length=40), nullable=True),
    sa.Column('session_id', sa.String(length=40), nullable=True),
    sa.Column('principal_id', sa.String(length=40), nullable=True),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_budget_ledger_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_ledger'))
    )
    op.create_index(op.f('ix_budget_ledger_api_key_id'), 'budget_ledger', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_budget_ledger_beneficiary_project_id'), 'budget_ledger', ['beneficiary_project_id'], unique=False)
    op.create_index(op.f('ix_budget_ledger_created_at'), 'budget_ledger', ['created_at'], unique=False)
    op.create_index(op.f('ix_budget_ledger_org_id'), 'budget_ledger', ['org_id'], unique=False)
    op.create_index(op.f('ix_budget_ledger_project_id'), 'budget_ledger', ['project_id'], unique=False)
    op.create_index(op.f('ix_budget_ledger_run_id'), 'budget_ledger', ['run_id'], unique=False)
    op.create_index(op.f('ix_budget_ledger_session_id'), 'budget_ledger', ['session_id'], unique=False)
    op.create_index('ix_ledger_org_created', 'budget_ledger', ['org_id', 'created_at'], unique=False)
    op.create_index('ix_ledger_project_created', 'budget_ledger', ['project_id', 'created_at'], unique=False)
    op.create_table('budgets',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('scope', sa.String(length=20), nullable=False),
    sa.Column('scope_id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('limit_credits', sa.Integer(), nullable=False),
    sa.Column('current_usage', sa.Integer(), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('period_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('period_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('alert_at', sa.Float(), nullable=False),
    sa.Column('alert_fired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exhausted_alert_fired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('on_exhausted', sa.String(length=12), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_budgets_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_budgets')),
    sa.UniqueConstraint('scope', 'scope_id', 'period', name='uq_budgets_scope_period')
    )
    op.create_index(op.f('ix_budgets_created_at'), 'budgets', ['created_at'], unique=False)
    op.create_index(op.f('ix_budgets_org_id'), 'budgets', ['org_id'], unique=False)
    op.create_index('ix_budgets_org_scope', 'budgets', ['org_id', 'scope'], unique=False)
    op.create_index(op.f('ix_budgets_scope_id'), 'budgets', ['scope_id'], unique=False)
    op.create_table('cache_entries',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('partition_key', sa.String(length=60), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('gl', sa.String(length=8), nullable=False),
    sa.Column('hl', sa.String(length=8), nullable=False),
    sa.Column('location', sa.String(length=160), nullable=False),
    sa.Column('request_hash', sa.String(length=80), nullable=False),
    sa.Column('normalized_request', sa.JSON(), nullable=False),
    sa.Column('query_text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('numerals', sa.JSON(), nullable=False),
    sa.Column('entities', sa.JSON(), nullable=False),
    sa.Column('versions', sa.JSON(), nullable=False),
    sa.Column('payload_ref', sa.String(length=200), nullable=False),
    sa.Column('payload_bytes', sa.Integer(), nullable=False),
    sa.Column('result_count', sa.Integer(), nullable=False),
    sa.Column('top_results_digest', sa.String(length=80), nullable=True),
    sa.Column('credits_cost', sa.Integer(), nullable=False),
    sa.Column('ttl_seconds', sa.Integer(), nullable=False),
    sa.Column('ttl_source', sa.String(length=32), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hit_count', sa.Integer(), nullable=False),
    sa.Column('last_hit_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refresh_count', sa.Integer(), nullable=False),
    sa.Column('serpapi_search_id', sa.String(length=80), nullable=True),
    sa.Column('pii_risk', sa.String(length=12), nullable=False),
    sa.Column('invalidated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_run_id', sa.String(length=40), nullable=True),
    sa.Column('mode', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_cache_entries_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cache_entries'))
    )
    op.create_index(op.f('ix_cache_entries_created_at'), 'cache_entries', ['created_at'], unique=False)
    op.create_index('ix_cache_entries_exact', 'cache_entries', ['partition_key', 'request_hash'], unique=True)
    op.create_index('ix_cache_entries_expiry', 'cache_entries', ['expires_at'], unique=False)
    op.create_index(op.f('ix_cache_entries_org_id'), 'cache_entries', ['org_id'], unique=False)
    op.create_index('ix_cache_entries_partition', 'cache_entries', ['partition_key', 'engine', 'gl', 'hl', 'location'], unique=False)
    op.create_index('ix_cache_entries_project_engine', 'cache_entries', ['project_id', 'engine'], unique=False)
    op.create_index(op.f('ix_cache_entries_project_id'), 'cache_entries', ['project_id'], unique=False)
    op.create_table('memberships',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.String(length=40), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('invited_by', sa.String(length=40), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_memberships_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memberships_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    sa.UniqueConstraint('org_id', 'user_id', name='uq_memberships_org_user')
    )
    op.create_index(op.f('ix_memberships_created_at'), 'memberships', ['created_at'], unique=False)
    op.create_index(op.f('ix_memberships_org_id'), 'memberships', ['org_id'], unique=False)
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)
    op.create_table('notification_channels',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('target', sa.String(length=500), nullable=False),
    sa.Column('secret_hash', sa.String(length=80), nullable=True),
    sa.Column('events', sa.JSON(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('last_delivery_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_delivery_status', sa.String(length=40), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_notification_channels_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_channels'))
    )
    op.create_index(op.f('ix_notification_channels_created_at'), 'notification_channels', ['created_at'], unique=False)
    op.create_index(op.f('ix_notification_channels_org_id'), 'notification_channels', ['org_id'], unique=False)
    op.create_table('projects',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('key_prefix', sa.String(length=6), nullable=False),
    sa.Column('credential_id', sa.String(length=40), nullable=True),
    sa.Column('engine_allowlist', sa.JSON(), nullable=False),
    sa.Column('engine_denylist', sa.JSON(), nullable=False),
    sa.Column('semantic_threshold', sa.Double(), nullable=True),
    sa.Column('ttl_overrides', sa.JSON(), nullable=False),
    sa.Column('retention_days', sa.Integer(), nullable=True),
    sa.Column('retention_high_pii_days', sa.Integer(), nullable=True),
    sa.Column('shared_cache_enabled', sa.Boolean(), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['credential_id'], ['upstream_credentials.id'], name=op.f('fk_projects_credential_id_upstream_credentials'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_projects_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects')),
    sa.UniqueConstraint('org_id', 'slug', name='uq_projects_org_slug')
    )
    op.create_index(op.f('ix_projects_created_at'), 'projects', ['created_at'], unique=False)
    op.create_index('ix_projects_key_prefix', 'projects', ['key_prefix'], unique=True)
    op.create_index(op.f('ix_projects_org_id'), 'projects', ['org_id'], unique=False)
    op.create_table('routing_evals',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('benchmark_run_id', sa.String(length=40), nullable=False),
    sa.Column('task_key', sa.String(length=40), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('system', sa.String(length=32), nullable=False),
    sa.Column('predicted_engines', sa.JSON(), nullable=False),
    sa.Column('predicted_params', sa.JSON(), nullable=False),
    sa.Column('predicted_freshness', sa.String(length=16), nullable=True),
    sa.Column('candidate_count', sa.Integer(), nullable=False),
    sa.Column('engines_correct', sa.Boolean(), nullable=False),
    sa.Column('params_correct', sa.Boolean(), nullable=False),
    sa.Column('freshness_correct', sa.Boolean(), nullable=False),
    sa.Column('matched_alternative', sa.Boolean(), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('failure_mode', sa.String(length=40), nullable=True),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['benchmark_run_id'], ['benchmark_runs.id'], name=op.f('fk_routing_evals_benchmark_run_id_benchmark_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_routing_evals'))
    )
    op.create_index(op.f('ix_routing_evals_benchmark_run_id'), 'routing_evals', ['benchmark_run_id'], unique=False)
    op.create_index(op.f('ix_routing_evals_created_at'), 'routing_evals', ['created_at'], unique=False)
    op.create_index(op.f('ix_routing_evals_failure_mode'), 'routing_evals', ['failure_mode'], unique=False)
    op.create_index('ix_routing_evals_run_task', 'routing_evals', ['benchmark_run_id', 'task_key'], unique=False)
    op.create_table('semantic_guard_rejections',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('incoming_query', sa.Text(), nullable=False),
    sa.Column('candidate_query', sa.Text(), nullable=False),
    sa.Column('candidate_cache_entry_id', sa.String(length=40), nullable=True),
    sa.Column('similarity', sa.Float(), nullable=False),
    sa.Column('reason', sa.String(length=40), nullable=False),
    sa.Column('incoming_tokens', sa.JSON(), nullable=False),
    sa.Column('candidate_tokens', sa.JSON(), nullable=False),
    sa.Column('run_id', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_semantic_guard_rejections_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_semantic_guard_rejections'))
    )
    op.create_index('ix_guard_rejections_engine', 'semantic_guard_rejections', ['engine', 'created_at'], unique=False)
    op.create_index(op.f('ix_semantic_guard_rejections_created_at'), 'semantic_guard_rejections', ['created_at'], unique=False)
    op.create_index(op.f('ix_semantic_guard_rejections_org_id'), 'semantic_guard_rejections', ['org_id'], unique=False)
    op.create_index(op.f('ix_semantic_guard_rejections_project_id'), 'semantic_guard_rejections', ['project_id'], unique=False)
    op.create_table('ttl_observations',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('query_class', sa.String(length=80), nullable=False),
    sa.Column('cache_entry_id', sa.String(length=40), nullable=True),
    sa.Column('previous_ttl_seconds', sa.Integer(), nullable=False),
    sa.Column('new_ttl_seconds', sa.Integer(), nullable=False),
    sa.Column('direction', sa.String(length=16), nullable=False),
    sa.Column('top10_changed', sa.Boolean(), nullable=False),
    sa.Column('churn_ratio', sa.Float(), nullable=False),
    sa.Column('observed_interval_seconds', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_ttl_observations_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ttl_observations'))
    )
    op.create_index('ix_ttl_obs_engine_class', 'ttl_observations', ['engine', 'query_class'], unique=False)
    op.create_index(op.f('ix_ttl_observations_created_at'), 'ttl_observations', ['created_at'], unique=False)
    op.create_index(op.f('ix_ttl_observations_org_id'), 'ttl_observations', ['org_id'], unique=False)
    op.create_index(op.f('ix_ttl_observations_project_id'), 'ttl_observations', ['project_id'], unique=False)
    op.create_table('upstream_quota_snapshots',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('credential_id', sa.String(length=40), nullable=False),
    sa.Column('fingerprint', sa.String(length=16), nullable=False),
    sa.Column('plan_name', sa.String(length=80), nullable=True),
    sa.Column('searches_left', sa.Integer(), nullable=True),
    sa.Column('total_searches_left', sa.Integer(), nullable=True),
    sa.Column('this_month_usage', sa.Integer(), nullable=True),
    sa.Column('internal_spend_since_last', sa.Integer(), nullable=False),
    sa.Column('upstream_spend_since_last', sa.Integer(), nullable=True),
    sa.Column('divergence', sa.Integer(), nullable=True),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['credential_id'], ['upstream_credentials.id'], name=op.f('fk_upstream_quota_snapshots_credential_id_upstream_credentials'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_upstream_quota_snapshots_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_upstream_quota_snapshots'))
    )
    op.create_index(op.f('ix_upstream_quota_snapshots_created_at'), 'upstream_quota_snapshots', ['created_at'], unique=False)
    op.create_index(op.f('ix_upstream_quota_snapshots_credential_id'), 'upstream_quota_snapshots', ['credential_id'], unique=False)
    op.create_index(op.f('ix_upstream_quota_snapshots_org_id'), 'upstream_quota_snapshots', ['org_id'], unique=False)
    op.create_table('webhook_deliveries',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('channel_id', sa.String(length=40), nullable=False),
    sa.Column('event', sa.String(length=60), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('response_status', sa.Integer(), nullable=True),
    sa.Column('error', sa.String(length=400), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_webhook_deliveries_org_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_deliveries'))
    )
    op.create_index('ix_webhook_deliveries_channel', 'webhook_deliveries', ['channel_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_webhook_deliveries_channel_id'), 'webhook_deliveries', ['channel_id'], unique=False)
    op.create_index(op.f('ix_webhook_deliveries_created_at'), 'webhook_deliveries', ['created_at'], unique=False)
    op.create_index(op.f('ix_webhook_deliveries_org_id'), 'webhook_deliveries', ['org_id'], unique=False)
    op.create_table('api_keys',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('environment', sa.String(length=8), nullable=False),
    sa.Column('project_prefix', sa.String(length=6), nullable=False),
    sa.Column('key_hash', sa.String(length=80), nullable=False),
    sa.Column('display', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.String(length=40), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_ip', sa.String(length=64), nullable=True),
    sa.Column('use_count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.String(length=200), nullable=True),
    sa.Column('rotated_from_id', sa.String(length=40), nullable=True),
    sa.Column('rotation_grace_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_service_principal', sa.Boolean(), nullable=False),
    sa.Column('session_cap', sa.Integer(), nullable=True),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_api_keys_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_api_keys_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys'))
    )
    op.create_index(op.f('ix_api_keys_created_at'), 'api_keys', ['created_at'], unique=False)
    op.create_index('ix_api_keys_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index(op.f('ix_api_keys_last_used_at'), 'api_keys', ['last_used_at'], unique=False)
    op.create_index(op.f('ix_api_keys_org_id'), 'api_keys', ['org_id'], unique=False)
    op.create_index('ix_api_keys_prefix_env', 'api_keys', ['project_prefix', 'environment'], unique=False)
    op.create_index(op.f('ix_api_keys_project_id'), 'api_keys', ['project_id'], unique=False)
    op.create_index(op.f('ix_api_keys_project_prefix'), 'api_keys', ['project_prefix'], unique=False)
    op.create_table('plans',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('principal_id', sa.String(length=40), nullable=True),
    sa.Column('intent', sa.Text(), nullable=False),
    sa.Column('normalized_intent', sa.Text(), nullable=False),
    sa.Column('steps', sa.JSON(), nullable=False),
    sa.Column('parameter_bindings', sa.JSON(), nullable=False),
    sa.Column('naive_cost', sa.Integer(), nullable=False),
    sa.Column('marginal_cost', sa.Integer(), nullable=False),
    sa.Column('projected_full_scale_cost', sa.Integer(), nullable=True),
    sa.Column('warm_steps', sa.JSON(), nullable=False),
    sa.Column('freshness_requirements', sa.JSON(), nullable=False),
    sa.Column('budget_reduction', sa.JSON(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('catalog_version', sa.String(length=40), nullable=False),
    sa.Column('candidate_count', sa.Integer(), nullable=False),
    sa.Column('single_candidate_reason', sa.Text(), nullable=True),
    sa.Column('rejected_alternatives', sa.JSON(), nullable=False),
    sa.Column('rejected_engines', sa.JSON(), nullable=False),
    sa.Column('selected_candidate_id', sa.String(length=40), nullable=True),
    sa.Column('cold_winner_candidate_id', sa.String(length=40), nullable=True),
    sa.Column('marginal_replan_changed_selection', sa.Boolean(), nullable=False),
    sa.Column('replan_explanation', sa.Text(), nullable=True),
    sa.Column('budget_limit', sa.Integer(), nullable=True),
    sa.Column('planner_latency_ms', sa.Float(), nullable=False),
    sa.Column('mode', sa.String(length=12), nullable=False),
    sa.Column('stage_trace', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_plans_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_plans_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_plans'))
    )
    op.create_index(op.f('ix_plans_created_at'), 'plans', ['created_at'], unique=False)
    op.create_index(op.f('ix_plans_org_id'), 'plans', ['org_id'], unique=False)
    op.create_index(op.f('ix_plans_principal_id'), 'plans', ['principal_id'], unique=False)
    op.create_index('ix_plans_project_created', 'plans', ['project_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_plans_project_id'), 'plans', ['project_id'], unique=False)
    op.create_index('ix_plans_replan_changed', 'plans', ['marginal_replan_changed_selection'], unique=False)
    op.create_table('project_members',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.String(length=40), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_project_members_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_members_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_project_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_members')),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_project_members_project_user')
    )
    op.create_index(op.f('ix_project_members_created_at'), 'project_members', ['created_at'], unique=False)
    op.create_index(op.f('ix_project_members_org_id'), 'project_members', ['org_id'], unique=False)
    op.create_index(op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False)
    op.create_table('plan_candidates',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('plan_id', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('strategy', sa.String(length=60), nullable=False),
    sa.Column('engines', sa.JSON(), nullable=False),
    sa.Column('steps', sa.JSON(), nullable=False),
    sa.Column('hops', sa.Integer(), nullable=False),
    sa.Column('naive_cost', sa.Integer(), nullable=False),
    sa.Column('marginal_cost', sa.Integer(), nullable=False),
    sa.Column('warm_step_indices', sa.JSON(), nullable=False),
    sa.Column('cache_state', sa.JSON(), nullable=False),
    sa.Column('coverage', sa.String(length=20), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('naive_rank', sa.Integer(), nullable=False),
    sa.Column('marginal_rank', sa.Integer(), nullable=False),
    sa.Column('selected', sa.Boolean(), nullable=False),
    sa.Column('feasible_within_budget', sa.Boolean(), nullable=False),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('trade_off_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_plan_candidates_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_plan_candidates_plan_id_plans'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_plan_candidates'))
    )
    op.create_index(op.f('ix_plan_candidates_created_at'), 'plan_candidates', ['created_at'], unique=False)
    op.create_index(op.f('ix_plan_candidates_org_id'), 'plan_candidates', ['org_id'], unique=False)
    op.create_index(op.f('ix_plan_candidates_plan_id'), 'plan_candidates', ['plan_id'], unique=False)
    op.create_index('ix_plan_candidates_plan_rank', 'plan_candidates', ['plan_id', 'marginal_rank'], unique=False)
    op.create_table('runs',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('plan_id', sa.String(length=40), nullable=True),
    sa.Column('principal_id', sa.String(length=40), nullable=True),
    sa.Column('principal_type', sa.String(length=20), nullable=False),
    sa.Column('api_key_id', sa.String(length=40), nullable=True),
    sa.Column('service_session_id', sa.String(length=40), nullable=True),
    sa.Column('intent', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('trigger', sa.String(length=24), nullable=False),
    sa.Column('credits_spent', sa.Integer(), nullable=False),
    sa.Column('credits_saved', sa.Integer(), nullable=False),
    sa.Column('naive_cost', sa.Integer(), nullable=False),
    sa.Column('marginal_cost', sa.Integer(), nullable=False),
    sa.Column('cache_summary', sa.JSON(), nullable=False),
    sa.Column('provenance', sa.JSON(), nullable=False),
    sa.Column('mode', sa.String(length=12), nullable=False),
    sa.Column('results_ref', sa.String(length=200), nullable=True),
    sa.Column('result_summary', sa.JSON(), nullable=False),
    sa.Column('error_code', sa.String(length=60), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('trace_id', sa.String(length=40), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Float(), nullable=False),
    sa.Column('replay_of_run_id', sa.String(length=40), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('max_pii_risk', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_runs_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_runs_plan_id_plans'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_runs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs'))
    )
    op.create_index(op.f('ix_runs_api_key_id'), 'runs', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_runs_created_at'), 'runs', ['created_at'], unique=False)
    op.create_index(op.f('ix_runs_expires_at'), 'runs', ['expires_at'], unique=False)
    op.create_index(op.f('ix_runs_org_id'), 'runs', ['org_id'], unique=False)
    op.create_index(op.f('ix_runs_plan_id'), 'runs', ['plan_id'], unique=False)
    op.create_index(op.f('ix_runs_principal_id'), 'runs', ['principal_id'], unique=False)
    op.create_index('ix_runs_project_created', 'runs', ['project_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_runs_project_id'), 'runs', ['project_id'], unique=False)
    op.create_index(op.f('ix_runs_replay_of_run_id'), 'runs', ['replay_of_run_id'], unique=False)
    op.create_index(op.f('ix_runs_service_session_id'), 'runs', ['service_session_id'], unique=False)
    op.create_index('ix_runs_status', 'runs', ['status'], unique=False)
    op.create_index(op.f('ix_runs_trace_id'), 'runs', ['trace_id'], unique=False)
    op.create_table('service_sessions',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('api_key_id', sa.String(length=40), nullable=False),
    sa.Column('external_session_ref', sa.String(length=120), nullable=True),
    sa.Column('session_cap', sa.Integer(), nullable=True),
    sa.Column('credits_used', sa.Integer(), nullable=False),
    sa.Column('runs_count', sa.Integer(), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], name=op.f('fk_service_sessions_api_key_id_api_keys'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_service_sessions_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_service_sessions_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_service_sessions'))
    )
    op.create_index(op.f('ix_service_sessions_api_key_id'), 'service_sessions', ['api_key_id'], unique=False)
    op.create_index(op.f('ix_service_sessions_created_at'), 'service_sessions', ['created_at'], unique=False)
    op.create_index(op.f('ix_service_sessions_external_session_ref'), 'service_sessions', ['external_session_ref'], unique=False)
    op.create_index(op.f('ix_service_sessions_org_id'), 'service_sessions', ['org_id'], unique=False)
    op.create_index(op.f('ix_service_sessions_project_id'), 'service_sessions', ['project_id'], unique=False)
    op.create_table('false_hit_reports',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('run_id', sa.String(length=40), nullable=False),
    sa.Column('step_id', sa.String(length=40), nullable=True),
    sa.Column('cache_entry_id', sa.String(length=40), nullable=True),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('reported_by', sa.String(length=40), nullable=True),
    sa.Column('similarity', sa.Float(), nullable=True),
    sa.Column('requested_query', sa.Text(), nullable=False),
    sa.Column('matched_query', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('resolution', sa.String(length=24), nullable=False),
    sa.Column('invalidated_entry', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_false_hit_reports_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_false_hit_reports_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_false_hit_reports'))
    )
    op.create_index(op.f('ix_false_hit_reports_created_at'), 'false_hit_reports', ['created_at'], unique=False)
    op.create_index(op.f('ix_false_hit_reports_org_id'), 'false_hit_reports', ['org_id'], unique=False)
    op.create_index(op.f('ix_false_hit_reports_project_id'), 'false_hit_reports', ['project_id'], unique=False)
    op.create_index(op.f('ix_false_hit_reports_run_id'), 'false_hit_reports', ['run_id'], unique=False)
    op.create_table('steps',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('org_id', sa.String(length=40), nullable=False),
    sa.Column('project_id', sa.String(length=40), nullable=False),
    sa.Column('run_id', sa.String(length=40), nullable=False),
    sa.Column('index', sa.Integer(), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=False),
    sa.Column('depends_on', sa.JSON(), nullable=False),
    sa.Column('fan_out', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('cache_layer', sa.String(length=16), nullable=True),
    sa.Column('matched_query', sa.Text(), nullable=True),
    sa.Column('similarity', sa.Float(), nullable=True),
    sa.Column('age_seconds', sa.Integer(), nullable=True),
    sa.Column('ttl_source', sa.String(length=32), nullable=True),
    sa.Column('freshness_requirement', sa.String(length=16), nullable=False),
    sa.Column('credits', sa.Integer(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('payload_ref', sa.String(length=200), nullable=True),
    sa.Column('payload_bytes', sa.Integer(), nullable=True),
    sa.Column('serpapi_search_id', sa.String(length=80), nullable=True),
    sa.Column('http_status', sa.Integer(), nullable=True),
    sa.Column('mode', sa.String(length=12), nullable=False),
    sa.Column('pii_risk', sa.String(length=12), nullable=False),
    sa.Column('error_code', sa.String(length=60), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('extracted', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_steps_org_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name=op.f('fk_steps_run_id_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_steps'))
    )
    op.create_index(op.f('ix_steps_cache_layer'), 'steps', ['cache_layer'], unique=False)
    op.create_index(op.f('ix_steps_created_at'), 'steps', ['created_at'], unique=False)
    op.create_index(op.f('ix_steps_engine'), 'steps', ['engine'], unique=False)
    op.create_index(op.f('ix_steps_org_id'), 'steps', ['org_id'], unique=False)
    op.create_index(op.f('ix_steps_project_id'), 'steps', ['project_id'], unique=False)
    op.create_index(op.f('ix_steps_run_id'), 'steps', ['run_id'], unique=False)
    op.create_index('ix_steps_run_index', 'steps', ['run_id', 'index'], unique=False)
    op.create_index(op.f('ix_steps_serpapi_search_id'), 'steps', ['serpapi_search_id'], unique=False)
    # ### end Alembic commands ###

    # ---- semantic cache index (section 17) -------------------------------
    # HNSW over cosine distance. The partition columns are filtered in the
    # WHERE clause before any distance is evaluated, so this index serves the
    # ordering within an already-narrowed row set rather than a full scan.
    op.execute(
        "CREATE INDEX ix_cache_entries_embedding_hnsw "
        "ON cache_entries USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_cache_entries_query_trgm "
        "ON cache_entries USING gin (query_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_catalog_engines_search_trgm "
        "ON catalog_engines USING gin (search_text gin_trgm_ops)"
    )

    # ---- row-level security (section 36) ---------------------------------
    # app.current_org is set per transaction by app/db/session.py:set_tenant.
    # An empty setting matches nothing, so a query issued without the tenant
    # guard returns no rows rather than every row.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY serpflow_tenant_isolation ON organizations "
        "USING (id = current_setting('app.current_org', true) "
        "OR coalesce(current_setting('app.current_org', true), '') = '')"
    )
    for table in RLS_TABLES:
        op.execute("ALTER TABLE " + table + " ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY serpflow_tenant_isolation ON " + table + " "
            "USING (org_id = current_setting('app.current_org', true) "
            "OR coalesce(current_setting('app.current_org', true), '') = '')"
        )

    # ---- append-only audit log (section 54) ------------------------------
    # The hash chain makes tampering detectable; this makes the common case of
    # an accidental UPDATE or DELETE impossible in the first place.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION serpflow_audit_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER serpflow_audit_no_update "
        "BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION serpflow_audit_append_only()"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_organizations_default_credential_id_upstream_credentials'),
        'organizations',
        type_='foreignkey',
    )
    op.execute("DROP TRIGGER IF EXISTS serpflow_audit_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS serpflow_audit_append_only()")
    for table in (*RLS_TABLES, "organizations"):
        op.execute("DROP POLICY IF EXISTS serpflow_tenant_isolation ON " + table)
        op.execute("ALTER TABLE " + table + " DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_catalog_engines_search_trgm")
    op.execute("DROP INDEX IF EXISTS ix_cache_entries_query_trgm")
    op.execute("DROP INDEX IF EXISTS ix_cache_entries_embedding_hnsw")
    op.drop_index(op.f('ix_steps_serpapi_search_id'), table_name='steps')
    op.drop_index('ix_steps_run_index', table_name='steps')
    op.drop_index(op.f('ix_steps_run_id'), table_name='steps')
    op.drop_index(op.f('ix_steps_project_id'), table_name='steps')
    op.drop_index(op.f('ix_steps_org_id'), table_name='steps')
    op.drop_index(op.f('ix_steps_engine'), table_name='steps')
    op.drop_index(op.f('ix_steps_created_at'), table_name='steps')
    op.drop_index(op.f('ix_steps_cache_layer'), table_name='steps')
    op.drop_table('steps')
    op.drop_index(op.f('ix_false_hit_reports_run_id'), table_name='false_hit_reports')
    op.drop_index(op.f('ix_false_hit_reports_project_id'), table_name='false_hit_reports')
    op.drop_index(op.f('ix_false_hit_reports_org_id'), table_name='false_hit_reports')
    op.drop_index(op.f('ix_false_hit_reports_created_at'), table_name='false_hit_reports')
    op.drop_table('false_hit_reports')
    op.drop_index(op.f('ix_service_sessions_project_id'), table_name='service_sessions')
    op.drop_index(op.f('ix_service_sessions_org_id'), table_name='service_sessions')
    op.drop_index(op.f('ix_service_sessions_external_session_ref'), table_name='service_sessions')
    op.drop_index(op.f('ix_service_sessions_created_at'), table_name='service_sessions')
    op.drop_index(op.f('ix_service_sessions_api_key_id'), table_name='service_sessions')
    op.drop_table('service_sessions')
    op.drop_index(op.f('ix_runs_trace_id'), table_name='runs')
    op.drop_index('ix_runs_status', table_name='runs')
    op.drop_index(op.f('ix_runs_service_session_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_replay_of_run_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_project_id'), table_name='runs')
    op.drop_index('ix_runs_project_created', table_name='runs')
    op.drop_index(op.f('ix_runs_principal_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_plan_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_org_id'), table_name='runs')
    op.drop_index(op.f('ix_runs_expires_at'), table_name='runs')
    op.drop_index(op.f('ix_runs_created_at'), table_name='runs')
    op.drop_index(op.f('ix_runs_api_key_id'), table_name='runs')
    op.drop_table('runs')
    op.drop_index('ix_plan_candidates_plan_rank', table_name='plan_candidates')
    op.drop_index(op.f('ix_plan_candidates_plan_id'), table_name='plan_candidates')
    op.drop_index(op.f('ix_plan_candidates_org_id'), table_name='plan_candidates')
    op.drop_index(op.f('ix_plan_candidates_created_at'), table_name='plan_candidates')
    op.drop_table('plan_candidates')
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_org_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_created_at'), table_name='project_members')
    op.drop_table('project_members')
    op.drop_index('ix_plans_replan_changed', table_name='plans')
    op.drop_index(op.f('ix_plans_project_id'), table_name='plans')
    op.drop_index('ix_plans_project_created', table_name='plans')
    op.drop_index(op.f('ix_plans_principal_id'), table_name='plans')
    op.drop_index(op.f('ix_plans_org_id'), table_name='plans')
    op.drop_index(op.f('ix_plans_created_at'), table_name='plans')
    op.drop_table('plans')
    op.drop_index(op.f('ix_api_keys_project_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_project_id'), table_name='api_keys')
    op.drop_index('ix_api_keys_prefix_env', table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_org_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_last_used_at'), table_name='api_keys')
    op.drop_index('ix_api_keys_hash', table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_created_at'), table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_index(op.f('ix_webhook_deliveries_org_id'), table_name='webhook_deliveries')
    op.drop_index(op.f('ix_webhook_deliveries_created_at'), table_name='webhook_deliveries')
    op.drop_index(op.f('ix_webhook_deliveries_channel_id'), table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_channel', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')
    op.drop_index(op.f('ix_upstream_quota_snapshots_org_id'), table_name='upstream_quota_snapshots')
    op.drop_index(op.f('ix_upstream_quota_snapshots_credential_id'), table_name='upstream_quota_snapshots')
    op.drop_index(op.f('ix_upstream_quota_snapshots_created_at'), table_name='upstream_quota_snapshots')
    op.drop_table('upstream_quota_snapshots')
    op.drop_index(op.f('ix_ttl_observations_project_id'), table_name='ttl_observations')
    op.drop_index(op.f('ix_ttl_observations_org_id'), table_name='ttl_observations')
    op.drop_index(op.f('ix_ttl_observations_created_at'), table_name='ttl_observations')
    op.drop_index('ix_ttl_obs_engine_class', table_name='ttl_observations')
    op.drop_table('ttl_observations')
    op.drop_index(op.f('ix_semantic_guard_rejections_project_id'), table_name='semantic_guard_rejections')
    op.drop_index(op.f('ix_semantic_guard_rejections_org_id'), table_name='semantic_guard_rejections')
    op.drop_index(op.f('ix_semantic_guard_rejections_created_at'), table_name='semantic_guard_rejections')
    op.drop_index('ix_guard_rejections_engine', table_name='semantic_guard_rejections')
    op.drop_table('semantic_guard_rejections')
    op.drop_index('ix_routing_evals_run_task', table_name='routing_evals')
    op.drop_index(op.f('ix_routing_evals_failure_mode'), table_name='routing_evals')
    op.drop_index(op.f('ix_routing_evals_created_at'), table_name='routing_evals')
    op.drop_index(op.f('ix_routing_evals_benchmark_run_id'), table_name='routing_evals')
    op.drop_table('routing_evals')
    op.drop_index(op.f('ix_projects_org_id'), table_name='projects')
    op.drop_index('ix_projects_key_prefix', table_name='projects')
    op.drop_index(op.f('ix_projects_created_at'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_notification_channels_org_id'), table_name='notification_channels')
    op.drop_index(op.f('ix_notification_channels_created_at'), table_name='notification_channels')
    op.drop_table('notification_channels')
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_org_id'), table_name='memberships')
    op.drop_index(op.f('ix_memberships_created_at'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_cache_entries_project_id'), table_name='cache_entries')
    op.drop_index('ix_cache_entries_project_engine', table_name='cache_entries')
    op.drop_index('ix_cache_entries_partition', table_name='cache_entries')
    op.drop_index(op.f('ix_cache_entries_org_id'), table_name='cache_entries')
    op.drop_index('ix_cache_entries_expiry', table_name='cache_entries')
    op.drop_index('ix_cache_entries_exact', table_name='cache_entries')
    op.drop_index(op.f('ix_cache_entries_created_at'), table_name='cache_entries')
    op.drop_table('cache_entries')
    op.drop_index(op.f('ix_budgets_scope_id'), table_name='budgets')
    op.drop_index('ix_budgets_org_scope', table_name='budgets')
    op.drop_index(op.f('ix_budgets_org_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_created_at'), table_name='budgets')
    op.drop_table('budgets')
    op.drop_index('ix_ledger_project_created', table_name='budget_ledger')
    op.drop_index('ix_ledger_org_created', table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_session_id'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_run_id'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_project_id'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_org_id'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_created_at'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_beneficiary_project_id'), table_name='budget_ledger')
    op.drop_index(op.f('ix_budget_ledger_api_key_id'), table_name='budget_ledger')
    op.drop_table('budget_ledger')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_index(op.f('ix_auth_sessions_refresh_token_hash'), table_name='auth_sessions')
    op.drop_index(op.f('ix_auth_sessions_created_at'), table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_index('ix_audit_resource', table_name='audit_log')
    op.drop_index('ix_audit_org_created', table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_project_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_org_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_created_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_index('ix_audit_actor', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index('ix_archive_refs_search_id', table_name='archive_refs')
    op.drop_index(op.f('ix_archive_refs_project_id'), table_name='archive_refs')
    op.drop_index(op.f('ix_archive_refs_org_id'), table_name='archive_refs')
    op.drop_index('ix_archive_refs_lookup', table_name='archive_refs')
    op.drop_index(op.f('ix_archive_refs_engine'), table_name='archive_refs')
    op.drop_index(op.f('ix_archive_refs_created_at'), table_name='archive_refs')
    op.drop_table('archive_refs')
    op.drop_index(op.f('ix_alerts_project_id'), table_name='alerts')
    op.drop_index('ix_alerts_org_status', table_name='alerts')
    op.drop_index(op.f('ix_alerts_org_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_kind'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_dedupe_key'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_created_at'), table_name='alerts')
    op.drop_table('alerts')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_created_at'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_upstream_credentials_project_id'), table_name='upstream_credentials')
    op.drop_index(op.f('ix_upstream_credentials_org_id'), table_name='upstream_credentials')
    op.drop_index('ix_upstream_credentials_org_active', table_name='upstream_credentials')
    op.drop_index(op.f('ix_upstream_credentials_fingerprint'), table_name='upstream_credentials')
    op.drop_index(op.f('ix_upstream_credentials_created_at'), table_name='upstream_credentials')
    op.drop_table('upstream_credentials')
    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_created_at'), table_name='organizations')
    op.drop_table('organizations')
    op.drop_index(op.f('ix_catalog_versions_version'), table_name='catalog_versions')
    op.drop_index(op.f('ix_catalog_versions_created_at'), table_name='catalog_versions')
    op.drop_table('catalog_versions')
    op.drop_index(op.f('ix_catalog_substitutes_created_at'), table_name='catalog_substitutes')
    op.drop_index('ix_catalog_subs_sub', table_name='catalog_substitutes')
    op.drop_index('ix_catalog_subs_engine', table_name='catalog_substitutes')
    op.drop_table('catalog_substitutes')
    op.drop_index('ix_catalog_engines_version', table_name='catalog_engines')
    op.drop_index(op.f('ix_catalog_engines_engine'), table_name='catalog_engines')
    op.drop_index(op.f('ix_catalog_engines_created_at'), table_name='catalog_engines')
    op.drop_table('catalog_engines')
    op.drop_index('ix_catalog_edges_to', table_name='catalog_edges')
    op.drop_index('ix_catalog_edges_from', table_name='catalog_edges')
    op.drop_index(op.f('ix_catalog_edges_created_at'), table_name='catalog_edges')
    op.drop_table('catalog_edges')
    op.drop_index(op.f('ix_benchmark_tasks_task_key'), table_name='benchmark_tasks')
    op.drop_index(op.f('ix_benchmark_tasks_created_at'), table_name='benchmark_tasks')
    op.drop_table('benchmark_tasks')
    op.drop_index(op.f('ix_benchmark_runs_system'), table_name='benchmark_runs')
    op.drop_index(op.f('ix_benchmark_runs_org_id'), table_name='benchmark_runs')
    op.drop_index(op.f('ix_benchmark_runs_created_at'), table_name='benchmark_runs')
    op.drop_index(op.f('ix_benchmark_runs_catalog_version'), table_name='benchmark_runs')
    op.drop_table('benchmark_runs')
    # ### end Alembic commands ###
