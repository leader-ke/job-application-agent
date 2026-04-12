"""
Scraper for Kenya Government job adverts at gaa.go.ke/index.php/job-adverts.
(mygov.go.ke now redirects to gaa.go.ke — Government Advertising Agency)

Job listings appear as PDF links. We extract the title + PDF URL and treat
the title as the description. These jobs always land as "review" in the
pipeline (they won't match Greenhouse/Lever auto-apply) so they appear in
your email digest for manual action.
"""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://gaa.go.ke"
JOBS_URL = f"{BASE_URL}/index.php/job-adverts"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# Roles/keywords to include
TARGET_KEYWORDS = [
    "ict",
    "information and communication",
    "information technology",
    "software",
    "qa",
    "quality",
    "automation",
    "product manager",
    "product management",
    "data",
    "engineer",
    "developer",
    "analyst",
    "digital",
    "systems",
    "network",
    "cybersecurity",
    "database",
    "programme",
    "program",
]


def _job_id(url: str) -> str:
    return "mygov_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _is_relevant(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in TARGET_KEYWORDS)


def fetch_mygov_jobs() -> list[dict[str, Any]]:
    """
    Scrape gaa.go.ke/index.php/job-adverts for relevant PDF job listings.
    Returns job dicts compatible with the main pipeline.
    """
    jobs: list[dict[str, Any]] = []

    try:
        resp = httpx.get(JOBS_URL, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[mygov] Fetch failed: {exc}")
        return jobs

    soup = BeautifulSoup(resp.text, "html.parser")

    # All job listings appear as links to PDFs
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Only PDF links or job-related links
        if ".pdf" not in href.lower() and "job" not in href.lower():
            continue

        if not _is_relevant(title):
            continue

        full_url = urljoin(BASE_URL, href) if not href.startswith("http") else href
        job_id = _job_id(full_url)

        # Build a description from the title (PDF content not fetched for speed)
        description = (
            f"{title}\n\n"
            f"Source: Kenya Government (gaa.go.ke)\n"
            f"Full advert PDF: {full_url}\n\n"
            "Note: This is a government job advert. Review the PDF for full details "
            "and application instructions. Apply manually via the PDF or contact listed."
        )

        jobs.append(
            {
                "id": job_id,
                "title": title,
                "company": "Kenya Government",
                "location": "Kenya",
                "description": description,
                "job_url": full_url,
                "site": "mygov",
            }
        )

    return jobs
