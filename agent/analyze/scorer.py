"""
Analyze layer: score job fit, rewrite resume bullets, draft cover letter.
Uses Claude with prompt caching for the static resume content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic

RESUME_PATH = Path(__file__).parents[2] / "config" / "resume.md"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _load_resume() -> str:
    return RESUME_PATH.read_text()


def analyze_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Sends job description + resume to Claude.
    Returns:
      {
        "score": int (0-100),
        "rationale": str,
        "gaps": str,
        "tailored_bullets": list[str],
        "cover_letter": str,
      }
    """
    client = _get_client()
    resume = _load_resume()

    system_prompt = (
        "You are a career coach and expert resume writer. "
        "You receive a job description and a candidate's resume. "
        "You respond ONLY with a JSON object — no markdown fences, no commentary."
    )

    user_prompt = f"""Job title: {job['title']}
Company: {job['company']}
Location: {job['location']}

--- JOB DESCRIPTION ---
{job['description'][:6000]}

--- CANDIDATE RESUME ---
{resume}

Return a JSON object with these exact keys:
- score: integer 0-100 (fit score)
- rationale: 1-2 sentence explanation of the score
- gaps: key skills or experience missing
- tailored_bullets: list of 4-6 resume bullet points rewritten to mirror the JD's language
- cover_letter: a concise, 3-paragraph cover letter (no placeholders)
"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                # Cache the static system prompt across calls
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Graceful fallback: return a zero score so the job is flagged, not silently dropped
        result = {
            "score": 0,
            "rationale": "LLM response could not be parsed.",
            "gaps": "",
            "tailored_bullets": [],
            "cover_letter": "",
        }

    return result
