"""API keys, passwords, the credential vault, RBAC, TTL and redaction."""

from __future__ import annotations

import logging
import re

import pytest

from app.core import permissions as perms
from app.core.logging import CredentialRedactionFilter, redact_mapping, redact_text
from app.core.permissions import Permission, Role, has_permission, require_permission
from app.core.security import (
    API_KEY_PATTERN,
    credential_fingerprint,
    decrypt_credential,
    encrypt_credential,
    generate_project_prefix,
    hash_api_key,
    hash_password,
    mint_api_key,
    parse_api_key,
    verify_api_key,
    verify_password,
)
from app.services.cache import ttl


# --------------------------------------------------------------------------
# API keys (sections 28-32)
# --------------------------------------------------------------------------
def test_key_format_matches_the_specification():
    """sf_<env>_<6-char project prefix>_<32-char secret>."""
    minted = mint_api_key("live", "pm8kd3")
    assert API_KEY_PATTERN.match(minted.plaintext)
    env, prefix, secret = minted.plaintext.split("_")[1:]
    assert env == "live"
    assert prefix == "pm8kd3"
    assert len(secret) == 32


def test_display_never_shows_the_secret():
    minted = mint_api_key("live", "pm8kd3")
    assert minted.display == "sf_live_pm8kd3_••••"
    assert minted.plaintext.split("_")[-1] not in minted.display


def test_keys_are_hmac_hashed_not_argon2():
    """Section 31: API keys carry 190+ bits of entropy, so there is no
    brute-force surface to stretch against. Argon2 would add 50-100ms to every
    request for no security gain."""
    minted = mint_api_key("test", "abc123")
    assert re.fullmatch(r"[0-9a-f]{64}", minted.key_hash)
    assert not minted.key_hash.startswith("$argon2")


def test_key_verification_is_exact():
    minted = mint_api_key("live", "abc123")
    assert verify_api_key(minted.plaintext, minted.key_hash)
    assert not verify_api_key(minted.plaintext[:-1] + "X", minted.key_hash)


def test_key_hash_is_stable():
    minted = mint_api_key("live", "abc123")
    assert hash_api_key(minted.plaintext) == minted.key_hash


def test_minted_keys_are_unique():
    prefix = generate_project_prefix()
    assert len({mint_api_key("live", prefix).plaintext for _ in range(200)}) == 200


@pytest.mark.parametrize(
    "candidate",
    ["", "nonsense", "sf_live_short_x", "sf_prod_abc123_" + "a" * 32, "sf_live_ABC123_" + "a" * 32],
)
def test_malformed_keys_are_rejected(candidate):
    assert parse_api_key(candidate) is None


def test_test_keys_are_identifiable_before_any_database_lookup():
    """Mode precedence needs to know the environment from the key itself."""
    parsed = parse_api_key(mint_api_key("test", "abc123").plaintext)
    assert parsed is not None and parsed.is_test


def test_key_rejects_an_invalid_environment():
    with pytest.raises(ValueError):
        mint_api_key("production", "abc123")


# --------------------------------------------------------------------------
# passwords (sections 31, 62)
# --------------------------------------------------------------------------
def test_passwords_use_argon2id():
    digest = hash_password("correct horse battery staple")
    assert digest.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", digest)
    assert not verify_password("wrong", digest)


def test_password_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


# --------------------------------------------------------------------------
# credential vault (section 24)
# --------------------------------------------------------------------------
def test_envelope_encryption_round_trips():
    secret = "a" * 64
    envelope = encrypt_credential(secret)
    assert decrypt_credential(envelope.ciphertext, envelope.encrypted_dek) == secret


def test_ciphertext_never_contains_the_secret():
    secret = "deadbeef" * 8
    envelope = encrypt_credential(secret)
    assert secret not in envelope.ciphertext
    assert secret not in envelope.encrypted_dek


def test_each_credential_gets_its_own_data_key():
    secret = "a" * 64
    first, second = encrypt_credential(secret), encrypt_credential(secret)
    assert first.ciphertext != second.ciphertext
    assert first.encrypted_dek != second.encrypted_dek
    assert first.fingerprint == second.fingerprint


def test_fingerprint_is_short_and_non_reversible():
    secret = "a" * 64
    fingerprint = credential_fingerprint(secret)
    assert len(fingerprint) == 8
    assert secret not in fingerprint
    assert fingerprint == credential_fingerprint(secret)


def test_credential_response_schema_has_no_secret_field():
    """Section 25: the field must be absent, not excluded. Excluded fields leak
    through serialisation bugs."""
    from app.schemas.identity import CredentialResponse

    forbidden = {"api_key", "secret", "ciphertext", "encrypted_dek", "key", "plaintext"}
    assert not (set(CredentialResponse.model_fields) & forbidden)


def test_no_response_schema_anywhere_exposes_a_credential():
    import inspect

    from pydantic import BaseModel

    from app import schemas

    forbidden = {"api_key", "serpapi_api_key", "ciphertext", "encrypted_dek", "secret"}
    for _, obj in inspect.getmembers(schemas):
        if not (inspect.isclass(obj) and issubclass(obj, BaseModel)):
            continue
        if obj.__name__.endswith(("Request", "Create", "Rotate", "Update", "Confirm")):
            continue  # request models legitimately accept a secret
        assert not (set(obj.model_fields) & forbidden), obj.__name__


# --------------------------------------------------------------------------
# redaction (section 64)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "secret",
    [
        "sf_live_pm8kd3_v1a7Qx9mNc2PfLz4Rt6WbYs8KdJh3Gn5",
        "a" * 64,
        "gsk_" + "b" * 40,
        "sk-" + "c" * 40,
    ],
)
def test_secrets_are_scrubbed_from_log_text(secret):
    assert secret not in redact_text("upstream call failed with key " + secret)


def test_sensitive_keys_are_scrubbed_from_mappings():
    scrubbed = redact_mapping(
        {"api_key": "a" * 64, "nested": {"password": "hunter2"}, "engine": "google"}
    )
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["nested"]["password"] == "[REDACTED]"
    assert scrubbed["engine"] == "google"


def test_redaction_filter_scrubs_the_exception_path():
    """Section 64: the leak path is always an exception handler."""
    secret = "d" * 64
    record = logging.LogRecord(
        name="t",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed for %s",
        args=(secret,),
        exc_info=None,
    )
    assert CredentialRedactionFilter().filter(record)
    assert secret not in record.getMessage()


def test_redaction_filter_scrubs_key_value_pairs():
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='request params {"api_key": "zzzz-very-secret-value"}',
        args=(),
        exc_info=None,
    )
    CredentialRedactionFilter().filter(record)
    assert "zzzz-very-secret-value" not in record.getMessage()


# --------------------------------------------------------------------------
# RBAC (section 34)
# --------------------------------------------------------------------------
def test_analyst_can_plan_but_not_execute():
    """Planning calls an LLM, not SerpApi, so it spends nothing. That is what
    makes the analyst role useful."""
    assert has_permission(Role.ANALYST, Permission.PLAN_CREATE)
    assert not has_permission(Role.ANALYST, Permission.EXECUTE)
    assert not has_permission(Role.ANALYST, Permission.PAYLOAD_READ)


def test_developer_can_execute_but_not_manage_members():
    assert has_permission(Role.DEVELOPER, Permission.EXECUTE)
    assert has_permission(Role.DEVELOPER, Permission.PAYLOAD_READ)
    assert not has_permission(Role.DEVELOPER, Permission.MEMBER_WRITE)


def test_only_owner_can_rotate_credentials_or_delete_the_org():
    for permission in (Permission.CREDENTIAL_ROTATE, Permission.ORG_DELETE, Permission.ORG_BILLING):
        assert has_permission(Role.OWNER, permission)
        assert not has_permission(Role.ADMIN, permission)


def test_service_principal_is_scoped():
    assert has_permission(Role.SERVICE, Permission.EXECUTE)
    assert not has_permission(Role.SERVICE, Permission.MEMBER_WRITE)
    assert not has_permission(Role.SERVICE, Permission.AUDIT_READ)


def test_permission_check_denies_by_default():
    from app.core.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        require_permission(Role.ANALYST, Permission.EXECUTE)
    with pytest.raises(PermissionDeniedError):
        require_permission("not-a-role", Permission.RUN_READ)


def test_roles_are_cumulative():
    for lower, higher in (
        (Role.ANALYST, Role.DEVELOPER),
        (Role.DEVELOPER, Role.ADMIN),
        (Role.ADMIN, Role.OWNER),
    ):
        assert perms.permissions_for(lower) <= perms.permissions_for(higher)


# --------------------------------------------------------------------------
# adaptive TTL (section 20)
# --------------------------------------------------------------------------
def test_unchanged_top10_extends_the_ttl():
    decision = ttl.adapt(3600, churn=0.0, top10_unchanged=True)
    assert decision.ttl_seconds == 5400
    assert decision.direction == "extended"


def test_significant_churn_halves_the_ttl():
    decision = ttl.adapt(3600, churn=0.5, top10_unchanged=False)
    assert decision.ttl_seconds == 1800
    assert decision.direction == "shortened"


def test_minor_churn_holds_the_ttl():
    decision = ttl.adapt(3600, churn=0.1, top10_unchanged=False)
    assert decision.ttl_seconds == 3600
    assert decision.direction == "unchanged"


def test_ttl_is_clamped():
    assert ttl.adapt(1, churn=0.0, top10_unchanged=True).ttl_seconds >= 300
    assert ttl.adapt(10**9, churn=0.0, top10_unchanged=True).ttl_seconds <= 7776000


def test_ttl_seeds_from_the_volatility_prior():
    assert ttl.initial_ttl("24h").ttl_seconds == 86400
    assert ttl.initial_ttl("30d").ttl_seconds == 2592000


def test_ttl_never_outlives_the_freshness_requirement():
    """A 30-day entry serving a realtime step would be available long after it
    stopped being acceptable - the distinction section 14 turns on."""
    decision = ttl.initial_ttl("30d", freshness="realtime")
    assert decision.ttl_seconds <= 900
    assert decision.source == ttl.TTL_SOURCE_FRESHNESS


def test_ttl_is_learned_per_query_class_not_only_per_engine():
    assert ttl.query_class_key("google", "current gold price") != ttl.query_class_key(
        "google", "history of the roman empire"
    )


def test_top10_comparison_treats_reordering_as_churn():
    churn, unchanged = ttl.compare_top_results(["a", "b", "c"], ["b", "a", "c"])
    assert churn > 0
    assert not unchanged
