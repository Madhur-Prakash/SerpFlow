"""Channel labels and the email variants they select.

The property worth protecting is determinism: a label plus an event always
produces the same bytes. That is what makes these emails reviewable and what
keeps event data from becoming instructions.
"""

from __future__ import annotations

import pytest

from app.services.email import render_alert
from app.services.notifications import audiences

ALERT = {
    "recipient_name": "Ops",
    "kind": "budget.exhausted",
    "title": "Budget exhausted",
    "message": "The Review Intelligence project has spent its monthly allowance.",
    "details": [("Project id", "prj_01ABC"), ("Limit credits", "500")],
}


# ------------------------------------------------------------- resolution
@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("On-call", audiences.ON_CALL),
        ("on call", audiences.ON_CALL),
        ("ON-CALL", audiences.ON_CALL),
        ("Billing", audiences.BILLING),
        ("Leadership", audiences.LEADERSHIP),
    ],
)
def test_presets_resolve_regardless_of_casing_or_spacing(label, expected):
    assert audiences.resolve(label) is expected


@pytest.mark.parametrize("label", ["Growth squad", "", None, "on-call vendors", "oncall"])
def test_anything_else_is_generic(label):
    """Including near-misses.

    `on-call vendors` is somebody's supplier list, not the rota. Matching it on
    a prefix would mark their mail urgent on the strength of two words.
    """
    assert audiences.resolve(label) is audiences.GENERIC


def test_generic_is_not_offered_as_a_preset():
    """It is where unrecognised labels land, not something to choose."""
    assert audiences.GENERIC not in audiences.PRESETS


# ---------------------------------------------------------------- framing
def test_on_call_marks_the_subject_urgent():
    rendered = render_alert(**ALERT, channel_label="On-call")
    assert rendered.subject.startswith("[ALERT] ")


def test_most_labels_do_not_shout():
    for label in ("Billing", "Engineering", "Leadership", "Growth squad"):
        assert not render_alert(**ALERT, channel_label=label).subject.startswith("[")


def test_leadership_is_told_what_happened_but_not_the_identifiers():
    rendered = render_alert(**ALERT, channel_label="Leadership")
    assert "spent its monthly allowance" in rendered.text
    assert "prj_01ABC" not in rendered.text
    assert "prj_01ABC" not in rendered.html


def test_every_other_audience_keeps_the_identifiers():
    for label in ("On-call", "Engineering", "Billing", "Security", "Growth squad"):
        assert "prj_01ABC" in render_alert(**ALERT, channel_label=label).text, label


def test_the_facts_survive_every_variant():
    """Framing changes; the alert's own words do not."""
    for label in ("On-call", "Billing", "Leadership", "Security", None, "Anything"):
        assert ALERT["message"] in render_alert(**ALERT, channel_label=label).text


def test_each_preset_reads_differently():
    openings = {
        a.label: render_alert(**ALERT, channel_label=a.label).text for a in audiences.PRESETS
    }
    assert len(set(openings.values())) == len(audiences.PRESETS)


# ---------------------------------------------------------- determinism
def test_the_same_alert_renders_identically_every_time():
    """No model is involved, so this must hold byte for byte."""
    for label in ("On-call", "Leadership", "Made up label"):
        first = render_alert(**ALERT, channel_label=label)
        second = render_alert(**ALERT, channel_label=label)
        assert first.subject == second.subject
        assert first.text == second.text
        assert first.html == second.html


def test_an_unknown_label_is_never_an_error():
    """Anyone may type anything; it must render, not raise."""
    rendered = render_alert(**ALERT, channel_label="'; DROP TABLE channels; --")
    assert ALERT["title"] in rendered.text


def test_a_label_cannot_inject_markup_into_the_html():
    """The label reaches the template, so autoescaping has to hold."""
    rendered = render_alert(**ALERT, channel_label="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in rendered.html
