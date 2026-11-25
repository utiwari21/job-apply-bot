from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, FeatureNotFound

from src.models import Job, RoleKind

US_HINTS = re.compile(
    r"\b(united states|\busa\b|\bu\.s\.a?\b|\bremote[,\s]+us\b|"
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|"
    r"louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|"
    r"missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
    r"new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|"
    r"rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|"
    r"virginia|washington|west virginia|wisconsin|wyoming|"
    r"\bny\b|\bca\b|\bwa\b|\btx\b|\bma\b|\bil\b|\bga\b|\bnc\b|\bco\b)\b",
    re.I,
)
NON_US_ONLY = re.compile(
    r"\b(canada|united kingdom|\buk\b|india|germany|ireland|netherlands|"
    r"australia|singapore|remote worldwide|anywhere in the world)\b",
    re.I,
)
KEYWORD_RE = re.compile(
    r"\b(?:Python|Java|JavaScript|TypeScript|C\+\+|C#|Go|Rust|SQL|NoSQL|AWS|Azure|GCP|"
    r"Docker|Kubernetes|React|Angular|Django|Flask|Spring|Terraform|Git|Linux|"
    r"machine learning|deep learning|artificial intelligence|data science|data analytics|"
    r"software engineering|distributed systems|REST|GraphQL|CI/CD|Selenium|Playwright)\b",
    re.I,
)
RELO = re.compile(r"relocati", re.I)
HOUSING = re.compile(r"hous(e|ing)|stipend.*room|paid (apartment|housing)", re.I)
JOB_HOSTS = (
    "greenhouse.io",
    "boards.greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "smartrecruiters.com",
    "job-boards.greenhouse.io",
    "simplify.jobs",
    "linkedin.com",
)


def _kind_from_email(email_kind: str, title: str) -> RoleKind:
    if email_kind == "internship" or re.search(r"intern", title, re.I):
        return RoleKind.INTERNSHIP
    return RoleKind.FULL_TIME


def _us_flag(text: str) -> bool | None:
    if NON_US_ONLY.search(text) and not US_HINTS.search(text):
        return False
    # Digest cards often omit location. Treat an ambiguous listing as US by default;
    # explicit non-US locations remain excluded.
    return True


def _keywords(text: str) -> tuple[str, ...]:
    found: dict[str, str] = {}
    for match in KEYWORD_RE.finditer(text):
        value = match.group(0)
        found.setdefault(value.lower(), value)
    return tuple(found.values())


def parse_jobs_from_html(html: str, email_kind: str) -> list[Job]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    repo_footer = re.compile(r"summer2026-internships|summer2026-jobs|github\.com/.*/(summer2026|new-grad-positions)", re.I)
    swelist_domain = re.compile(r"swelist\.com|simplify\.jobs/copilot|unsubscrib", re.I)

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = " ".join(a.get_text(" ", strip=True).split())
        lower_href = href.lower()
        lower_label = label.lower()

        if "github.com" in lower_href and repo_footer.search(lower_href):
            break
        if "see more details by visiting the repo" in lower_label or "summer2026-internships" in lower_label:
            break
        if "simplify.jobs/copilot" in lower_href or "link to simplify" in lower_label:
            continue
        if "swelist.com" in lower_href or "swelist" in lower_label:
            continue
        if swelist_domain.search(lower_href) or swelist_domain.search(lower_label):
            continue
        if "unsubscribe" in lower_href or "mailto:" in lower_href:
            continue
        if not href.startswith("http"):
            continue

        host = urlparse(href).netloc.lower()
        if not any(h in host for h in JOB_HOSTS):
            if len(label) < 6:
                continue
            parent_text = a.parent.get_text(" ", strip=True) if a.parent else label
            if not re.search(r"job|career|greenhouse|lever|ashby|workday|intern|engineer", lower_href + " " + parent_text, re.I):
                continue

        if href in seen:
            continue
        seen.add(href)

        block = a.parent.get_text(" ", strip=True) if a.parent else label
        if not label or label.lower() in {"unsubscribe", "view all", "click here"}:
            continue

        company = ""
        if block and label in block and block.rfind(label) > 0:
            prefix = block[: block.rfind(label)].strip().rstrip(":")
            if prefix and len(prefix) < 80:
                company = prefix.strip().rstrip(":")

        if not company:
            # Common pattern: Title at Company or Company — Title
            m = re.search(r"(.+?)\s+(?:at|@|—|-|–)\s+(.+)", label)
            if m:
                title, company = m.group(1).strip(), m.group(2).strip()
            else:
                title = label
        else:
            title = label

        kind = _kind_from_email(email_kind, title)
        loc_match = re.search(
            r"(Remote[^|,]*|[A-Z][a-zA-Z]+(?:,\s*[A-Z]{2})?)",
            block,
        )
        location = loc_match.group(1) if loc_match else ""
        jobs.append(
            Job(
                company=company or host,
                title=title,
                url=href,
                kind=kind,
                location=location,
                salary_text=block,
                pays_relocation=bool(RELO.search(block)),
                pays_housing=bool(HOUSING.search(block)),
                in_united_states=_us_flag(block),
                keywords=_keywords(f"{title} {block}"),
            )
        )
    return jobs
