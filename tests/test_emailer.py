"""Unit tests for agent.notify.emailer — pure helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.notify.emailer import (
    _apply_badge,
    _apply_method,
    _score_color,
    _score_label,
    build_subject,
)

# ── _score_color ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score, color",
    [
        (100, "#16a34a"),  # green
        (75, "#16a34a"),  # green boundary
        (74, "#d97706"),  # amber
        (55, "#d97706"),  # amber boundary
        (54, "#dc2626"),  # red
        (0, "#dc2626"),  # red
    ],
)
def test_score_color(score, color):
    assert _score_color(score) == color


# ── _score_label ─────────────────────────────────────────────────────────────


def test_score_label_auto_apply():
    label = _score_label(82, "apply")
    assert "82" in label
    assert "auto" in label


def test_score_label_review():
    assert _score_label(68, "review") == "68"


def test_score_label_unknown_decision():
    assert _score_label(60, "pending") == "60"


# ── _apply_method ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://jobs.greenhouse.io/acme/roles/12345", "Auto"),
        ("https://jobs.lever.co/acme/role-slug", "Auto"),
        ("https://gaa.go.ke/uploads/job-advert.pdf", "PDF"),
        ("https://bamboohr.com/careers/senior-qa", "Manual"),
        ("https://workday.com/apply", "Manual"),
        ("", "Manual"),
    ],
)
def test_apply_method(url, expected):
    assert _apply_method(url) == expected


# ── _apply_badge ─────────────────────────────────────────────────────────────


def test_apply_badge_auto_contains_auto():
    badge = _apply_badge("https://jobs.greenhouse.io/role")
    assert "Auto" in badge
    assert "dcfce7" in badge  # green background


def test_apply_badge_manual_contains_manual():
    badge = _apply_badge("https://example.com/apply")
    assert "Manual" in badge
    assert "fee2e2" in badge  # red background


def test_apply_badge_pdf_contains_pdf():
    badge = _apply_badge("https://gaa.go.ke/job.pdf")
    assert "PDF" in badge
    assert "fef9c3" in badge  # yellow background


# ── build_subject ─────────────────────────────────────────────────────────────


def test_build_subject_contains_digest_id():
    assert "Digest #7" in build_subject(7, 5)


def test_build_subject_contains_match_count():
    assert "12 matches" in build_subject(1, 12)


def test_build_subject_contains_date():
    from datetime import date

    assert date.today().isoformat() in build_subject(1, 0)


# ── send_no_results ───────────────────────────────────────────────────────────


def _make_smtp_mock():
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    return smtp


def _decode_mime_body(raw: str) -> str:
    """Parse a MIME message string and return the decoded HTML body."""
    import email as email_lib

    msg = email_lib.message_from_string(raw)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode()
    return raw


def test_send_no_results_zero_listings(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-password")
    monkeypatch.setenv("GMAIL_ADDRESS", "test@gmail.com")

    smtp_mock = _make_smtp_mock()
    captured: list[str] = []
    smtp_mock.sendmail = lambda *a: captured.append(a[2])

    with patch("agent.notify.emailer.smtplib.SMTP", return_value=smtp_mock):
        import importlib

        import agent.notify.emailer as em

        importlib.reload(em)
        em.send_no_results(new_listings=0, analyzed=0, review_threshold=65)

    assert len(captured) == 1
    body = _decode_mime_body(captured[0])
    assert "No new listings" in body


def test_send_no_results_below_threshold(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake-password")
    monkeypatch.setenv("GMAIL_ADDRESS", "test@gmail.com")

    smtp_mock = _make_smtp_mock()
    captured: list[str] = []
    smtp_mock.sendmail = lambda *a: captured.append(a[2])

    with patch("agent.notify.emailer.smtplib.SMTP", return_value=smtp_mock):
        import importlib

        import agent.notify.emailer as em

        importlib.reload(em)
        em.send_no_results(new_listings=5, analyzed=5, review_threshold=65)

    assert len(captured) == 1
    body = _decode_mime_body(captured[0])
    assert "5" in body
    assert "65" in body


def test_send_no_results_no_password_is_noop(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "")
    with patch("agent.notify.emailer.smtplib.SMTP") as smtp_cls:
        import importlib

        import agent.notify.emailer as em

        importlib.reload(em)
        em.send_no_results(new_listings=0, analyzed=0, review_threshold=65)
    smtp_cls.assert_not_called()
