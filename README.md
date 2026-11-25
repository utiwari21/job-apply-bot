# Job apply bot

Gmail digest emails (`👀 {X} New Jobs Posted Today` / `👀 {X} New Internships Posted Today`) → filter → tailor LaTeX → PDF → apply.

## SMTP vs Google Cloud

**SMTP cannot read your inbox.** It only sends mail.

You do **not** need a Google Cloud OAuth app. Use:

1. **IMAP** (this bot) to read unread Primary inbox mail — Gmail App Password
2. **SMTP** (optional) only if you want a notification sent to yourself after each listing

## Gmail credentials (no Google Cloud)

You need an **App Password**, not OAuth client IDs.

1. In Gmail: gear → **See all settings** → **Forwarding and POP/IMAP** → enable **IMAP** → Save.
2. Open [Google Account security](https://myaccount.google.com/security).
3. Turn on **2-Step Verification** if it is off.
4. Open [App passwords](https://myaccount.google.com/apppasswords) (or Security → 2-Step Verification → App passwords).
5. Create one named `job-apply-bot`. Google shows a 16-character password once.
6. Copy `.env.example` to `.env` and set:
   - `GMAIL_ADDRESS` — the inbox that receives the digest emails
   - `GMAIL_APP_PASSWORD` — that 16-character value (spaces optional)

Your normal Gmail password will be rejected by IMAP. Do not put a Google Cloud JSON key in this project.

## Resumes (project root)

| Kind | Working files (overwritten per listing) | Template (never submitted) |
|---|---|---|
| Full-time | `Utkarsh_Tiwari_Software_Engineer.tex` + `.pdf` | `Utkarsh_Tiwari_Software_Engineer.base.tex` |
| Internship | `Utkarsh_Tiwari_Software_Engineering_Intern.tex` + `.pdf` | `Utkarsh_Tiwari_Software_Engineering_Intern.base.tex` |

Each listing: delete the previous working `.tex`/`.pdf` for that kind, tailor from the `.base.tex`, save the same names, compile PDF, then apply.

The OpenAI **API is not free** (a ChatGPT Plus subscription does not include API credits). Leave `OPENAI_API_KEY` empty to skip the model. If you set a key, the model is instructed to return **a full `.tex` file only** (no markdown). `gpt-4o-mini` is cheap but billed per token.

## Rules

- Full-time: United States only, base **≥ $110,000**. Missing pay → company/role average, then still enforce $110k.
- Internships: **≥ $57/hour**. Missing hours → **40 hours/week**. Relocation/housing increase rank only.
- Required short-answer fields: answers can be drafted from the resume; **do not submit**.
- No application database. One unread digest at a time, listings in order, mark the email read after it is processed.

## Setup

```powershell
cd C:\Users\tiwar\projects\job-apply-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
# edit .env, config/profile.yaml, and the two .base.tex resumes
python -m src.runner --dry-run
python -m src.runner
```

Needs `latexmk` or `pdflatex` on PATH.

## Tests

```powershell
pytest -q
```
