"""
Analyze layer: score job fit, rewrite resume bullets, draft cover letter.
Uses Ollama (local, no API key required) with llama3.2 by default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import ollama

RESUME_PATH = Path(__file__).parents[2] / "config" / "resume.md"
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _load_resume() -> str:
    return RESUME_PATH.read_text()


def analyze_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Sends job description + resume to the local Ollama model.
    Returns:
      {
        "score": int (0-100),
        "rationale": str,
        "gaps": str,
        "tailored_bullets": list[str],
        "cover_letter": str,
      }
    """
    resume = _load_resume()

    prompt = f"""You are a career coach and expert resume writer.
You receive a job description and a candidate's resume.
You respond ONLY with a valid JSON object — no markdown fences, no commentary, no extra text.

Job title: {job['title']}
Company: {job['company']}
Location: {job['location']}

--- JOB DESCRIPTION ---
{job['description'][:4000]}

--- CANDIDATE RESUME ---
{resume}

Return a JSON object with exactly these keys:
- score: integer 0-100 (fit score)
- rationale: 1-2 sentence explanation of the score
- gaps: key skills or experience missing from the resume
- tailored_bullets: list of 4-6 resume bullet points rewritten to mirror the JD language
- cover_letter: a concise 3-paragraph cover letter (no placeholders)
"""

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3},
        )
        raw = response["message"]["content"].strip()

        # Strip accidental markdown fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "score": 0,
            "rationale": "LLM response could not be parsed.",
            "gaps": "",
            "tailored_bullets": [],
            "cover_letter": "",
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "score": 0,
            "rationale": f"LLM call failed: {exc}",
            "gaps": "",
            "tailored_bullets": [],
            "cover_letter": "",
        }

    return result
