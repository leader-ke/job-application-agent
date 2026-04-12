"""
Search layer: scrape job boards via JobSpy and deduplicate against SQLite store.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

DB_PATH = Path(__file__).parents[2] / "data" / "jobs.db"


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            date_seen TEXT DEFAULT (date('now'))
        )
        """
    )
    conn.commit()


def _make_job_id(row: pd.Series) -> str:
    """Stable ID from job_url, falling back to title+company."""
    url = row.get("job_url") or ""
    if url:
        return url.strip()
    return f"{row.get('title', '')}::{row.get('company', '')}".lower()


def fetch_new_jobs(
    roles: list[str],
    locations: list[str],
    sources: list[str],
    results_per_search: int,
    exclude_keywords: list[str],
) -> list[dict[str, Any]]:
    """
    Scrape job boards, filter out seen jobs and excluded keywords.
    Returns a list of job dicts ready for the analyze layer.
    """
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    _ensure_db(conn)

    new_jobs: list[dict[str, Any]] = []

    for role in roles:
        for location in locations:
            try:
                df: pd.DataFrame = scrape_jobs(
                    site_name=sources,
                    search_term=role,
                    location=location,
                    results_wanted=results_per_search,
                    country_indeed="worldwide",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[search] scrape failed for '{role}' / '{location}': {exc}")
                continue

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                job_id = _make_job_id(row)

                # Deduplication check
                exists = conn.execute(
                    "SELECT 1 FROM seen_jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if exists:
                    continue

                description = str(row.get("description") or "")

                # Keyword exclusion
                lowered = description.lower()
                if any(kw.lower() in lowered for kw in exclude_keywords):
                    continue

                conn.execute(
                    "INSERT INTO seen_jobs (id, title, company, location) VALUES (?, ?, ?, ?)",
                    (
                        job_id,
                        str(row.get("title") or ""),
                        str(row.get("company") or ""),
                        str(row.get("location") or ""),
                    ),
                )
                conn.commit()

                new_jobs.append(
                    {
                        "id": job_id,
                        "title": str(row.get("title") or ""),
                        "company": str(row.get("company") or ""),
                        "location": str(row.get("location") or ""),
                        "description": description,
                        "job_url": str(row.get("job_url") or ""),
                        "site": str(row.get("site") or ""),
                    }
                )

    conn.close()
    return new_jobs
