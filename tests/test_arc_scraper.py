"""Unit tests for agent.search.arc_scraper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent.search.arc_scraper import (
    _build_description,
    _extract_from_next_data,
    _job_id,
    fetch_arc_jobs,
)

# ── _job_id ──────────────────────────────────────────────────────────────────


def test_job_id_prefix():
    assert _job_id("https://arc.dev/remote-jobs/qa-engineer").startswith("arc_")


def test_job_id_stable():
    url = "https://arc.dev/remote-jobs/qa-lead"
    assert _job_id(url) == _job_id(url)


def test_job_id_differs():
    assert _job_id("https://arc.dev/remote-jobs/a") != _job_id("https://arc.dev/remote-jobs/b")


# ── _build_description ───────────────────────────────────────────────────────


def test_build_description_includes_fields():
    desc = _build_description("QA Lead", "TechCorp", "https://arc.dev/remote-jobs/qa-lead")
    assert "QA Lead" in desc
    assert "TechCorp" in desc
    assert "arc.dev" in desc


# ── _extract_from_next_data ───────────────────────────────────────────────────


def _make_next_data(jobs: list[dict]) -> str:
    data = {"props": {"pageProps": {"jobs": jobs}}}
    payload = json.dumps(data)
    return f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'


def test_extract_from_next_data_finds_jobs():
    html = _make_next_data(
        [
            {"title": "QA Engineer", "slug": "qa-engineer-abc", "company": {"name": "Acme"}},
            {"title": "Product Manager", "slug": "pm-xyz", "company": {"name": "Beta"}},
        ]
    )
    jobs = _extract_from_next_data(html)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "QA Engineer"
    assert jobs[0]["site"] == "arc"
    assert jobs[0]["is_remote"] is True
    assert jobs[1]["company"] == "Beta"


def test_extract_from_next_data_deduplicates_slugs():
    html = _make_next_data(
        [
            {"title": "QA Engineer", "slug": "qa-dup"},
            {"title": "QA Engineer", "slug": "qa-dup"},
        ]
    )
    jobs = _extract_from_next_data(html)
    assert len(jobs) == 1


def test_extract_from_next_data_no_script():
    assert _extract_from_next_data("<html><body>No Next data</body></html>") == []


def test_extract_from_next_data_bad_json():
    assert (
        _extract_from_next_data(
            '<script id="__NEXT_DATA__" type="application/json">{bad json}</script>'
        )
        == []
    )


def test_extract_from_next_data_no_jobs_key():
    data = json.dumps({"props": {"pageProps": {}}})
    html = f'<script id="__NEXT_DATA__" type="application/json">{data}</script>'
    assert _extract_from_next_data(html) == []


# ── fetch_arc_jobs ────────────────────────────────────────────────────────────


def test_fetch_arc_jobs_uses_next_data(monkeypatch):
    html = _make_next_data(
        [
            {"title": "Senior QA Engineer", "slug": "senior-qa", "company": {"name": "EIDU"}},
        ]
    )
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    with patch("agent.search.arc_scraper.httpx.get", return_value=mock_resp):
        jobs = fetch_arc_jobs()

    titles = [j["title"] for j in jobs]
    assert "Senior QA Engineer" in titles
    assert all(j["site"] == "arc" for j in jobs)


def test_fetch_arc_jobs_deduplicates_across_search_terms():
    """Same slug returned for multiple search terms should only appear once."""
    html = _make_next_data(
        [
            {"title": "QA Engineer", "slug": "qa-123", "company": {"name": "Co"}},
        ]
    )
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status = MagicMock()

    with patch("agent.search.arc_scraper.httpx.get", return_value=mock_resp):
        jobs = fetch_arc_jobs()

    ids = [j["id"] for j in jobs]
    assert len(ids) == len(set(ids))  # no duplicates


def test_fetch_arc_jobs_handles_http_error():
    with (
        patch("agent.search.arc_scraper.httpx.get", side_effect=Exception("timeout")),
        patch("agent.search.arc_scraper._fetch_via_playwright", return_value=[]),
    ):
        jobs = fetch_arc_jobs()
    assert jobs == []
