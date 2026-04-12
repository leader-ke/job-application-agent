"""
Search layer: scrape job boards via JobSpy and deduplicate against SQLite store.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from jobspy2 import scrape_jobs

from agent.search.mygov_scraper import fetch_mygov_jobs

DB_PATH = Path(__file__).parents[2] / "data" / "jobs.db"


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            norm_key    TEXT,
            date_seen   TEXT DEFAULT (date('now'))
        )
        """
    )
    # Add norm_key column if upgrading from older schema
    try:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN norm_key TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation/whitespace for fuzzy dedup."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _make_job_id(row: pd.Series) -> str:
    """Stable ID: prefer job_url, fall back to title+company."""
    url = row.get("job_url") or ""
    if url:
        return url.strip()
    return f"{row.get('title', '')}::{row.get('company', '')}".lower()


def _norm_key(title: str, company: str) -> str:
    """Normalized key for duplicate detection across different URLs."""
    return _normalize(title) + "::" + _normalize(company)


def _location_ok(job_location: str, is_remote: Any, search_location: str) -> bool:
    """
    Return True only if the job's location matches the search intent.
    - "Remote" search → job must be explicitly remote
    - "Kenya"/"Nairobi" search → job must be in Kenya or remote
    """
    loc = (job_location or "").lower()
    search = search_location.lower()

    # JobSpy's is_remote flag is the most reliable signal
    if is_remote is True:
        return True

    if "remote" in search:
        return "remote" in loc or not loc.strip()

    if "kenya" in search or "nairobi" in search:
        return "kenya" in loc or "nairobi" in loc or "remote" in loc

    return True


def fetch_new_jobs(
    roles: list[str],
    locations: list[str],
    sources: list[str],
    results_per_search: int,
    exclude_keywords: list[str],
) -> list[dict[str, Any]]:
    """
    Scrape job boards, filter out seen/duplicate jobs and excluded keywords.
    Returns a list of job dicts ready for the analyze layer.
    """
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _ensure_db(conn)

    new_jobs: list[dict[str, Any]] = []
    # In-memory set of norm_keys already queued this run (prevents same job
    # appearing multiple times when it shows up in different role/location queries)
    seen_this_run: set[str] = set()

    def _is_duplicate(job_id: str, nkey: str) -> bool:
        if nkey in seen_this_run:
            return True
        row = conn.execute(
            "SELECT 1 FROM seen_jobs WHERE id = ? OR norm_key = ?",
            (job_id, nkey),
        ).fetchone()
        return row is not None

    def _record(job_id: str, title: str, company: str, location: str) -> None:
        nkey = _norm_key(title, company)
        conn.execute(
            """INSERT OR IGNORE INTO seen_jobs (id, title, company, location, norm_key)
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, title, company, location, nkey),
        )
        conn.commit()
        seen_this_run.add(nkey)

    for role in roles:
        for location in locations:
            try:
                df: pd.DataFrame = scrape_jobs(
                    site_name=sources,
                    search_term=role,
                    location=location,
                    results_wanted=results_per_search,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[search] scrape failed for '{role}' / '{location}': {exc}")
                continue

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                title = str(row.get("title") or "")
                company = str(row.get("company") or "")
                job_location = str(row.get("location") or "")
                is_remote = row.get("is_remote")
                job_id = _make_job_id(row)
                nkey = _norm_key(title, company)

                if _is_duplicate(job_id, nkey):
                    continue

                # Strict location gate — only Kenya or genuinely remote
                if not _location_ok(job_location, is_remote, location):
                    continue

                description = str(row.get("description") or "")
                title_and_desc = (title + " " + description).lower()
                if any(kw.lower() in title_and_desc for kw in exclude_keywords):
                    continue

                _record(job_id, title, company, str(row.get("location") or ""))

                new_jobs.append(
                    {
                        "id": job_id,
                        "title": title,
                        "company": company,
                        "location": str(row.get("location") or ""),
                        "is_remote": bool(is_remote),
                        "description": description,
                        "job_url": str(row.get("job_url") or ""),
                        "site": str(row.get("site") or ""),
                    }
                )

    # --- MyGov (Kenya government jobs — always included) ---
    try:
        for job in fetch_mygov_jobs():
            job_id = job["id"]
            nkey = _norm_key(job["title"], job["company"])
            if _is_duplicate(job_id, nkey):
                continue
            title_and_desc = (job["title"] + " " + job.get("description", "")).lower()
            if any(kw.lower() in title_and_desc for kw in exclude_keywords):
                continue
            _record(job_id, job["title"], job["company"], job["location"])
            new_jobs.append(job)
    except Exception as exc:  # noqa: BLE001
        print(f"[search] mygov scrape failed: {exc}")

    conn.close()
    return new_jobs
