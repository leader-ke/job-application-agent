"""
Check Gmail inbox for user replies approving jobs from a digest.

Reply format (anywhere in the body, case-insensitive):
    APPLY: 1, 3, 5
    APPLY: 2

Connects via IMAP SSL to Gmail. Requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env.
Enable IMAP at: Gmail → Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
from typing import Any

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "kenisiaho@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DIGEST_SUBJECT_MARKER = "Job Agent Digest #"


def _extract_approved_nums(text: str) -> list[int]:
    """Parse 'APPLY: 1, 3, 5' from email body. Returns list of job numbers."""
    match = re.search(r"APPLY\s*:\s*([\d\s,]+)", text, re.IGNORECASE)
    if not match:
        return []
    return [
        int(n.strip())
        for n in re.split(r"[,\s]+", match.group(1))
        if n.strip().isdigit()
    ]


def _extract_digest_id(subject: str) -> int | None:
    """Parse digest ID from subject like 'Re: Job Agent Digest #3 — 2026-04-12 ...'"""
    match = re.search(r"Digest #(\d+)", subject, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _get_text_body(msg: email.message.Message) -> str:
    """Extract the plain-text body. Falls back to HTML if no plain part."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(errors="replace")
    return ""


def check_for_approvals() -> list[dict[str, Any]]:
    """
    Scans unread Gmail messages whose subject contains 'Job Agent Digest #'.
    Returns list of {"digest_id": int, "approved_nums": [int]} for each reply
    that contains an APPLY command. Marks matched emails as read.
    """
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD is not set in .env. "
            "Generate a Gmail App Password and add it."
        )

    results: list[dict[str, Any]] = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        mail.select("inbox")

        # Search for unread messages referencing our digest subjects
        _, data = mail.search(None, f'(UNSEEN SUBJECT "{DIGEST_SUBJECT_MARKER}")')
        ids = data[0].split() if data[0] else []

        for uid in ids:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = msg.get("Subject", "")
            body = _get_text_body(msg)

            digest_id = _extract_digest_id(subject)
            approved_nums = _extract_approved_nums(body)

            if digest_id is not None and approved_nums:
                results.append({"digest_id": digest_id, "approved_nums": approved_nums})
                mail.store(uid, "+FLAGS", "\\Seen")  # mark as read

        mail.logout()

    except imaplib.IMAP4.error as exc:
        print(f"[reply_checker] IMAP authentication error: {exc}")
        print(
            "  Ensure IMAP is enabled in Gmail settings and GMAIL_APP_PASSWORD is correct."
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[reply_checker] Unexpected error: {exc}")

    return results
