"""
Persistent store for pending jobs (awaiting human approval) and digest records.
Uses the same SQLite DB as the scraper: data/jobs.db.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parents[2] / "data" / "jobs.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS digests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT    DEFAULT (date('now')),
                subject     TEXT,
                jobs_count  INTEGER,
                replied     INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_jobs (
                id               TEXT PRIMARY KEY,
                digest_id        INTEGER REFERENCES digests(id),
                digest_num       INTEGER,
                title            TEXT,
                company          TEXT,
                location         TEXT,
                job_url          TEXT,
                score            INTEGER,
                rationale        TEXT,
                tailored_bullets TEXT,
                cover_letter     TEXT,
                status           TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()


def create_digest(subject: str, jobs_count: int) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO digests (subject, jobs_count) VALUES (?, ?)",
            (subject, jobs_count),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def update_digest_subject(digest_id: int, subject: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE digests SET subject = ? WHERE id = ?", (subject, digest_id))
        conn.commit()


def save_pending_job(
    job: dict[str, Any],
    analysis: dict[str, Any],
    digest_id: int,
    digest_num: int,
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pending_jobs
                (id, digest_id, digest_num, title, company, location, job_url,
                 score, rationale, tailored_bullets, cover_letter, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                job["id"],
                digest_id,
                digest_num,
                job["title"],
                job["company"],
                job["location"],
                job["job_url"],
                analysis.get("score", 0),
                analysis.get("rationale", ""),
                json.dumps(analysis.get("tailored_bullets", [])),
                analysis.get("cover_letter", ""),
            ),
        )
        conn.commit()


def get_jobs_by_digest_nums(digest_id: int, nums: list[int]) -> list[dict[str, Any]]:
    if not nums:
        return []
    placeholders = ",".join("?" * len(nums))
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM pending_jobs
                WHERE digest_id = ? AND digest_num IN ({placeholders})
                  AND status = 'pending'""",
            (digest_id, *nums),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_job_status(job_id: str, status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE pending_jobs SET status = ? WHERE id = ?",
            (status, job_id),
        )
        conn.commit()


def mark_digest_replied(digest_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE digests SET replied = 1 WHERE id = ?", (digest_id,))
        conn.commit()


def get_digest(digest_id: int) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM digests WHERE id = ?", (digest_id,)).fetchone()
    return dict(row) if row else None
