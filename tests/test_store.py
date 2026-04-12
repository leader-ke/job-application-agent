"""Unit tests for agent.data.store — uses a temp SQLite DB via monkeypatching."""

from __future__ import annotations

import pytest

from agent.data import store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect all store operations to a throwaway DB in tmp_path."""
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    store.ensure_tables()


# ── digests ───────────────────────────────────────────────────────────────────


def test_create_digest_returns_int():
    digest_id = store.create_digest("Test subject", 5)
    assert isinstance(digest_id, int)
    assert digest_id >= 1


def test_get_digest_fields():
    digest_id = store.create_digest("My digest", 10)
    d = store.get_digest(digest_id)
    assert d is not None
    assert d["subject"] == "My digest"
    assert d["jobs_count"] == 10
    assert d["replied"] == 0


def test_get_digest_missing_returns_none():
    assert store.get_digest(9999) is None


def test_update_digest_subject():
    digest_id = store.create_digest("Old subject", 3)
    store.update_digest_subject(digest_id, "New subject")
    assert store.get_digest(digest_id)["subject"] == "New subject"


def test_mark_digest_replied():
    digest_id = store.create_digest("D", 0)
    store.mark_digest_replied(digest_id)
    assert store.get_digest(digest_id)["replied"] == 1


# ── pending_jobs ──────────────────────────────────────────────────────────────


SAMPLE_JOB = {
    "id": "job_abc",
    "title": "Senior QA Engineer",
    "company": "EIDU",
    "location": "Nairobi, Kenya",
    "job_url": "https://jobs.greenhouse.io/eidu/qa",
}

SAMPLE_ANALYSIS = {
    "score": 82,
    "rationale": "Strong QA + automation match.",
    "tailored_bullets": ["Led automated test suites"],
    "cover_letter": "Dear Hiring Manager...",
}


def test_save_and_retrieve_pending_job():
    digest_id = store.create_digest("D", 1)
    store.save_pending_job(SAMPLE_JOB, SAMPLE_ANALYSIS, digest_id, digest_num=1)

    results = store.get_jobs_by_digest_nums(digest_id, [1])
    assert len(results) == 1
    row = results[0]
    assert row["title"] == "Senior QA Engineer"
    assert row["score"] == 82
    assert row["company"] == "EIDU"


def test_get_jobs_by_digest_nums_wrong_num():
    digest_id = store.create_digest("D", 1)
    store.save_pending_job(SAMPLE_JOB, SAMPLE_ANALYSIS, digest_id, digest_num=1)

    assert store.get_jobs_by_digest_nums(digest_id, [99]) == []


def test_get_jobs_by_digest_nums_empty_list():
    digest_id = store.create_digest("D", 0)
    assert store.get_jobs_by_digest_nums(digest_id, []) == []


def test_mark_job_status_removes_from_pending():
    digest_id = store.create_digest("D", 1)
    store.save_pending_job(SAMPLE_JOB, SAMPLE_ANALYSIS, digest_id, digest_num=1)

    store.mark_job_status("job_abc", "applied")
    # status != pending so it should not be returned
    assert store.get_jobs_by_digest_nums(digest_id, [1]) == []


def test_save_pending_job_upserts():
    digest_id = store.create_digest("D", 1)
    store.save_pending_job(SAMPLE_JOB, SAMPLE_ANALYSIS, digest_id, digest_num=1)

    updated_analysis = {**SAMPLE_ANALYSIS, "score": 90}
    store.save_pending_job(SAMPLE_JOB, updated_analysis, digest_id, digest_num=1)

    results = store.get_jobs_by_digest_nums(digest_id, [1])
    assert results[0]["score"] == 90
