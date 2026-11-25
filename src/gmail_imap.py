"""Gmail access through IMAP.

Use IMAP + a Google App Password (no Google Cloud OAuth client required).
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Iterator
from zoneinfo import ZoneInfo

import socket

from src.settings import gmail_address, gmail_app_password

IMAP_HOST = "imap.gmail.com"
APPLYING_NEEDED_LABEL = "AApplying Needed"
BOT_APPLIED_LABEL = "Bot Applied"
SUBJECT_RE = re.compile(
    r"New (Internships|Jobs) Posted Today",
    re.IGNORECASE,
)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _is_primary(msg: email.message.Message) -> bool:
    # Gmail IMAP X-GM-LABELS includes category; Category Personal ~= Primary.
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


def _is_current_year_or_later(msg: email.message.Message) -> bool:
    dt = _message_datetime_est(msg)
    current_year = datetime.now(ZoneInfo("America/New_York")).year
    return dt.year >= current_year


def connect_imap() -> imaplib.IMAP4_SSL:
    user = gmail_address()
    password = gmail_app_password()
    if not user or not password:
        raise RuntimeError("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env (use a Gmail App Password).")
    client = imaplib.IMAP4_SSL(IMAP_HOST)
    client.socket().settimeout(20)
    client.login(user, password)
    return client


def iter_matching_unread(limit: int | None = None) -> Iterator[tuple[imaplib.IMAP4_SSL, bytes, email.message.Message]]:
    client = connect_imap()
    try:
        client.select('"[Gmail]/All Mail"')
        status, data = client.search(None, "X-GM-LABELS", f'"{APPLYING_NEEDED_LABEL}"')
        if status != "OK":
            print(f"Could not search Gmail label {APPLYING_NEEDED_LABEL!r}.")
            return
        ids = data[0].split()
        if not ids:
            print(f"No messages found under Gmail label: {APPLYING_NEEDED_LABEL}")
            return

        label_candidates: list[tuple[datetime, bytes, email.message.Message]] = []
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
            if not _is_current_year_or_later(msg):
                subject = _decode(msg.get("Subject"))
                est = _message_datetime_est(msg)
                print(f"Skip stale labeled message: {subject} | date_est={est.isoformat()}")
                continue
            subject = _decode(msg.get("Subject"))
            if not SUBJECT_RE.search(subject):
                print(f"Skip non-digest label message: {subject}")
                continue
            est = _message_datetime_est(msg)
            print(f"Labeled digest candidate: {subject} | date_est={est.isoformat()}")
            label_candidates.append((est, msg_id, msg))

        if not label_candidates:
            print(f"No matching digest emails found under label: {APPLYING_NEEDED_LABEL}")
            return

        ordered = sorted(label_candidates, key=lambda item: item[0])
        print(f"Selected digest order by EST date: {[msg_id.decode('ascii', 'ignore') for _, msg_id, _ in ordered]}")
        if limit is not None:
            ordered = ordered[:limit]
        for _, msg_id, msg in ordered:
            yield client, msg_id, msg
    finally:
        try:
            client.logout()
        except Exception:
            pass


def mark_seen(client, msg_id: bytes) -> None:
    client.store(msg_id, "+FLAGS", "\\Seen")


def move_message_to_label(client, msg_id: bytes, from_label: str, to_label: str) -> None:
    client.store(msg_id, "-X-GM-LABELS", f'"{from_label}"')
    client.store(msg_id, "+X-GM-LABELS", f'"{to_label}"')


def html_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def classify_subject(subject: str) -> str:
    if re.search(r"Internships Posted Today", subject, re.I):
        return "internship"
    return "full_time"


