from __future__ import annotations

import re
from typing import Optional

from src.models import Job, RoleKind
from src.settings import load_yaml

PAY_ANNUAL = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?(?:\s*(?:-|–|to)\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?)?\s*(?:usd)?\s*(?:/?\s*(?:year|yr|annual))?",
    re.I,
)
PAY_HOURLY = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s*)?h(?:ou)?r",
    re.I,
)
PAY_MONTHLY = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?\s*(?:/|per\s*)?mo",
    re.I,
)

# Conservative US new-grad / intern averages used only when the posting has no pay.
FT_COMPANY_AVERAGES = {
    "google": 140000,
    "meta": 155000,
    "facebook": 155000,
    "amazon": 130000,
    "microsoft": 135000,
    "apple": 145000,
    "netflix": 180000,
    "nvidia": 150000,
    "uber": 140000,
    "lyft": 130000,
    "airbnb": 150000,
    "stripe": 160000,
    "snowflake": 145000,
    "databricks": 155000,
    "oracle": 115000,
    "ibm": 110000,
    "intel": 120000,
    "cisco": 120000,
    "salesforce": 135000,
    "adobe": 130000,
    "bloomberg": 145000,
    "jpmorgan": 120000,
    "goldman": 125000,
    "capital one": 115000,
}
INTERN_HOURLY_AVERAGES = {
    "google": 60,
    "meta": 62,
    "amazon": 70,
    "microsoft": 60,
    "apple": 65,
    "netflix": 70,
    "nvidia": 60,
    "stripe": 65,
    "databricks": 65,
    "uber": 58,
    "bloomberg": 60,
}

FT_ROLE_BONUS = [
    (re.compile(r"staff|principal", re.I), 40000),
    (re.compile(r"senior", re.I), 25000),
    (re.compile(r"new\s*grad|university|early career|junior", re.I), 0),
    (re.compile(r"intern", re.I), 0),
    (re.compile(r"software|swe|sde|engineer", re.I), 0),
]

DEFAULT_FT_AVERAGE = 118000
DEFAULT_INTERN_HOURLY = 48


def _num(raw: str, k: str | None) -> float:
    n = float(raw.replace(",", ""))
    if k:
        n *= 1000
    return n


def parse_posted_pay(text: str) -> tuple[Optional[float], Optional[float]]:
    """Return (annual_low, hourly) from posting text."""
    if not text:
        return None, None
    hm = PAY_HOURLY.search(text)
    hourly = float(hm.group(1).replace(",", "")) if hm else None
    mm = PAY_MONTHLY.search(text)
    annual = None
    if mm:
        monthly = _num(mm.group(1), mm.group(2))
        annual = monthly * 12
    am = PAY_ANNUAL.search(text)
    if am:
        low = _num(am.group(1), am.group(2))
        # $45/hr can also match the annual regex first number; prefer explicit hourly.
        if hourly and low <= 200:
            pass
        elif low >= 1000:
            annual = low
        elif low <= 300 and (am.group(2) or "").lower() == "k":
            annual = low
        elif 80 <= low <= 400:
            annual = low * (1000 if low < 1000 else 1)
    return annual, hourly


def estimate_average_pay(job: Job, hours_per_week: int = 40) -> tuple[Optional[float], Optional[float]]:
    key = job.company.lower()
    matched_company = next((k for k in FT_COMPANY_AVERAGES if k in key), None)
    if job.kind == RoleKind.FULL_TIME:
        base = FT_COMPANY_AVERAGES.get(matched_company, DEFAULT_FT_AVERAGE) if matched_company else DEFAULT_FT_AVERAGE
        for rx, bonus in FT_ROLE_BONUS:
            if rx.search(job.title):
                base += bonus
                break
        return float(base), base / (hours_per_week * 52)
    intern_hourly = (
        INTERN_HOURLY_AVERAGES.get(matched_company, DEFAULT_INTERN_HOURLY)
        if matched_company
        else DEFAULT_INTERN_HOURLY
    )
    for k, v in INTERN_HOURLY_AVERAGES.items():
        if k in key:
            intern_hourly = v
            break
    return intern_hourly * hours_per_week * 52, float(intern_hourly)


def fill_pay(job: Job) -> Job:
    cfg = load_yaml("config/filters.yaml")
    hours = int(cfg.get("internship", {}).get("assume_hours_per_week") or cfg.get("salary_defaults", {}).get("hours_per_week") or 40)
    annual, hourly = parse_posted_pay(job.salary_text)
    if annual is None and hourly is None:
        annual, hourly = estimate_average_pay(job, hours)
        job.estimated_pay = True
    if hourly is None and annual is not None:
        hourly = annual / (hours * 52)
    if annual is None and hourly is not None:
        annual = hourly * hours * 52
    job.annual_low_usd = annual
    job.hourly_usd = hourly
    return job
