"""
Scraper for Arc.dev — remote developer & tech job board.

Arc.dev robots.txt permits crawling (10-second crawl-delay for bots).
The site is a Next.js SPA, so we first try extracting __NEXT_DATA__ JSON
embedded in the initial HTML (fast, no browser needed). If that yields
nothing, we fall back to a Playwright render.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx

BASE_URL = "https://arc.dev"

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


# Role-specific search URLs on Arc.dev
SEARCH_URLS = [
    f"{BASE_URL}/remote-jobs?keyword=QA+engineer",
    f"{BASE_URL}/remote-jobs?keyword=quality+assurance",
    f"{BASE_URL}/remote-jobs?keyword=test+automation",
    f"{BASE_URL}/remote-jobs?keyword=product+manager",
    f"{BASE_URL}/remote-jobs?keyword=software+engineer+in+test",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _job_id(url: str) -> str:
    return "arc_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _build_description(title: str, company: str, url: str) -> str:
    return (
        f"{title}\n\n"
        f"Company: {company}\n"
        f"Source: Arc.dev (arc.dev)\n"
        f"Apply: {url}\n\n"
        "Arc.dev lists vetted remote developer roles. "
        "Review the listing for full responsibilities and application instructions."
    )


def _extract_from_next_data(html: str) -> list[dict[str, Any]]:
    """Parse jobs from Next.js __NEXT_DATA__ JSON embedded in the page."""
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    # Walk the dehydrated query cache for job objects
    jobs_raw: list[dict] = []

    # Arc.dev job objects typically have "slug", "title", "company" keys
    # Try multiple known paths
    page_props = data.get("props", {}).get("pageProps", {})
    for key in ("jobs", "jobListings", "results", "data"):
        candidates = page_props.get(key)
        if isinstance(candidates, list):
            jobs_raw = candidates
            break
        if isinstance(candidates, dict):
            inner = candidates.get("jobs") or candidates.get("results") or []
            if inner:
                jobs_raw = inner
                break

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        slug = str(item.get("slug") or item.get("id") or "").strip()
        company = str(
            (item.get("company") or {}).get("name")
            if isinstance(item.get("company"), dict)
            else item.get("company") or item.get("companyName") or "Arc.dev"
        ).strip()
        if not title or not slug:
            continue
        if not _is_relevant(title):
            continue
        url = urljoin(BASE_URL, f"/remote-jobs/{slug}")
        if url in seen:
            continue
        seen.add(url)
        jobs.append(
            {
                "id": _job_id(url),
                "title": title,
                "company": company,
                "location": "Remote",
                "is_remote": True,
                "description": _build_description(title, company, url),
                "job_url": url,
                "site": "arc",
            }
        )
    return jobs


def _fetch_via_playwright(search_url: str) -> list[dict[str, Any]]:
    """Fallback: use Playwright to render the page and extract job links."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    jobs: list[dict[str, Any]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(search_url, timeout=30_000, wait_until="networkidle")

            try:
                page.wait_for_selector(
                    "a[href*='/remote-jobs/'], [class*='job'], article",
                    timeout=10_000,
                    state="attached",
                )
            except Exception:  # noqa: BLE001
                pass

            links = page.query_selector_all("a[href*='/remote-jobs/']")
            seen: set[str] = set()
            for link in links:
                href = link.get_attribute("href") or ""
                if not href or href == "/remote-jobs":
                    continue
                full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
                if full_url in seen:
                    continue

                title_el = link.query_selector("h2, h3, h4, [class*='title']") or link
                title = (title_el.inner_text() or "").strip()
                if not title or len(title) < 4:
                    continue
                if not _is_relevant(title):
                    continue

                company_el = link.query_selector("[class*='company'], [class*='employer']")
                company = (company_el.inner_text() or "").strip() if company_el else "Arc.dev"

                seen.add(full_url)
                jobs.append(
                    {
                        "id": _job_id(full_url),
                        "title": title,
                        "company": company or "Arc.dev",
                        "location": "Remote",
                        "is_remote": True,
                        "description": _build_description(title, company, full_url),
                        "job_url": full_url,
                        "site": "arc",
                    }
                )
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[arc] Playwright fallback failed for {search_url}: {exc}")

    return jobs


def fetch_arc_jobs() -> list[dict[str, Any]]:
    """
    Scrape Arc.dev for relevant remote roles.
    Returns job dicts compatible with the main pipeline.
    """
    jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for search_url in SEARCH_URLS:
        page_jobs: list[dict[str, Any]] = []

        # Try fast path: static HTML + __NEXT_DATA__
        try:
            import time

            time.sleep(1)  # be polite — arc.dev requests a crawl delay
            resp = httpx.get(search_url, headers=HEADERS, timeout=20, follow_redirects=True)
            resp.raise_for_status()
            page_jobs = _extract_from_next_data(resp.text)
        except Exception:  # noqa: BLE001
            pass

        # Fall back to Playwright if static extraction found nothing
        if not page_jobs:
            page_jobs = _fetch_via_playwright(search_url)

        for job in page_jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                jobs.append(job)

    print(f"[arc] Found {len(jobs)} jobs.")
    return jobs
