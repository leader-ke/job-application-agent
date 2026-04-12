"""Unit tests for agent.search.mygov_scraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.search.mygov_scraper import _is_relevant, _job_id, fetch_mygov_jobs

# ── _job_id ──────────────────────────────────────────────────────────────────


def test_job_id_starts_with_prefix():
    assert _job_id("https://example.com/job.pdf").startswith("mygov_")


def test_job_id_is_stable():
    url = "https://gaa.go.ke/uploads/ict-officer.pdf"
    assert _job_id(url) == _job_id(url)


def test_job_id_differs_for_different_urls():
    assert _job_id("https://gaa.go.ke/a.pdf") != _job_id("https://gaa.go.ke/b.pdf")


# ── _is_relevant ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "title, expected",
    [
        ("ICT Officer Grade 5", True),
        ("Senior Software Engineer", True),
        ("Head of Digital Transformation", True),
        ("PROGRAMME OFFICER - DATA MANAGEMENT", True),
        ("Systems Administrator", True),
        ("Cybersecurity Analyst", True),
        ("Database Administrator", True),
        ("Network Engineer", True),
        ("Driver/Mechanic", False),
        ("Administrative Assistant", False),
        ("Office Cleaner", False),
    ],
)
def test_is_relevant(title, expected):
    assert _is_relevant(title) is expected


# ── fetch_mygov_jobs ─────────────────────────────────────────────────────────


SAMPLE_HTML = """
<html><body>
  <a href="/uploads/ict-officer-grade-5.pdf">ICT Officer Grade 5 - Ministry of Finance</a>
  <a href="/uploads/driver.pdf">Driver/Mechanic Grade C</a>
  <a href="/uploads/software-qa-lead.pdf">Software QA Lead Engineer - NCA</a>
  <a href="https://external.com/unrelated">Short</a>
</body></html>
"""


def test_fetch_mygov_jobs_returns_relevant_only():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch("agent.search.mygov_scraper.httpx.get", return_value=mock_resp):
        jobs = fetch_mygov_jobs()

    titles = [j["title"] for j in jobs]
    assert any("ICT Officer" in t for t in titles)
    assert any("Software QA" in t for t in titles)
    assert not any("Driver" in t for t in titles)


def test_fetch_mygov_jobs_structure():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch("agent.search.mygov_scraper.httpx.get", return_value=mock_resp):
        jobs = fetch_mygov_jobs()

    for job in jobs:
        assert "id" in job
        assert job["id"].startswith("mygov_")
        assert job["company"] == "Kenya Government"
        assert job["location"] == "Kenya"
        assert job["site"] == "mygov"
        assert job["job_url"].startswith("http")


def test_fetch_mygov_jobs_handles_network_error():
    with patch("agent.search.mygov_scraper.httpx.get", side_effect=Exception("timeout")):
        jobs = fetch_mygov_jobs()
    assert jobs == []
