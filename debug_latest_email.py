from __future__ import annotations

import email
import imaplib
import re
import socket
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from src.email_parser import parse_jobs_from_html
from src.gmail_imap import APPLYING_NEEDED_LABEL, SUBJECT_RE, _decode, _is_current_year_or_later, _message_datetime_est, classify_subject, html_body
from src.settings import gmail_address, gmail_app_password


def _decode(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _is_primary(msg: email.message.Message) -> bool:
    labels = " ".join(msg.get_all("X-Gmail-Labels", []) + msg.get_all("X-GM-LABELS", []))
    if not labels:
        return True
    lowered = labels.lower()
    if "category promotions" in lowered or "category social" in lowered:
        return False
    if "category updates" in lowered or "category forums" in lowered:
        return False
    return True


def _message_datetime_est(msg: email.message.Message) -> datetime:
    raw = msg.get("Date")
    if not raw:
        return datetime.min.replace(tzinfo=ZoneInfo("America/New_York"))
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return datetime.min.replace(tzinfo=ZoneInfo("America/New_York"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("America/New_York"))


def connect_imap() -> imaplib.IMAP4_SSL:
    user = gmail_address()
    password = gmail_app_password()
    if not user or not password:
        raise RuntimeError("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env before running this debug script.")
    client = imaplib.IMAP4_SSL("imap.gmail.com")
    client.socket().settimeout(20)
    client.login(user, password)
    return client


def latest_labeled_digest_email(kind: str) -> None:
    client = connect_imap()
    try:
        client.select('"[Gmail]/All Mail"')
        status, data = client.search(None, "X-GM-LABELS", f'"{APPLYING_NEEDED_LABEL}"')
        if status != "OK":
            print(f"IMAP search failed for label {APPLYING_NEEDED_LABEL!r}.")
            return

        ids = data[0].split()
        if not ids:
            print(f"No emails found under label: {APPLYING_NEEDED_LABEL}")
            return

        matches: list[tuple[datetime, bytes, email.message.Message]] = []
        for msg_id in ids:
            try:
                status, fetched = client.fetch(msg_id, "(RFC822)")
            except (socket.timeout, OSError, imaplib.IMAP4.abort, imaplib.IMAP4.error) as exc:
                print(f"IMAP fetch timeout/failed for {msg_id!r}: {exc}")
                continue
            if status != "OK" or not fetched or not fetched[0]:
                continue

            raw = fetched[0][1]
            msg = email.message_from_bytes(raw)
            subject = _decode(msg.get("Subject"))
            if not SUBJECT_RE.search(subject):
                continue
            if not _is_current_year_or_later(msg):
                continue
            if classify_subject(subject) != kind:
                continue
            matches.append((_message_datetime_est(msg), msg_id, msg))

        if not matches:
            print(f"No {kind} digest emails found in label: {APPLYING_NEEDED_LABEL}")
            return

        _, msg_id, msg = max(matches, key=lambda item: item[0])
        html = html_body(msg)
        jobs = parse_jobs_from_html(html, kind)

        print("\n" + "=" * 88)
        print(f"LATEST {kind.upper()} DIGEST")
        print("=" * 88)
        print(f"MSG_ID: {msg_id!r}")
        print(f"SUBJECT: {_decode(msg.get('Subject'))}")
        print(f"DATE_EST: {_message_datetime_est(msg).isoformat()}")
        print(f"LISTINGS: {len(jobs)}")
        print("=" * 88)
        for idx, job in enumerate(jobs[:20], 1):
            print(f"{idx}. Company: {job.company}")
            print(f"   Role: {job.title}")
            print(f"   Link: {job.url}")
        print("=" * 88)
    finally:
        try:
            client.logout()
        except Exception:
            pass


if __name__ == "__main__":
    latest_labeled_digest_email("full_time")
    latest_labeled_digest_email("internship")
