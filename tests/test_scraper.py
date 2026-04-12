"""Unit tests for agent.search.scraper — pure helpers and fetch_new_jobs."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from agent.search.scraper import _location_ok, _make_job_id, _norm_key, _normalize, fetch_new_jobs

# ── _normalize ──────────────────────────────────────────────────────────────


def test_normalize_strips_non_alnum():
    assert _normalize("Senior QA Engineer") == "seniorqaengineer"


def test_normalize_lowercases():
    assert _normalize("EIDU") == "eidu"


def test_normalize_removes_hyphens_and_spaces():
    assert _normalize("foo-bar baz") == "foobarbaz"


# ── _norm_key ───────────────────────────────────────────────────────────────


def test_norm_key_format():
    assert _norm_key("Senior QA Engineer", "EIDU") == "seniorqaengineer::eidu"


def test_norm_key_same_for_equivalent_titles():
    assert _norm_key("Senior QA  Engineer", "Acme Inc.") == _norm_key(
        "Senior QA Engineer", "Acme Inc"
    )


# ── _location_ok ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "job_location, is_remote, search_location, expected",
    [
        # is_remote flag always passes
        ("New York, US", True, "Remote", True),
        ("New York, US", True, "Nairobi Kenya", True),
        # Remote search — must be remote or blank location
        ("Remote", False, "Remote", True),
        ("", False, "Remote", True),  # blank = assume remote
        ("New York, US", False, "Remote", False),
        # Kenya search — must be Kenya or remote
        ("Nairobi, Kenya", False, "Nairobi Kenya", True),
        ("Kenya", False, "Nairobi Kenya", True),
        ("Remote", False, "Nairobi Kenya", True),
        ("London, UK", False, "Nairobi Kenya", False),
        # Generic search — always passes
        ("Anywhere", False, "Global", True),
    ],
)
def test_location_ok(job_location, is_remote, search_location, expected):
    assert _location_ok(job_location, is_remote, search_location) is expected


# ── _make_job_id ─────────────────────────────────────────────────────────────


def test_make_job_id_prefers_url():
    row = pd.Series({"job_url": "https://example.com/job/123", "title": "Eng", "company": "Acme"})
    assert _make_job_id(row) == "https://example.com/job/123"


def test_make_job_id_strips_whitespace():
    row = pd.Series({"job_url": "  https://example.com/  ", "title": "Eng", "company": "Acme"})
    assert _make_job_id(row) == "https://example.com/"


def test_make_job_id_fallback_nan():
    # pandas uses NaN (float) for None in mixed-type Series
    row = pd.Series({"job_url": float("nan"), "title": "Eng", "company": "Acme"})
    assert _make_job_id(row) == "eng::acme"


def test_make_job_id_fallback_empty_url():
    row = pd.Series({"job_url": "", "title": "QA Lead", "company": "EIDU"})
    assert _make_job_id(row) == "qa lead::eidu"


# ── fetch_new_jobs ────────────────────────────────────────────────────────────

_SAMPLE_ROW = {
    "title": "Senior QA Engineer",
    "company": "EIDU",
    "location": "Nairobi, Kenya",
    "is_remote": False,
    "job_url": "https://jobs.greenhouse.io/eidu/qa-engineer",
    "description": "Senior QA role requiring Python and Playwright.",
    "site": "linkedin",
}


@pytest.fixture()
def mock_db(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.search.scraper.DB_PATH", tmp_path / "scraper.db")


def test_fetch_new_jobs_returns_matching_job(mock_db):
    df = pd.DataFrame([_SAMPLE_ROW])
    with (
        patch("agent.search.scraper.scrape_jobs", return_value=df),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        jobs = fetch_new_jobs(
            roles=["Senior QA Engineer"],
            locations=["Nairobi Kenya"],
            sources=["linkedin"],
            results_per_search=10,
            exclude_keywords=[],
        )
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior QA Engineer"
    assert jobs[0]["company"] == "EIDU"
    assert "is_remote" in jobs[0]


def test_fetch_new_jobs_deduplicates_across_calls(mock_db):
    df = pd.DataFrame([_SAMPLE_ROW])
    with (
        patch("agent.search.scraper.scrape_jobs", return_value=df),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        first = fetch_new_jobs(["QA"], ["Nairobi Kenya"], ["linkedin"], 10, [])
        second = fetch_new_jobs(["QA"], ["Nairobi Kenya"], ["linkedin"], 10, [])

    assert len(first) == 1
    assert len(second) == 0  # already seen


def test_fetch_new_jobs_excludes_keywords(mock_db):
    junior_row = {
        **_SAMPLE_ROW,
        "title": "Junior QA Engineer",
        "description": "entry level junior role",
    }
    df = pd.DataFrame([junior_row])
    with (
        patch("agent.search.scraper.scrape_jobs", return_value=df),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        jobs = fetch_new_jobs(["QA"], ["Nairobi Kenya"], ["linkedin"], 10, ["junior"])
    assert jobs == []


def test_fetch_new_jobs_filters_wrong_location(mock_db):
    london_row = {
        **_SAMPLE_ROW,
        "location": "London, UK",
        "is_remote": False,
        "job_url": "https://example.com/london-job",
    }
    df = pd.DataFrame([london_row])
    with (
        patch("agent.search.scraper.scrape_jobs", return_value=df),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        jobs = fetch_new_jobs(["QA"], ["Nairobi Kenya"], ["linkedin"], 10, [])
    assert jobs == []


def test_fetch_new_jobs_handles_scrape_failure(mock_db):
    with (
        patch("agent.search.scraper.scrape_jobs", side_effect=Exception("network error")),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        jobs = fetch_new_jobs(["QA"], ["Nairobi Kenya"], ["linkedin"], 10, [])
    assert jobs == []


def test_fetch_new_jobs_includes_mygov(mock_db):
    mygov_job = {
        "id": "mygov_abc123",
        "title": "ICT Officer",
        "company": "Kenya Government",
        "location": "Kenya",
        "description": "ICT Officer role",
        "job_url": "https://gaa.go.ke/job.pdf",
        "site": "mygov",
    }
    with (
        patch("agent.search.scraper.scrape_jobs", return_value=pd.DataFrame()),
        patch("agent.search.scraper.fetch_mygov_jobs", return_value=[mygov_job]),
        patch("agent.search.scraper.fetch_crossover_jobs", return_value=[]),
        patch("agent.search.scraper.fetch_arc_jobs", return_value=[]),
    ):
        jobs = fetch_new_jobs(["ICT"], ["Kenya"], ["linkedin"], 10, [])
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Kenya Government"
