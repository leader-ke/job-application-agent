"""
Apply layer: browser automation for ATS portals via Playwright.
Supports Greenhouse and Lever. Flags unsupported portals for human review.
"""

from __future__ import annotations

import os
from typing import Any

from playwright.sync_api import sync_playwright

APPLICANT_NAME = os.getenv("APPLICANT_NAME", "Kennedy Isiaho")
APPLICANT_FIRST = APPLICANT_NAME.split()[0]
APPLICANT_LAST = " ".join(APPLICANT_NAME.split()[1:])
APPLICANT_EMAIL = os.getenv("GMAIL_ADDRESS", "kenisiaho@gmail.com")
APPLICANT_PHONE = os.getenv("APPLICANT_PHONE", "+254712869569")


SUPPORTED_PORTALS = {
    "greenhouse.io": "_apply_greenhouse",
    "lever.co": "_apply_lever",
}


def detect_portal(url: str) -> str | None:
    for domain in SUPPORTED_PORTALS:
        if domain in url:
            return domain
    return None


def apply(job: dict[str, Any], analysis: dict[str, Any]) -> dict[str, str]:
    """
    Attempt automated application.
    Returns {"status": "applied" | "flagged", "reason": str}
    """
    url = job.get("job_url", "")
    portal = detect_portal(url)

    if portal is None:
        return {
            "status": "flagged",
            "reason": f"Unsupported portal — open manually: {url}",
        }

    handler_name = SUPPORTED_PORTALS[portal]
    handler = globals()[handler_name]

    try:
        handler(url, job, analysis)
        return {"status": "applied", "reason": f"Applied via {portal}"}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "flagged",
            "reason": f"Automation failed ({portal}): {exc} — open manually: {url}",
        }


# ---------------------------------------------------------------------------
# Portal handlers
# ---------------------------------------------------------------------------

def _apply_greenhouse(url: str, job: dict[str, Any], analysis: dict[str, Any]) -> None:
    cover_letter = analysis.get("cover_letter", "")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, timeout=30_000)

        # Greenhouse standard apply form fields
        page.fill("#first_name", APPLICANT_FIRST)
        page.fill("#last_name", APPLICANT_LAST)
        page.fill("#email", APPLICANT_EMAIL)
        page.fill("#phone", APPLICANT_PHONE)

        # Cover letter textarea (if present)
        cl_field = page.query_selector("textarea[name='cover_letter']")
        if cl_field:
            cl_field.fill(cover_letter)

        # Resume upload — expects a pre-generated PDF in data/
        resume_pdf = str(
            __import__("pathlib").Path(__file__).parents[2] / "data" / "resume.pdf"
        )
        file_input = page.query_selector("input[type='file']")
        if file_input:
            file_input.set_input_files(resume_pdf)

        page.click("input[type='submit'], button[type='submit']")
        page.wait_for_timeout(3000)
        browser.close()


def _apply_lever(url: str, job: dict[str, Any], analysis: dict[str, Any]) -> None:
    cover_letter = analysis.get("cover_letter", "")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, timeout=30_000)

        page.fill("input[name='name']", APPLICANT_NAME)
        page.fill("input[name='email']", APPLICANT_EMAIL)
        page.fill("input[name='phone']", APPLICANT_PHONE)

        cl_field = page.query_selector("textarea[name='comments']")
        if cl_field:
            cl_field.fill(cover_letter)

        resume_pdf = str(
            __import__("pathlib").Path(__file__).parents[2] / "data" / "resume.pdf"
        )
        file_input = page.query_selector("input[type='file']")
        if file_input:
            file_input.set_input_files(resume_pdf)

        page.click("button[type='submit']")
        page.wait_for_timeout(3000)
        browser.close()
