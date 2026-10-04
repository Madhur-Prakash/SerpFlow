"""Channel labels, and what each one changes about the email.

A notification channel's label is not decoration. The same alert means
different things to different readers: an exhausted budget is an incident to
whoever is on call, a number to whoever owns the spend, and neither of those
to a director who wants to know it happened. Sending one body to all three
means writing for none of them.

So the label selects a *presentation*: how urgent the subject reads, whether
the technical identifiers are included at all, and how the mail opens and
closes. The facts are identical in every variant - only the framing differs,
and nothing is ever added that the event did not carry.

**No model generates any of this.** Every variant is a fixed template filled
with values from the event. The same alert to the same label produces a
byte-identical email every time, which is what makes it reviewable, testable
and safe to send without a human reading it first. A generated body would be
none of those, and would also be a way for event data to become instructions.

An unrecognised label - anyone may type their own - resolves to GENERIC, which
states the facts plainly and includes the details. It is a deliberate
fallback, not a degraded one: a custom label carries no information about its
reader, so the honest thing is to assume nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Audience:
    """One reader of an alert, and how the mail should read for them."""

    slug: str
    label: str
    #: Shown next to the label in the console, so the choice is informed.
    description: str
    #: Prefixes the subject. Empty for readers who do not want shouting.
    subject_prefix: str
    #: Opens the body. Sets the register before the alert's own title.
    lede: str
    #: Whether to include the identifier table (project, engine, limits).
    #: False for readers to whom an engine name means nothing.
    include_details: bool
    #: Closes the body. Usually says what to do next.
    closing: str


ON_CALL = Audience(
    slug="on-call",
    label="On-call",
    description="Operational alerts. Urgent framing, full detail.",
    subject_prefix="[ALERT] ",
    lede="This needs attention now.",
    include_details=True,
    closing="Open the console to see the current state before acting.",
)

ENGINEERING = Audience(
    slug="engineering",
    label="Engineering",
    description="Technical detail, no urgency framing.",
    subject_prefix="",
    lede="SerpFlow recorded the following.",
    include_details=True,
    closing="The run and its plan are kept, so this is reproducible.",
)

BILLING = Audience(
    slug="billing",
    label="Billing",
    description="Spend and quota, in money terms.",
    subject_prefix="",
    lede="This affects what the organization is spending.",
    include_details=True,
    closing=(
        "SerpFlow's ledger and the upstream account are two different numbers. "
        "Check both before reconciling."
    ),
)

SECURITY = Audience(
    slug="security",
    label="Security",
    description="Credentials, access and audit. Says what to verify.",
    subject_prefix="[SECURITY] ",
    lede="This concerns credentials or access.",
    include_details=True,
    closing=(
        "The audit log is hash-chained, so the sequence around this event can be "
        "verified rather than taken on trust."
    ),
)

LEADERSHIP = Audience(
    slug="leadership",
    label="Leadership",
    description="Plain summary. No identifiers or engine names.",
    subject_prefix="",
    lede="A short summary of something that happened in SerpFlow.",
    # Deliberately off: a reader who does not operate the system cannot act on
    # an engine name, and including it only makes the mail look urgent.
    include_details=False,
    closing="No action is expected from this message.",
)

GENERIC = Audience(
    slug="generic",
    label="Custom",
    description="Anything else. States the facts, includes the detail.",
    subject_prefix="",
    lede="SerpFlow raised an alert on your organization.",
    include_details=True,
    closing="Open the console for the full context.",
)

#: The ones offered in the console. GENERIC is not among them - it is what a
#: label that is not on this list resolves to, not something to pick.
PRESETS: tuple[Audience, ...] = (ON_CALL, ENGINEERING, BILLING, SECURITY, LEADERSHIP)

_BY_SLUG = {a.slug: a for a in PRESETS}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def resolve(label: str | None) -> Audience:
    """The audience a channel's label names, or GENERIC.

    Matching is on the slug, so "On-call", "on call" and "ON-CALL" are the same
    preset while "Growth team" is not any of them and gets GENERIC. Nothing is
    guessed from a substring: a label of "on-call vendors" is somebody else's
    list, not the on-call rota, and treating it as the latter would mark their
    mail urgent on the strength of a prefix.
    """
    if not label:
        return GENERIC
    return _BY_SLUG.get(_slugify(label), GENERIC)


__all__ = [
    "BILLING",
    "ENGINEERING",
    "GENERIC",
    "LEADERSHIP",
    "ON_CALL",
    "PRESETS",
    "SECURITY",
    "Audience",
    "resolve",
]
