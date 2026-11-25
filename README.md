# job-apply-bot

An agentic pipeline that reads job-posting digest emails, filters them against
configurable criteria, tailors a LaTeX resume per listing, compiles it, and
drives a browser to submit the application.

Python · Playwright · Gemini · pytest

## Why it exists

Applying to a few hundred postings by hand is mostly mechanical: read the
posting, decide whether it is worth the time, rewrite the same experience in
the language the posting uses, compile, upload, fill the form. The judgment
calls are worth keeping. The rest is not.

The interesting part of building it was not the automation. It was deciding
where the model is allowed to act and where it is not.

## Architecture

```
Gmail (IMAP, unread digests)
  → parse listings out of the email HTML
  → filter against config/filters.yaml
  → tailor a LaTeX resume from a template (Gemini)
  → compile to PDF (latexmk / pdflatex)
  → Playwright fills and submits the form
  → append the outcome to a run log
```

One unread digest at a time, listings in order, email marked read once
processed. No application database.

## Design decisions

**The model is constrained to emit a compilable artifact and nothing else.**
Asked for a tailored resume, a language model will happily wrap its output in a
markdown code fence. That fence breaks the LaTeX build, and it breaks it
silently: `pdflatex` fails, the previous PDF is still on disk, and the pipeline
submits a stale file. The prompt forbids anything outside the `.tex` body, and
the compile step is checked rather than assumed.

**The agent will not submit free-text fields.** It fills dropdowns, uploads
files, and completes structured inputs. It stops at anything requiring a claim
about me, because the model has no way to verify whether such a claim is true
and I am the one accountable for it. Short answers get drafted from the resume
for review; they never get submitted automatically.

**A dry-run mode exercises the whole path without touching a live form**, so a
changed selector or a changed dependency surfaces in a test rather than in a
submission.

## What the run log caught

The pipeline logs every decision as JSONL: timestamp, company, title, URL,
whether it submitted, and why not if it did not.

One run logged 1,316 decisions. 1,271 of them — 96.6% — were skipped with the
reason `below_57_hourly`. The filter was working exactly as written. The
problem was that nothing in the pipeline could tell me a single threshold was
rejecting almost everything: no exception was raised, no run failed, and every
reason field was populated neatly. It was visible only by aggregating outcomes
rather than reading them.

That is the failure mode this project actually taught me about. Code that
breaks announces itself. Code that is quietly wrong does not.

## Setup

Requires Python 3.11+, and `latexmk` or `pdflatex` on PATH.

```bash
git clone https://github.com/utiwari21/job-apply-bot.git
cd job-apply-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Then edit `.env`, `config/profile.yaml`, and the resume template.

```bash
python -m src.runner --dry-run   # no submissions
python -m src.runner
```

## Gmail credentials

IMAP with an App Password. No Google Cloud project, no OAuth client, no
service-account JSON.

1. Gmail → Settings → Forwarding and POP/IMAP → enable IMAP.
2. [Google Account security](https://myaccount.google.com/security) → enable
   2-Step Verification.
3. [App passwords](https://myaccount.google.com/apppasswords) → create one.
   Google shows the 16-character value once.
4. Set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env`.

A normal account password will be rejected by IMAP.

SMTP is not used for reading mail — it only sends. It is optional here, for
notifying yourself after a run.

## Model

Defaults to `gemini-2.5-flash` via `GEMINI_API_KEY`. Leave the key empty to
skip tailoring and submit the template unchanged. Billed per token.

## Configuration

`config/filters.yaml` holds the filter criteria — pay floors, location
requirement, assumed hours for postings with no stated pay.
`config/profile.yaml` holds the details that go on application forms.

## Tests

```bash
pytest -q
```

Covers filter logic, profile loading, and resume generation.
