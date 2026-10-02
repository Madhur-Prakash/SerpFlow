"""Email rendering and transport selection.

The thing most worth asserting is what must *not* appear: a rendered body
carries a single-use token, so the console backend must never write one to a
log, and the templates must escape what they interpolate.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.services.email import service as email


@pytest.fixture
def local_settings() -> Settings:
    return Settings(
        frontend_url="http://localhost:5173",
        gmail_credentials_b64="",
        gmail_sender="",
        email_from_name="SerpFlow",
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def test_verify_email_carries_the_token_in_the_link(local_settings):
    rendered = email.render_verify_email("Ada", "tok_abc123", local_settings)
    assert "tok_abc123" in rendered.html
    assert "tok_abc123" in rendered.text
    assert "/verify-email?token=tok_abc123" in rendered.text


def test_password_reset_points_at_the_reset_route(local_settings):
    rendered = email.render_password_reset("Ada", "tok_reset", local_settings)
    assert "/reset-password?token=tok_reset" in rendered.text
    assert rendered.subject == "Reset your SerpFlow password"


def test_both_formats_are_rendered(local_settings):
    rendered = email.render_verify_email("Ada", "t", local_settings)
    assert rendered.html.lstrip().startswith("<!DOCTYPE html>")
    assert "<" not in rendered.text.split("http")[0]


def test_templates_escape_interpolated_values(local_settings):
    """A display name is user-supplied. It must not become markup."""
    rendered = email.render_alert(
        recipient_name='<script>alert("x")</script>',
        kind="budget.exhausted",
        title="Budget exhausted",
        message="Spent it all.",
        settings=local_settings,
    )
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html


def test_a_template_referencing_an_unknown_variable_fails_loudly():
    """StrictUndefined: a missing variable is a bug, not a blank gap in an inbox."""
    from jinja2 import UndefinedError

    env = email.get_template_env()
    template = env.from_string("{{ never_passed }}")
    with pytest.raises(UndefinedError):
        template.render()


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (86400, "1 day"),
        (172800, "2 days"),
        (3600, "1 hour"),
        (7200, "2 hours"),
        (900, "15 minutes"),
    ],
)
def test_durations_read_like_english(seconds, expected):
    assert email._duration(seconds) == expected


def test_alert_renders_its_detail_rows(local_settings):
    rendered = email.render_alert(
        recipient_name="Ada",
        kind="budget.threshold",
        title="Budget at 80%",
        message="The Review Intelligence budget is nearly spent.",
        details=[("Project", "Review Intelligence"), ("Limit", "60 credits")],
        settings=local_settings,
    )
    assert "Review Intelligence" in rendered.html
    assert "Limit: 60 credits" in rendered.text


# --------------------------------------------------------------------------
# Transport selection
# --------------------------------------------------------------------------
def test_console_backend_when_no_credential_is_configured():
    email.set_email_backend(None)
    try:
        assert isinstance(email.get_email_backend(), email.ConsoleEmailBackend)
    finally:
        email.set_email_backend(None)


def test_gmail_backend_refuses_to_send_without_a_credential():
    backend = email.GmailEmailBackend(Settings(gmail_credentials_b64=""))
    message = email.OutgoingEmail(to="a@b.dev", subject="s", html="<p>h</p>", text="t")
    with pytest.raises(email.EmailSendError, match="GMAIL_CREDENTIALS_B64"):
        asyncio.run(backend.send(message))


def test_configuring_a_credential_is_what_selects_gmail():
    """There is no third setting to get wrong."""
    assert Settings(gmail_credentials_b64="").email_configured is False
    assert Settings(gmail_credentials_b64="blob").email_configured is True


def test_sender_header_uses_the_consented_mailbox():
    s = Settings(gmail_sender="ops@example.dev", email_from_name="SerpFlow")
    assert s.email_sender == "SerpFlow <ops@example.dev>"


# --------------------------------------------------------------------------
# MIME
# --------------------------------------------------------------------------
def test_mime_is_multipart_alternative_with_both_bodies():
    mime = email.build_mime(
        email.OutgoingEmail(to="a@b.dev", subject="Hello", html="<p>hi</p>", text="hi"),
        "SerpFlow <ops@example.dev>",
    )
    assert mime["To"] == "a@b.dev"
    assert mime["Subject"] == "Hello"
    assert mime["Message-ID"]
    types = {part.get_content_type() for part in mime.walk()}
    assert "text/plain" in types
    assert "text/html" in types


def test_console_backend_never_logs_the_body(caplog, local_settings):
    """Bodies hold single-use tokens. The log gets the subject and nothing more."""
    rendered = email.render_verify_email("Ada", "tok_secret_value", local_settings)
    message = email.OutgoingEmail(
        to="ada@example.dev", subject=rendered.subject, html=rendered.html, text=rendered.text
    )
    with caplog.at_level("INFO"):
        asyncio.run(email.ConsoleEmailBackend().send(message))

    record = next(r for r in caplog.records if getattr(r, "event", "") == "email.sent")
    # Recipient and subject are structured fields, so the message stays
    # greppable. The body is on neither.
    assert record.to == "ada@example.dev"
    assert record.subject == rendered.subject
    assert "tok_secret_value" not in caplog.text
    assert not any("tok_secret_value" in str(v) for v in vars(record).values())


# --------------------------------------------------------------------------
# Gmail failure classification
# --------------------------------------------------------------------------
def test_a_revoked_token_is_not_retried():
    from google.auth.exceptions import RefreshError

    assert email._gmail_transient(RefreshError("invalid_grant")) is False


@pytest.mark.parametrize("exc", [TimeoutError(), OSError()])
def test_network_failures_are_retried(exc):
    assert email._gmail_transient(exc) is True


def test_invalid_grant_explains_the_cause_that_the_error_hides():
    from google.auth.exceptions import RefreshError

    reason = email._gmail_reason(RefreshError("invalid_grant"))
    assert "mint_gmail_token.py" in reason
    assert "Testing" in reason
