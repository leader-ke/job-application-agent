"""Unit tests for agent.analyze.scorer — mock LLM, test parsing + error handling."""

from __future__ import annotations

import json
from unittest.mock import patch

from agent.analyze.scorer import analyze_job

_JOB = {
    "title": "Senior QA Engineer",
    "company": "EIDU",
    "location": "Nairobi, Kenya",
    "description": "We need an experienced QA engineer with Python and Playwright skills.",
}

_VALID_RESPONSE = json.dumps(
    {
        "score": 85,
        "rationale": "Strong match on QA and automation skills.",
        "gaps": "No formal SDET certification.",
        "tailored_bullets": ["Led test automation suites", "Built CI/CD pipelines"],
        "cover_letter": "Dear Hiring Manager, I am a great fit...",
    }
)


def _patched(llm_return: str):
    """Context manager that mocks both _call_llm and _load_resume."""
    return (
        patch("agent.analyze.scorer._call_llm", return_value=llm_return),
        patch("agent.analyze.scorer._load_resume", return_value="Candidate resume text."),
    )


# ── happy path ────────────────────────────────────────────────────────────────


def test_analyze_job_valid_json():
    with (
        patch("agent.analyze.scorer._call_llm", return_value=_VALID_RESPONSE),
        patch("agent.analyze.scorer._load_resume", return_value="resume"),
    ):
        result = analyze_job(_JOB)
    assert result["score"] == 85
    assert result["rationale"] == "Strong match on QA and automation skills."
    assert len(result["tailored_bullets"]) == 2
    assert result["cover_letter"].startswith("Dear")


# ── markdown fence stripping ──────────────────────────────────────────────────


def test_analyze_job_strips_markdown_fences():
    fenced = f"```json\n{_VALID_RESPONSE}\n```"
    with (
        patch("agent.analyze.scorer._call_llm", return_value=fenced),
        patch("agent.analyze.scorer._load_resume", return_value="resume"),
    ):
        result = analyze_job(_JOB)
    assert result["score"] == 85


def test_analyze_job_strips_plain_code_fence():
    fenced = f"```\n{_VALID_RESPONSE}\n```"
    with (
        patch("agent.analyze.scorer._call_llm", return_value=fenced),
        patch("agent.analyze.scorer._load_resume", return_value="resume"),
    ):
        result = analyze_job(_JOB)
    assert result["score"] == 85


# ── error handling ────────────────────────────────────────────────────────────


def test_analyze_job_bad_json_returns_zero():
    with (
        patch("agent.analyze.scorer._call_llm", return_value="not valid json"),
        patch("agent.analyze.scorer._load_resume", return_value="resume"),
    ):
        result = analyze_job(_JOB)
    assert result["score"] == 0
    assert "could not be parsed" in result["rationale"]
    assert result["tailored_bullets"] == []
    assert result["cover_letter"] == ""


def test_analyze_job_llm_exception_returns_zero():
    with (
        patch("agent.analyze.scorer._call_llm", side_effect=RuntimeError("API down")),
        patch("agent.analyze.scorer._load_resume", return_value="resume"),
    ):
        result = analyze_job(_JOB)
    assert result["score"] == 0
    assert "LLM call failed" in result["rationale"]
    assert "API down" in result["rationale"]
