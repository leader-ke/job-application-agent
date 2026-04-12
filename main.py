"""
Job Application Agent — orchestrator.

Usage:
    uv run main.py [--dry-run]

Flags:
    --dry-run   Search and analyze but never submit applications.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from agent.analyze.scorer import analyze_job
from agent.apply.browser import apply
from agent.search.scraper import fetch_new_jobs

load_dotenv()
console = Console()
PREFS_PATH = Path(__file__).parent / "config" / "preferences.yaml"


def load_prefs() -> dict:
    return yaml.safe_load(PREFS_PATH.read_text())


def main(dry_run: bool = False) -> None:
    prefs = load_prefs()

    console.rule("[bold blue]Job Application Agent")
    console.print(f"Dry run: {dry_run}", style="dim")

    # --- Search ---
    console.print("\n[bold]Searching job boards...[/bold]")
    jobs = fetch_new_jobs(
        roles=prefs["roles"],
        locations=prefs["locations"],
        sources=prefs["sources"],
        results_per_search=prefs["results_per_search"],
        exclude_keywords=prefs.get("exclude_keywords", []),
    )
    console.print(f"Found {len(jobs)} new listings.\n")

    if not jobs:
        console.print("Nothing new. Exiting.")
        return

    results_table = Table("Title", "Company", "Score", "Decision", show_lines=True)

    for job in jobs:
        # --- Analyze ---
        console.print(f"  Analyzing: [cyan]{job['title']}[/cyan] @ {job['company']}")
        analysis = analyze_job(job)
        score: int = analysis.get("score", 0)

        auto_threshold: int = prefs["auto_apply_threshold"]
        review_threshold: int = prefs["review_threshold"]

        if score < review_threshold:
            decision = "skip"
        elif score < auto_threshold:
            decision = "review"
        else:
            decision = "apply"

        # --- Apply ---
        outcome = "—"
        if decision == "apply" and not dry_run:
            result = apply(job, analysis)
            outcome = result["status"]
            if result["status"] == "flagged":
                console.print(f"    [yellow]Flagged:[/yellow] {result['reason']}")
        elif decision == "review":
            console.print(
                f"    [yellow]Needs review[/yellow] (score {score}): {job['job_url']}"
            )
        elif decision == "skip":
            console.print(f"    [dim]Skipped (score {score})[/dim]")

        results_table.add_row(
            job["title"],
            job["company"],
            str(score),
            outcome if decision == "apply" else decision,
        )

    console.print()
    console.print(results_table)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
