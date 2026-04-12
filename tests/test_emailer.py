"""Unit tests for agent.notify.emailer — pure helper functions."""

from __future__ import annotations

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
