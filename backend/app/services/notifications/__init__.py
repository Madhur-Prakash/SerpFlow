"""Notification channels: who gets told, and how it reads for them."""

from app.services.notifications.audiences import (
    GENERIC,
    PRESETS,
    Audience,
    resolve,
)

__all__ = ["GENERIC", "PRESETS", "Audience", "resolve"]
