"""Unit tests for agent.notify.reply_checker — pure parsing functions."""

from __future__ import annotations

import email

import pytest

from agent.notify.reply_checker import _extract_approved_nums, _extract_digest_id, _get_text_body

# ── _extract_approved_nums ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("APPLY: 1, 3, 5", [1, 3, 5]),
        ("apply: 2", [2]),
        ("APPLY:1,3", [1, 3]),
        ("APPLY: 1 3 5", [1, 3, 5]),  # space-separated
        ("Hi!\nAPPLY: 4, 7\nThanks", [4, 7]),
        ("No approval here", []),
        ("", []),
    ],
)
def test_extract_approved_nums(text, expected):
    assert _extract_approved_nums(text) == expected


# ── _extract_digest_id ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("Re: Job Agent Digest #3 — 2026-04-12 (5 matches)", 3),
        ("Job Agent Digest #12 — 2026-04-12 (2 matches)", 12),
        ("Re: Job Agent Digest #1 — 2026-04-12 (0 matches)", 1),
        ("Unrelated subject", None),
        ("", None),
    ],
)
def test_extract_digest_id(subject, expected):
    assert _extract_digest_id(subject) == expected


# ── _get_text_body ────────────────────────────────────────────────────────────


def _make_plain_message(body: str) -> email.message.Message:
    msg = email.message.Message()
    msg["Content-Type"] = "text/plain"
    msg.set_payload(body.encode(), decode=False)
    # Simulate raw bytes payload
    msg._payload = body.encode()  # noqa: SLF001
    return msg


def test_get_text_body_simple():
    msg = email.message_from_bytes(b"Content-Type: text/plain\r\n\r\nAPPLY: 1, 2")
    body = _get_text_body(msg)
    assert "APPLY: 1, 2" in body


def test_get_text_body_multipart_prefers_plain():
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    outer = MIMEMultipart("alternative")
    outer.attach(MIMEText("APPLY: 3", "plain"))
    outer.attach(MIMEText("<b>APPLY: 3</b>", "html"))

    body = _get_text_body(outer)
    assert "APPLY: 3" in body
    assert "<b>" not in body


def test_get_text_body_empty_message():
    msg = email.message_from_bytes(b"Content-Type: text/plain\r\n\r\n")
    body = _get_text_body(msg)
    assert body == ""
