"""Transactional email: rendering and delivery.

See :mod:`app.services.email.service`. Nothing else in the application imports
a mail library directly.
"""

from app.services.email.service import (
    ConsoleEmailBackend,
    EmailBackend,
    EmailSendError,
    GmailEmailBackend,
    OutgoingEmail,
    RenderedEmail,
    frontend_url,
    get_email_backend,
    render,
    render_alert,
    render_password_reset,
    render_verify_email,
    send,
    send_rendered,
    set_email_backend,
)

__all__ = [
    "ConsoleEmailBackend",
    "EmailBackend",
    "EmailSendError",
    "GmailEmailBackend",
    "OutgoingEmail",
    "RenderedEmail",
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
