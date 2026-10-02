"""Email rendering (Jinja2, autoescaped) and delivery (Gmail API, or the console).

Rendered bodies carry single-use tokens inside links. They are handed straight
to the backend and are never logged or persisted: a log line carries the
template name, the subject and the recipient, and nothing else.

**Transports.** The Gmail API is what a deployment uses, and it takes over as
soon as ``GMAIL_CREDENTIALS_B64`` is set. Google refuses plain passwords, and
an app password needs 2FA plus a per-account secret a Workspace admin can
switch off, whereas a refresh token scoped to ``gmail.send`` grants exactly one
capability - it cannot read the mailbox it sends from. With nothing configured,
``ConsoleEmailBackend`` records that a message would have been sent, which is
what keeps ``make dev`` working with no keys at all (section 41).

Every failure reaches the caller as :class:`EmailSendError`. The Gmail backend
rides out a blip itself before giving up, and says in the error whether the
cause looks transient or permanent, so a dead credential is not mistaken for a
network wobble.
"""

from __future__ import annotations

import asyncio
import base64
import pickle
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import make_msgid
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.parse import urlencode

import anyio.to_thread
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger("serpflow.email")

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"

VERIFY_EMAIL = "verify_email"
PASSWORD_RESET = "password_reset"
NOTIFICATION = "notification"

#: Linked from the footer of every notification email.
PREFERENCES_PATH = "/app/settings"


class EmailSendError(Exception):
    """Delivery failed. The caller decides whether that is fatal."""


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    template: str
    subject: str
    html: str
    text: str


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    html: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=True),
        # StrictUndefined: a template referencing a variable nobody passed is a
        # bug, and it should fail in a test rather than render a blank gap in
        # somebody's inbox.
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def frontend_url(
    path: str, query: dict[str, str] | None = None, settings: Settings | None = None
) -> str:
    base = (settings or get_settings()).frontend_url.rstrip("/")
    url = base + "/" + path.lstrip("/")
    return url + "?" + urlencode(query) if query else url


def _duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        days = seconds // 86400
        return str(days) + (" days" if days != 1 else " day")
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return str(hours) + (" hours" if hours != 1 else " hour")
    minutes = max(1, seconds // 60)
    return str(minutes) + (" minutes" if minutes != 1 else " minute")


def render(
    template: str, subject: str, context: dict[str, Any], settings: Settings | None = None
) -> RenderedEmail:
    settings = settings or get_settings()
    env = get_template_env()
    full_context: dict[str, Any] = {
        "subject": subject,
        "app_name": "SerpFlow",
        "year": datetime.now(UTC).year,
        "recipient_name": None,
        "action_url": None,
        "action_label": "Open SerpFlow",
        "preferences_url": None,
        "details": [],
        **context,
    }
    return RenderedEmail(
        template=template,
        subject=subject,
        html=env.get_template(template + ".html").render(full_context),
        text=env.get_template(template + ".txt").render(full_context),
    )


def render_verify_email(
    recipient_name: str, raw_token: str, settings: Settings | None = None
) -> RenderedEmail:
    settings = settings or get_settings()
    return render(
        VERIFY_EMAIL,
        "Confirm your email for SerpFlow",
        {
            "recipient_name": recipient_name,
            "action_url": frontend_url("/verify-email", {"token": raw_token}, settings),
            "action_label": "Confirm email address",
            "expires_in": _duration(settings.email_verification_ttl_seconds),
        },
        settings,
    )


def render_password_reset(
    recipient_name: str, raw_token: str, settings: Settings | None = None
) -> RenderedEmail:
    settings = settings or get_settings()
    return render(
        PASSWORD_RESET,
        "Reset your SerpFlow password",
        {
            "recipient_name": recipient_name,
            "action_url": frontend_url("/reset-password", {"token": raw_token}, settings),
            "action_label": "Choose a new password",
            "expires_in": _duration(settings.password_reset_ttl_seconds),
        },
        settings,
    )


#: What the subject line calls each alert kind, and where the button goes.
_ALERT_LABELS: dict[str, tuple[str, str, str]] = {
    "budget.threshold": ("Budget", "View budgets", "/app/budgets"),
    "budget.exhausted": ("Budget", "View budgets", "/app/budgets"),
    "quota.low": ("Upstream quota", "View budgets", "/app/budgets"),
    "quota.divergence": ("Upstream quota", "View budgets", "/app/budgets"),
    "cache.false_hit": ("Cache", "Open the run", "/app/cache"),
    "credential.invalid": ("Credential", "View credentials", "/app/settings/credentials"),
    "run.failed": ("Run", "Open the run", "/app/runs"),
}


def render_alert(
    *,
    recipient_name: str,
    kind: str,
    title: str,
    message: str,
    details: list[tuple[str, str]] | None = None,
    link: str | None = None,
    settings: Settings | None = None,
) -> RenderedEmail:
    settings = settings or get_settings()
    category, action_label, default_path = _ALERT_LABELS.get(
        kind, ("Alert", "Open SerpFlow", "/app")
    )
    return render(
        NOTIFICATION,
        title + " | SerpFlow",
        {
            "recipient_name": recipient_name,
            "title": title,
            "message": message,
            "details": details or [],
            "category_label": category,
            "action_url": frontend_url(link or default_path, settings=settings),
            "action_label": action_label,
            "preferences_url": frontend_url(PREFERENCES_PATH, settings=settings),
        },
        settings,
    )


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------
class EmailBackend(Protocol):
    async def send(self, message: OutgoingEmail) -> None: ...


def build_mime(message: OutgoingEmail, sender: str) -> EmailMessage:
    mime = EmailMessage()
    mime["From"] = sender
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1].rstrip(">") or None)
    for key, value in message.headers.items():
        mime[key] = value
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    return mime


#: Sending is serialised. Neither the httplib2 connection inside a Gmail
#: service object nor a shared ``Credentials`` is thread-safe, and two threads
#: refreshing the same token at once is a race on it. Transactional mail is a
#: handful of messages, so serialising costs nothing measurable.
_gmail_lock = threading.Lock()

#: Attempts per message and the waits between them. Deliberately short: a send
#: is awaited inside the request or job that triggered it, and only transient
#: failures are retried at all, so a dead credential still fails on the first
#: attempt rather than after six seconds of waiting.
_GMAIL_ATTEMPTS: Final = 3
_GMAIL_WAITS: Final = (1.0, 2.0)


def _gmail_service(credentials_b64: str) -> Any:
    """Unpickle the configured credential and build an authorised Gmail client.

    The blob is the operator's own configuration and carries the same authority
    as this repository's code, so it is unpickled without validation. That is
    safe only because of where it comes from: it must never be sourced from the
    database, an upload, an API request or a shared config service. If that
    ever changes, this function has to change first.
    """
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    credentials = pickle.loads(base64.b64decode(credentials_b64))  # noqa: S301 - see above
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _gmail_transient(exc: BaseException) -> bool:
    """Whether retrying this failure could plausibly succeed.

    A revoked token or a missing scope cannot be fixed by asking again, and
    retrying only delays a failure that is already certain. 429 and 5xx are
    Google saying "not now"; every other 4xx is "not ever".
    """
    from google.auth.exceptions import RefreshError, TransportError
    from googleapiclient.errors import HttpError

    if isinstance(exc, RefreshError):
        return False
    if isinstance(exc, HttpError):
        status = exc.status_code
        return status is not None and (status == 429 or status >= 500)
    return isinstance(exc, TransportError | OSError | TimeoutError)


def _gmail_reason(exc: BaseException) -> str:
    """A one-line cause, carrying Google's own wording where there is one."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(exc, RefreshError):
        if "invalid_grant" in str(exc):
            # The one Gmail failure whose own message says nothing useful.
            # Google has rejected the refresh token itself, so it is dead
            # rather than misconfigured and has to be replaced. The first cause
            # is by far the most common and is invisible from the error.
            return (
                "Google rejected the refresh token (invalid_grant). Mint a new one with "
                "scripts/mint_gmail_token.py. Causes, in order of likelihood: the OAuth "
                "consent screen is still in Testing (Google expires those tokens after 7 "
                "days - publish the app), access was revoked, the account password "
                "changed, or the OAuth client was deleted."
            )
        return "RefreshError: " + str(exc)
    if isinstance(exc, HttpError):
        return "HTTP " + str(exc.status_code) + ": " + str(exc)
    return type(exc).__name__ + ": " + str(exc)


class GmailEmailBackend:
    """Delivery through the Gmail API.

    ``google-api-python-client`` owns the send and ``google-auth`` owns the
    token lifecycle, so neither is reimplemented here. Both are synchronous
    (httplib2 underneath), so the send leaves the event loop or it stalls every
    other task for the length of a round trip.
    """

    name = "gmail"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _send_sync(self, mime: EmailMessage) -> None:
        # `raw` is a complete RFC 5322 message serialised with the SMTP policy:
        # CRLF endings and folded headers, the same bytes any mail transport
        # would put on the wire.
        raw = base64.urlsafe_b64encode(mime.as_bytes(policy=SMTP_POLICY)).decode("ascii")
        with _gmail_lock:
            service = _gmail_service(self.settings.gmail_credentials_b64)
            service.users().messages().send(userId="me", body={"raw": raw}).execute()

    async def send(self, message: OutgoingEmail) -> None:
        if not self.settings.gmail_credentials_b64:
            raise EmailSendError(
                "GMAIL_CREDENTIALS_B64 is not set, so the Gmail transport cannot send."
            )
        mime = build_mime(message, self.settings.email_sender)
        for attempt in range(1, _GMAIL_ATTEMPTS + 1):
            try:
                # anyio rather than asyncio.to_thread: that is the pool FastAPI
                # already sizes.
                await anyio.to_thread.run_sync(self._send_sync, mime)
                log.info(
                    "email sent",
                    extra={
                        "event": "email.sent",
                        "backend": "gmail",
                        "to": message.to,
                        "subject": message.subject,
                    },
                )
                return
            except Exception as exc:
                transient = _gmail_transient(exc)
                if not transient or attempt == _GMAIL_ATTEMPTS:
                    raise EmailSendError(
                        "Gmail delivery failed ("
                        + ("transient" if transient else "permanent")
                        + "): "
                        + _gmail_reason(exc)
                    ) from exc
                log.warning(
                    "email send retry",
                    extra={
                        "event": "email.retry",
                        "backend": "gmail",
                        "to": message.to,
                        "attempt": attempt,
                        "error": _gmail_reason(exc),
                    },
                )
                await asyncio.sleep(_GMAIL_WAITS[attempt - 1])


class ConsoleEmailBackend:
    """The no-configuration backend.

    Records that an email would have been sent. Bodies hold single-use tokens,
    so they are never written to the log - the link is available from the API
    response in development instead.
    """

    name = "console"

    async def send(self, message: OutgoingEmail) -> None:
        log.info(
            "email sent",
            extra={
                "event": "email.sent",
                "backend": "console",
                "to": message.to,
                "subject": message.subject,
            },
        )


_backend: EmailBackend | None = None


def get_email_backend() -> EmailBackend:
    """Gmail once a credential is configured, the console otherwise.

    There is no third setting to get wrong: configuring the credential *is* the
    instruction to send for real.
    """
    global _backend
    if _backend is None:
        settings = get_settings()
        _backend = (
            GmailEmailBackend(settings) if settings.email_configured else ConsoleEmailBackend()
        )
    return _backend


def set_email_backend(backend: EmailBackend | None) -> None:
    """Used by tests to capture outgoing mail."""
    global _backend
    _backend = backend


async def send(message: OutgoingEmail) -> None:
    await get_email_backend().send(message)


async def send_rendered(to: str, rendered: RenderedEmail) -> None:
    await send(
        OutgoingEmail(to=to, subject=rendered.subject, html=rendered.html, text=rendered.text)
    )


__all__ = [
    "ConsoleEmailBackend",
    "EmailBackend",
    "EmailSendError",
    "GmailEmailBackend",
    "OutgoingEmail",
    "RenderedEmail",
    "build_mime",
    "frontend_url",
    "get_email_backend",
    "render",
    "render_alert",
    "render_password_reset",
    "render_verify_email",
    "send",
    "send_rendered",
    "set_email_backend",
]
