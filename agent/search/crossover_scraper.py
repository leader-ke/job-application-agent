"""
Scraper for Crossover (crossover.com/jobs) — remote, high-paying roles.

Uses Playwright because the site is an Angular SPA.
Crossover robots.txt permits crawling of job listing pages.
"""

from __future__ import annotations

import hashlib
from typing import Any

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.crossover.com"
JOBS_URL = f"{BASE_URL}/jobs"

# Search terms mapped to the role categories we care about
SEARCH_TERMS = [
    "QA Engineer",
    "Quality Assurance",
    "Test Engineer",
    "Automation Engineer",
    "Product Manager",
]

# Title must contain at least one of these to be forwarded to the LLM
TITLE_KEYWORDS = [
    "qa",
    "quality assurance",
    "quality engineer",
    "test engineer",
    "sdet",
    "software engineer in test",
    "automation engineer",
    "product manager",
    "ict officer",
    "ict manager",
]


def _is_relevant(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in TITLE_KEYWORDS)


def _job_id(url: str) -> str:
    return "crossover_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _build_description(title: str, company: str, url: str) -> str:
    return (
        f"{title}\n\n"
        f"Company: {company}\n"
        f"Source: Crossover (crossover.com)\n"
        f"Apply: {url}\n\n"
        "Crossover specialises in full-time remote roles with structured pay. "
        "Review the listing for full responsibilities and application steps."
    )


def fetch_crossover_jobs() -> list[dict[str, Any]]:
    """
    Scrape crossover.com/jobs for relevant remote roles.
    Returns job dicts compatible with the main pipeline.
    Falls back to empty list on any error.
    """
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )
            page = context.new_page()

            for term in SEARCH_TERMS:
                try:
                    url = f"{JOBS_URL}?search={term.replace(' ', '+')}"
                    page.goto(url, timeout=30_000, wait_until="networkidle")

                    # Wait for job cards to render
                    page.wait_for_selector(
                        "[class*='job'], [class*='role'], article, li[data-job]",
                        timeout=10_000,
                        state="attached",
                    )
                except Exception:  # noqa: BLE001
                    # Selector may not exist — page may be empty or layout changed
                    pass

                # Extract all anchor tags that look like job links
                links = page.query_selector_all("a[href*='/job/'], a[href*='/jobs/']")

                for link in links:
                    href = link.get_attribute("href") or ""
                    if not href:
                        continue

                    full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                    if full_url in seen_urls:
                        continue

                    # Try to find title text: the link itself or a child heading
                    title_el = (
                        link.query_selector("h2, h3, h4, [class*='title'], [class*='name']") or link
                    )
                    title = (title_el.inner_text() or "").strip()
                    if not title or len(title) < 4:
                        continue

                    if not _is_relevant(title):
                        continue

                    # Company — Crossover jobs are typically listed under the client company
                    company_el = link.query_selector(
                        "[class*='company'], [class*='client'], [class*='employer']"
                    )
                    company = (company_el.inner_text() or "").strip() if company_el else "Crossover"

                    seen_urls.add(full_url)
                    jobs.append(
                        {
                            "id": _job_id(full_url),
                            "title": title,
                            "company": company or "Crossover",
                            "location": "Remote",
                            "is_remote": True,
                            "description": _build_description(title, company, full_url),
                            "job_url": full_url,
                            "site": "crossover",
                        }
                    )

            browser.close()

    except Exception as exc:  # noqa: BLE001
        print(f"[crossover] Scrape failed: {exc}")

    print(f"[crossover] Found {len(jobs)} jobs.")
    return jobs
