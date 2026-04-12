"""Unit tests for agent.search.crossover_scraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.search.crossover_scraper import _build_description, _job_id, fetch_crossover_jobs


def test_job_id_prefix():
    assert _job_id("https://crossover.com/jobs/123").startswith("crossover_")


def test_job_id_stable():
    url = "https://crossover.com/jobs/qa-engineer"
    assert _job_id(url) == _job_id(url)


def test_job_id_differs():
    assert _job_id("https://crossover.com/jobs/a") != _job_id("https://crossover.com/jobs/b")


def test_build_description_contains_title():
    desc = _build_description("QA Lead", "Acme", "https://crossover.com/jobs/1")
    assert "QA Lead" in desc
    assert "Acme" in desc
    assert "crossover.com" in desc


def test_fetch_crossover_jobs_handles_playwright_error():
    """fetch_crossover_jobs must return [] on any Playwright failure."""
    with patch(
        "agent.search.crossover_scraper.sync_playwright", side_effect=Exception("no browser")
    ):
        jobs = fetch_crossover_jobs()
    assert jobs == []


def test_fetch_crossover_jobs_returns_job_from_link():
    """Simulate Playwright finding a job link on the page."""
    mock_link = MagicMock()
    mock_link.get_attribute.return_value = "/jobs/senior-qa-engineer"
    mock_link.query_selector.return_value = None
    mock_link.inner_text.return_value = "Senior QA Engineer"

    mock_page = MagicMock()
    mock_page.query_selector_all.return_value = [mock_link]
    mock_page.goto = MagicMock()
    mock_page.wait_for_load_state = MagicMock()
    mock_page.wait_for_selector = MagicMock()

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.__enter__ = MagicMock(return_value=mock_playwright)
    mock_playwright.__exit__ = MagicMock(return_value=False)
    mock_playwright.chromium.launch.return_value = mock_browser

    with patch("agent.search.crossover_scraper.sync_playwright", return_value=mock_playwright):
        jobs = fetch_crossover_jobs()

    assert len(jobs) >= 1
    assert jobs[0]["site"] == "crossover"
    assert jobs[0]["is_remote"] is True
    assert jobs[0]["location"] == "Remote"
