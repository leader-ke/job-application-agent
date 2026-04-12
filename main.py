"""
Job Application Agent — orchestrator.

Usage:
    uv run main.py [--dry-run | --digest | --apply-approved]

Modes:
    (no flag)         Search, analyze, and auto-apply based on thresholds.
    --dry-run         Search and analyze; print results. No applications submitted.
    --digest          Search, analyze, save pending jobs, send email digest.
    --apply-approved  Check Gmail for APPLY replies and apply to approved jobs.
"""

from __future__ import annotations

# load_dotenv MUST run before any project imports that call os.getenv at module level
from dotenv import load_dotenv

load_dotenv()

import json
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from agent.analyze.scorer import analyze_job
from agent.apply.browser import apply
from agent.data.store import (
    create_digest,
    ensure_tables,
    get_digest,
    get_jobs_by_digest_nums,
    mark_digest_replied,
    mark_job_status,
    save_pending_job,
    update_digest_subject,
)
from agent.notify.emailer import send_application_confirmation, send_digest, send_no_results
from agent.notify.reply_checker import check_for_approvals
from agent.search.scraper import fetch_new_jobs

console = Console()
PREFS_PATH = Path(__file__).parent / "config" / "preferences.yaml"


def load_prefs() -> dict:
    return yaml.safe_load(PREFS_PATH.read_text())


# ---------------------------------------------------------------------------
# Shared: search + analyze
# ---------------------------------------------------------------------------


def _search_and_analyze(prefs: dict) -> list[tuple[dict, dict, str]]:
    """Run search and analyze passes. Returns (job, analysis, decision) tuples."""
    console.print("\n[bold]Searching job boards...[/bold]")
    jobs = fetch_new_jobs(
        roles=prefs["roles"],
        locations=prefs["locations"],
        sources=prefs["sources"],
        results_per_search=prefs["results_per_search"],
        exclude_keywords=prefs.get("exclude_keywords", []),
    )
    console.print(f"Found {len(jobs)} new listings.\n")

    auto_threshold: int = prefs["auto_apply_threshold"]
    review_threshold: int = prefs["review_threshold"]

    results: list[tuple[dict, dict, str]] = []
    for job in jobs:
        console.print(f"  Analyzing: [cyan]{job['title']}[/cyan] @ {job['company']}")
        analysis = analyze_job(job)
        score: int = analysis.get("score", 0)

        if score < review_threshold:
            decision = "skip"
        elif score < auto_threshold:
            decision = "review"
        else:
            decision = "apply"

        results.append((job, analysis, decision))

    return results


# ---------------------------------------------------------------------------
# Mode: --dry-run
# ---------------------------------------------------------------------------


def run_dry(prefs: dict) -> None:
    results = _search_and_analyze(prefs)
    if not results:
        console.print("Nothing new. Exiting.")
        return

    table = Table("Title", "Company", "Score", "Decision", show_lines=True)
    for job, analysis, decision in results:
        score = analysis.get("score", 0)
        if decision == "review":
            console.print(f"    [yellow]Needs review[/yellow] (score {score}): {job['job_url']}")
        elif decision == "skip":
            console.print(f"    [dim]Skipped (score {score})[/dim]")
        table.add_row(job["title"], job["company"], str(score), decision)

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Mode: --digest
# ---------------------------------------------------------------------------


def run_digest(prefs: dict) -> None:
    """Search, analyze, save actionable jobs to DB, send email digest."""
    ensure_tables()
    results = _search_and_analyze(prefs)

    # Include all jobs above review_threshold — user decides via email reply
    actionable = [
        (job, analysis, decision)
        for job, analysis, decision in results
        if decision in ("review", "apply")
    ]

    if not actionable:
        console.print("[yellow]No actionable jobs found. Sending no-results notification.[/yellow]")
        try:
            send_no_results(
                new_listings=len(results),
                analyzed=len(results),
                review_threshold=prefs["review_threshold"],
            )
            console.print("[dim]No-results email sent.[/dim]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[dim]No-results email failed: {exc}[/dim]")
        return

    # Reserve a digest ID first, then update subject once we know it
    digest_id = create_digest("pending", len(actionable))

    digest_jobs: list[dict] = []
    for num, (job, analysis, decision) in enumerate(actionable, start=1):
        save_pending_job(job, analysis, digest_id=digest_id, digest_num=num)
        digest_jobs.append(
            {
                "digest_num": num,
                "id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "job_url": job["job_url"],
                "score": analysis.get("score", 0),
                "rationale": analysis.get("rationale", ""),
                "decision": decision,
            }
        )

    subject = send_digest(digest_jobs, digest_id)
    update_digest_subject(digest_id, subject)

    console.print(f"\n[green]Digest sent:[/green] {subject}")
    console.print(
        f"Included [bold]{len(digest_jobs)}[/bold] jobs — "
        "reply with [bold]APPLY: <numbers>[/bold] to approve."
    )

    # Print local table too
    table = Table("#", "Score", "Title", "Company", "Decision", show_lines=True)
    for j in digest_jobs:
        table.add_row(
            str(j["digest_num"]),
            str(j["score"]),
            j["title"],
            j["company"],
            j["decision"],
        )
    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Mode: --apply-approved
# ---------------------------------------------------------------------------


def run_apply_approved() -> None:
    """Check Gmail for APPLY replies and apply to those jobs."""
    ensure_tables()
    console.print("\n[bold]Checking Gmail for approval replies...[/bold]")

    approvals = check_for_approvals()
    if not approvals:
        console.print("[dim]No approval replies found.[/dim]")
        return

    for approval in approvals:
        digest_id: int = approval["digest_id"]
        nums: list[int] = approval["approved_nums"]
        console.print(f"\n  Digest [bold]#{digest_id}[/bold]: approved job numbers {nums}")

        jobs_to_apply = get_jobs_by_digest_nums(digest_id, nums)
        if not jobs_to_apply:
            console.print(
                f"  [yellow]No pending jobs found for digest #{digest_id} "
                f"with numbers {nums}. Already applied or invalid numbers.[/yellow]"
            )
            continue

        digest_record = get_digest(digest_id)
        digest_subject = (
            digest_record["subject"] if digest_record else f"Job Agent Digest #{digest_id}"
        )

        for job_row in jobs_to_apply:
            job = {
                "id": job_row["id"],
                "title": job_row["title"],
                "company": job_row["company"],
                "location": job_row["location"],
                "job_url": job_row["job_url"],
            }
            analysis = {
                "tailored_bullets": json.loads(job_row["tailored_bullets"] or "[]"),
                "cover_letter": job_row["cover_letter"] or "",
            }
            console.print(f"  Applying: [cyan]{job['title']}[/cyan] @ {job['company']}")
            result = apply(job, analysis)
            status = result["status"]
            mark_job_status(job["id"], status)

            if status == "flagged":
                console.print(f"    [yellow]Flagged:[/yellow] {result['reason']}")
            else:
                console.print("    [green]Applied successfully[/green]")
                try:
                    send_application_confirmation(job, digest_id, digest_subject)
                except Exception as exc:  # noqa: BLE001
                    console.print(f"    [dim]Confirmation email failed: {exc}[/dim]")

        mark_digest_replied(digest_id)


# ---------------------------------------------------------------------------
# Mode: full auto (no flag)
# ---------------------------------------------------------------------------


def run_full(prefs: dict) -> None:
    results = _search_and_analyze(prefs)
    if not results:
        console.print("Nothing new. Exiting.")
        return

    table = Table("Title", "Company", "Score", "Decision", show_lines=True)
    for job, analysis, decision in results:
        score = analysis.get("score", 0)
        outcome = "—"
        if decision == "apply":
            result = apply(job, analysis)
            outcome = result["status"]
            if result["status"] == "flagged":
                console.print(f"    [yellow]Flagged:[/yellow] {result['reason']}")
        elif decision == "review":
            console.print(f"    [yellow]Needs review[/yellow] (score {score}): {job['job_url']}")
        elif decision == "skip":
            console.print(f"    [dim]Skipped (score {score})[/dim]")

        table.add_row(
            job["title"],
            job["company"],
            str(score),
            outcome if decision == "apply" else decision,
        )

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    console.rule("[bold blue]Job Application Agent")

    if "--digest" in sys.argv:
        console.print("Mode: [bold]Digest[/bold] — search → analyze → email", style="dim")
        run_digest(load_prefs())
    elif "--apply-approved" in sys.argv:
        console.print(
            "Mode: [bold]Apply Approved[/bold] — check Gmail replies → apply",
            style="dim",
        )
        run_apply_approved()
    elif "--dry-run" in sys.argv:
        console.print("Mode: [bold]Dry Run[/bold] — no applications submitted", style="dim")
        run_dry(load_prefs())
    else:
        console.print("Mode: [bold]Full Auto[/bold]", style="dim")
        run_full(load_prefs())


if __name__ == "__main__":
    main()
