from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from email.header import decode_header, make_header

from src.apply import apply_to_job, configure_cdp, wait_for_open_applications
from src.email_parser import parse_jobs_from_html
from src.filters import decide
from src.gmail_imap import APPLYING_NEEDED_LABEL, BOT_APPLIED_LABEL, classify_subject, html_body, iter_matching_unread, mark_seen, move_message_to_label
from src.resume import tailor_and_pdf
from src.models import ROOT

RESULTS_PATH = ROOT / "application_results.jsonl"


def _subject(msg) -> str:
    return str(make_header(decode_header(msg.get("Subject") or "")))


def _record_result(job, result: dict) -> None:
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "company": job.company,
        "title": job.title,
        "url": job.url,
        **result,
    }
    with RESULTS_PATH.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=True) + "\n")


def process_once(dry_run: bool = False, leave_open: bool = False, limit: int | None = 1) -> None:
    for client, msg_id, msg in iter_matching_unread(limit=limit):
        subject = _subject(msg)
        matched_kind = classify_subject(subject)
        html = html_body(msg)
        jobs = parse_jobs_from_html(html, matched_kind)
        print(f"Email: {subject!r} -> {len(jobs)} listings")
        resume_by_kind = {}
        for job in jobs:
            decision = decide(job)
            if not decision.apply:
                print(f"  skip {job.company} | {job.title}: {decision.reason}")
                _record_result(job, {"submitted": False, "skipped": True, "reason": decision.reason})
                continue
            try:
                pdf = resume_by_kind.get(job.kind)
                if pdf is None:
                    pdf = tailor_and_pdf(job)
                    resume_by_kind[job.kind] = pdf
            except Exception as exc:
                print(f"  resume failed {job.title}: {exc}")
                _record_result(job, {"submitted": False, "skipped": True, "reason": f"resume_failed:{exc}"})
                continue
            result = apply_to_job(job, pdf, dry_run=dry_run, leave_open=leave_open)
            _record_result(
                job,
                {
                    "submitted": result.submitted,
                    "skipped": result.skipped,
                    "reason": result.reason,
                },
            )
            if result.reason.startswith("inactive") or result.reason == "no_submit_button":
                print(f"  inactive/invalid posting: {job.title} @ {job.company} ({result.reason})")
                continue
            print(f"  {job.title} @ {job.company}: {result.reason} submitted={result.submitted}")
            if result.submitted or result.skipped:
                continue
        mark_seen(client, msg_id)
        move_message_to_label(client, msg_id, APPLYING_NEEDED_LABEL, BOT_APPLIED_LABEL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply from Gmail job digests in the AApplying Needed label.")
    parser.add_argument("--dry-run", action="store_true", help="Parse, filter, tailor PDF; do not click Submit.")
    parser.add_argument("--leave-open", action="store_true", help="Keep blocked application pages open and continue to the next job.")
    parser.add_argument("--limit", type=int, default=1, help="Process at most this many digests; default is one, oldest first.")
    parser.add_argument("--connect-cdp", help="Attach to an existing Chrome started with --remote-debugging-port, e.g. http://127.0.0.1:9222.")
    args = parser.parse_args()
    configure_cdp(args.connect_cdp)
    process_once(dry_run=args.dry_run, leave_open=args.leave_open, limit=args.limit)
    if args.leave_open:
        wait_for_open_applications()


if __name__ == "__main__":
    main()
