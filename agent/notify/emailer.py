"""
Send HTML email digests via Gmail SMTP.

Setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to myaccount.google.com → Security → App passwords.
  3. Generate a password for "Mail" and put it in GMAIL_APP_PASSWORD in .env.
  4. Enable IMAP in Gmail settings (for reply detection).
"""

from __future__ import annotations

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "kenisiaho@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DIGEST_RECIPIENT = os.getenv("DIGEST_RECIPIENT", GMAIL_ADDRESS)


def _score_color(score: int) -> str:
    if score >= 75:
        return "#16a34a"  # green
    if score >= 55:
        return "#d97706"  # amber
    return "#dc2626"  # red


def _score_label(score: int, decision: str) -> str:
    if decision == "apply":
        return f"{score} ✦ auto"
    return str(score)


def build_subject(digest_id: int, match_count: int) -> str:
    return f"Job Agent Digest #{digest_id} — {date.today().isoformat()} ({match_count} matches)"


_SUPPORTED_PORTALS = ("greenhouse.io", "lever.co")


def _apply_method(url: str) -> str:
    """Return a short label indicating how this job will be applied to."""
    if not url:
        return "Manual"
    if any(p in url for p in _SUPPORTED_PORTALS):
        return "Auto"
    if url.endswith(".pdf"):
        return "PDF"
    return "Manual"


def _apply_badge(url: str) -> str:
    method = _apply_method(url)
    if method == "Auto":
        return '<span style="background:#dcfce7;color:#166534;padding:2px 7px;border-radius:4px;font-size:0.8em;font-weight:bold;">Auto</span>'
    if method == "PDF":
        return '<span style="background:#fef9c3;color:#854d0e;padding:2px 7px;border-radius:4px;font-size:0.8em;font-weight:bold;">PDF</span>'
    return '<span style="background:#fee2e2;color:#991b1b;padding:2px 7px;border-radius:4px;font-size:0.8em;font-weight:bold;">Manual</span>'


def _build_html(jobs: list[dict[str, Any]], digest_id: int) -> str:
    rows = ""
    for j in jobs:
        color = _score_color(j["score"])
        label = _score_label(j["score"], j.get("decision", "review"))
        url = j["job_url"]
        short_url = (url[:50] + "…") if len(url) > 50 else url
        link = f'<a href="{url}" style="color:#1d4ed8;">{short_url}</a>'
        badge = _apply_badge(url)
        bg = "#f0fdf4" if j.get("decision") == "apply" else "#fff"
        loc_text = j["location"] or "—"
        is_remote = j.get("is_remote") or "remote" in loc_text.lower()
        remote_tag = (
            ' <span style="background:#e0f2fe;color:#0369a1;padding:1px 5px;'
            'border-radius:3px;font-size:0.78em;font-weight:bold;">Remote</span>'
            if is_remote
            else ""
        )
        rows += f"""
        <tr style="background:{bg};">
          <td style="text-align:center;font-weight:bold;padding:8px 12px;">{j["digest_num"]}</td>
          <td style="color:{color};text-align:center;font-weight:bold;padding:8px 12px;">{label}</td>
          <td style="padding:8px 12px;">{j["title"]}</td>
          <td style="padding:8px 12px;">{j["company"]}</td>
          <td style="padding:8px 12px;font-size:0.85em;">{loc_text}{remote_tag}</td>
          <td style="padding:8px 12px;text-align:center;">{badge}</td>
          <td style="padding:8px 12px;font-size:0.82em;color:#444;">{j["rationale"]}</td>
          <td style="padding:8px 12px;font-size:0.8em;">{link}</td>
        </tr>"""

    all_nums = ", ".join(str(j["digest_num"]) for j in jobs)
    review_nums = ", ".join(str(j["digest_num"]) for j in jobs if j.get("decision") != "apply")

    return f"""
    <html>
    <body style="font-family:sans-serif;color:#1a1a1a;max-width:1000px;margin:auto;padding:16px;">
      <h2 style="color:#1d4ed8;margin-bottom:4px;">
        Job Agent Digest #{digest_id} &mdash; {date.today().isoformat()}
      </h2>
      <p style="color:#555;margin-top:4px;">
        Found <strong>{len(jobs)}</strong> matches above your review threshold.
        ✦ = above auto-apply threshold (75+) &bull;
        <span style="background:#dcfce7;color:#166534;padding:1px 5px;border-radius:3px;font-size:0.85em;">Auto</span> = Greenhouse/Lever (automated) &bull;
        <span style="background:#fee2e2;color:#991b1b;padding:1px 5px;border-radius:3px;font-size:0.85em;">Manual</span> = open link and apply yourself &bull;
        <span style="background:#fef9c3;color:#854d0e;padding:1px 5px;border-radius:3px;font-size:0.85em;">PDF</span> = government advert
      </p>

      <table border="0" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;width:100%;border:1px solid #e5e7eb;font-size:0.88em;">
        <thead>
          <tr style="background:#1d4ed8;color:#fff;">
            <th style="padding:10px 12px;">#</th>
            <th style="padding:10px 12px;">Score</th>
            <th style="padding:10px 12px;text-align:left;">Title</th>
            <th style="padding:10px 12px;text-align:left;">Company</th>
            <th style="padding:10px 12px;text-align:left;">Location</th>
            <th style="padding:10px 12px;text-align:center;">Apply</th>
            <th style="padding:10px 12px;text-align:left;">Why this score</th>
            <th style="padding:10px 12px;text-align:left;">Apply URL</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>

      <br>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;padding:18px;border-radius:8px;">
        <strong style="font-size:1em;">How to approve applications:</strong><br><br>
        Reply to this email with the job numbers you want to apply to:<br><br>
        <code style="background:#dbeafe;padding:6px 12px;border-radius:4px;font-size:0.95em;">
          APPLY: {all_nums}
        </code><br><br>
        <span style="color:#555;font-size:0.9em;">
          Green rows (✦) are above your auto-apply threshold — they are held for your approval in digest mode.<br>
          Amber rows scored 55–74 and need your explicit go-ahead.<br>
          Reply checking runs hourly. The agent will apply to your chosen jobs on the next check.
          {f"<br><br>Jobs needing review only: <code>{review_nums}</code>" if review_nums else ""}
        </span>
      </div>

      <p style="color:#9ca3af;font-size:0.78em;margin-top:20px;">
        Sent by your local Job Application Agent &bull; Digest #{digest_id}<br>
        To stop receiving digests, pause the launchd agent:
        <code>launchctl unload ~/Library/LaunchAgents/com.jobagent.digest.plist</code>
      </p>
    </body>
    </html>
    """


def send_digest(jobs: list[dict[str, Any]], digest_id: int) -> str:
    """Send HTML digest email. Returns the subject line."""
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD is not set in .env. Generate a Gmail App Password and add it."
        )

    subject = build_subject(digest_id, len(jobs))
    html = _build_html(jobs, digest_id)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = DIGEST_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, DIGEST_RECIPIENT, msg.as_string())

    return subject


def send_no_results(new_listings: int, analyzed: int, review_threshold: int) -> None:
    """
    Send a short notification when the daily run finds nothing worth surfacing.
    Always fires so you know the agent ran — even on quiet days.
    """
    if not GMAIL_APP_PASSWORD:
        return

    today = date.today().isoformat()
    subject = f"Job Agent — No matches today ({today})"

    if new_listings == 0:
        reason = "No new listings were found on any job board today."
        detail = "All jobs seen previously were already in the database."
    else:
        reason = (
            f"Found <strong>{new_listings}</strong> new listing(s), "
            f"but none scored above your review threshold of <strong>{review_threshold}</strong>."
        )
        detail = (
            f"{analyzed} job(s) were analyzed. "
            "They may have been filtered by location, keywords, or relevance score."
        )

    html = f"""
    <html>
    <body style="font-family:sans-serif;color:#1a1a1a;max-width:560px;margin:auto;padding:16px;">
      <h3 style="color:#6b7280;">Job Agent — No Matches &mdash; {today}</h3>
      <p>{reason}</p>
      <p style="color:#6b7280;font-size:0.9em;">{detail}</p>
      <p style="color:#9ca3af;font-size:0.78em;margin-top:20px;">
        The agent runs daily at 7 AM EAT. Next check tomorrow.
      </p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = DIGEST_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, DIGEST_RECIPIENT, msg.as_string())


def send_application_confirmation(job: dict[str, Any], digest_id: int, digest_subject: str) -> None:
    """
    Send a reply-style confirmation email after a successful application.
    Threads under the original digest email so it stays in context.
    """
    if not GMAIL_APP_PASSWORD:
        return

    subject = f"Re: {digest_subject}"
    html = f"""
    <html><body style="font-family:sans-serif;color:#1a1a1a;max-width:600px;margin:auto;padding:16px;">
      <h3 style="color:#16a34a;">Application Submitted</h3>
      <p>Your application was automatically submitted for the following role:</p>
      <table style="border-collapse:collapse;width:100%;font-size:0.9em;">
        <tr><td style="padding:6px;color:#555;width:120px;">Role</td>
            <td style="padding:6px;font-weight:bold;">{job["title"]}</td></tr>
        <tr style="background:#f9fafb;"><td style="padding:6px;color:#555;">Company</td>
            <td style="padding:6px;">{job["company"]}</td></tr>
        <tr><td style="padding:6px;color:#555;">Location</td>
            <td style="padding:6px;">{job.get("location", "—")}</td></tr>
        <tr style="background:#f9fafb;"><td style="padding:6px;color:#555;">Apply URL</td>
            <td style="padding:6px;font-size:0.85em;">
              <a href="{job["job_url"]}">{job["job_url"][:80]}</a></td></tr>
      </table>
      <p style="color:#555;font-size:0.85em;margin-top:16px;">
        A tailored cover letter was submitted. Check the portal to confirm receipt
        and complete any additional steps required by the employer.
      </p>
      <p style="color:#9ca3af;font-size:0.78em;">Job Agent — Digest #{digest_id}</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = DIGEST_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, DIGEST_RECIPIENT, msg.as_string())
