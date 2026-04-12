"""
Analyze layer: score job fit, rewrite resume bullets, draft cover letter.

LLM backend (auto-selected):
  - If ANTHROPIC_API_KEY is set → uses Claude API (ideal for GitHub Actions)
  - Otherwise → uses local Ollama (ideal for local runs, no API cost)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RESUME_PATH = Path(__file__).parents[2] / "config" / "resume.md"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap for bulk scoring


def _load_resume() -> str:
    return RESUME_PATH.read_text()


def _call_llm(prompt: str) -> str:
    """
    Route to the best available LLM backend:
      1. Groq  (GROQ_API_KEY set)      — free, open-source Llama 3.1, cloud-safe
      2. Claude (ANTHROPIC_API_KEY set) — paid, most accurate
      3. Ollama (fallback)              — local only, no API key needed
    """
    if GROQ_API_KEY:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        return response.choices[0].message.content.strip()

    if ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    import ollama
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.3},
    )
    return response["message"]["content"].strip()


def analyze_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Sends job description + resume to the configured LLM.
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
- score: integer 0-100 (fit score based on skills, experience level, and role match)
- rationale: 1-2 sentence explanation of the score
- gaps: key skills or experience missing from the resume
- tailored_bullets: list of 4-6 resume bullet points rewritten to mirror the JD's exact language and keywords
- cover_letter: a concise 3-paragraph cover letter using the JD's keywords (no placeholders)
"""

    try:
        raw = _call_llm(prompt)

        # Strip accidental markdown fences
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
