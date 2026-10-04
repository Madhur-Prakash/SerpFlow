"""Execution mode precedence, and the guarantees it exists to protect.

The mode decides whether a search spends real money, so the interesting tests
here are the refusals: what a caller cannot talk the resolver into.
"""

from __future__ import annotations

import pytest

from app.integrations.serpapi import (
    MODE_LIVE,
    MODE_MOCK,
    MODE_RECORD,
    MODE_REPLAY,
    resolve_mode,
)
from app.services.credentials.providers import GROQ, PROVIDER_IDS, SERPAPI, get_provider


# --------------------------------------------------------------- rule 1
def test_test_key_always_routes_to_mock_whatever_is_configured():
    """Rule 1 is absolute. Nothing below it is consulted."""
    for configured in (MODE_LIVE, MODE_RECORD, MODE_REPLAY, "nonsense", None):
        resolved = resolve_mode(key_environment="test", configured_mode=configured)
        assert resolved.mode == MODE_MOCK
        assert resolved.credited is False


def test_a_test_key_cannot_be_talked_into_spending():
    resolved = resolve_mode(key_environment="test", configured_mode=MODE_LIVE)
    assert "cannot be overridden" in resolved.reason


# --------------------------------------------------------------- rules 2-4
@pytest.mark.parametrize(
    ("configured", "expected", "credited"),
    [
        (MODE_LIVE, MODE_LIVE, True),
        (MODE_RECORD, MODE_RECORD, True),
        (MODE_REPLAY, MODE_REPLAY, False),
    ],
)
def test_configured_mode_is_honoured(configured, expected, credited):
    resolved = resolve_mode(key_environment="live", configured_mode=configured)
    assert resolved.mode == expected
    assert resolved.credited is credited


def test_only_live_and_record_are_credited():
    assert resolve_mode(key_environment="live", configured_mode=MODE_REPLAY).credited is False
    assert resolve_mode(key_environment="test").credited is False


def test_the_source_of_the_decision_is_reported():
    """The UI shows the reason verbatim, so it must name where it came from."""
    assert (
        "project"
        in resolve_mode(key_environment="live", configured_mode=MODE_LIVE, source="project").reason
    )
    assert (
        "request"
        in resolve_mode(
            key_environment="live", configured_mode=MODE_REPLAY, source="request"
        ).reason
    )


# ------------------------------------------------- the dangerous fallthrough
def test_an_unknown_mode_falls_back_to_replay_not_live():
    """Regression: the final branch used to be an unguarded `return live`.

    That was safe while the only source was a validated setting. Once a
    project row and a request body can supply the value, defaulting an
    unrecognised string to billable execution is the wrong way to be wrong.
    """
    resolved = resolve_mode(key_environment="live", configured_mode="LIVE_PLEASE")
    assert resolved.mode == MODE_REPLAY
    assert resolved.credited is False


def test_mock_cannot_be_requested_by_configuration():
    """`mock` is rule 1's answer alone.

    If it were selectable, "this run cost nothing" would be a claim anyone
    could make about any run rather than evidence that a test key was used.
    """
    resolved = resolve_mode(key_environment="live", configured_mode=MODE_MOCK)
    assert resolved.mode != MODE_MOCK
    assert resolved.credited is False


def test_an_empty_configured_mode_uses_the_instance_default():
    """Falsy means "not set", which must reach settings rather than the guard."""
    assert resolve_mode(key_environment="live", configured_mode="").mode == MODE_REPLAY


# -------------------------------------------------------- credential vault
def test_every_provider_declares_what_happens_without_it():
    for provider_id in PROVIDER_IDS:
        spec = get_provider(provider_id)
        assert spec.absent_behaviour.strip()
        assert spec.console_url.startswith("https://")
        assert spec.label.strip()


def test_serpapi_is_required_and_groq_is_not():
    assert get_provider(SERPAPI).required is True
    assert get_provider(GROQ).required is False


def test_an_unknown_provider_is_refused_by_name():
    with pytest.raises(ValueError) as caught:
        get_provider("openai")
    assert "openai" in str(caught.value)
    assert SERPAPI in str(caught.value)


def test_there_is_no_deployment_wide_serpapi_key():
    """BYOK: a setting for one existed, was read by nothing, and was removed.

    A dead variable that reads as though the platform might spend its own
    credits is worse than no variable at all.
    """
    from app.core.config import Settings

    assert not hasattr(Settings(), "serpapi_api_key")
