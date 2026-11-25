from email.message import Message

from src.gmail_imap import SUBJECT_RE, _is_current_year_or_later, classify_subject
from src.email_parser import parse_jobs_from_html
from src.filters import decide
from src.gmail_imap import _message_datetime_est
from src.apply import _page_is_explicitly_non_us
from src.models import Job, RoleKind
from src.salary import fill_pay, parse_posted_pay


def test_subjects_match_digest_shape():
    intern = "👀 12 New Internships Posted Today"
    jobs = "👀 7 New Jobs Posted Today"
    assert SUBJECT_RE.search(intern)
    assert SUBJECT_RE.search(jobs)
    assert classify_subject(intern) == "internship"
    assert classify_subject(jobs) == "full_time"


def test_ft_missing_salary_uses_company_average_and_110k_floor():
    google = fill_pay(
        Job("Google", "Software Engineer, New Grad", "https://x", RoleKind.FULL_TIME, location="NY, US", in_united_states=True)
    )
    assert google.estimated_pay
    assert google.annual_low_usd >= 110000
    assert decide(google).apply

    unknown = fill_pay(
        Job(
            "TinyStartup",
            "Software Engineer",
            "https://x",
            RoleKind.FULL_TIME,
            location="NY, US",
            in_united_states=True,
        )
    )
    assert unknown.estimated_pay
    # Unknown-company SWE average is still gated at $110k.
    d = decide(unknown)
    if unknown.annual_low_usd < 110000:
        assert not d.apply
    else:
        assert d.apply


def test_ft_posted_below_110k_skipped():
    job = Job(
        "Acme",
        "Software Engineer",
        "https://x",
        RoleKind.FULL_TIME,
        location="Austin, TX",
        salary_text="$95,000 - $120,000 per year",
        in_united_states=True,
    )
    d = decide(job)
    assert not d.apply
    assert d.reason == "below_110k"


def test_intern_assumes_40_hours_when_only_weekly_or_monthly():
    job = Job(
        "Meta",
        "Software Engineering Intern",
        "https://x",
        RoleKind.INTERNSHIP,
        location="Menlo Park, CA",
        salary_text="$64/hr relocation housing",
        in_united_states=True,
        pays_relocation=True,
        pays_housing=True,
    )
    d = decide(job)
    assert d.apply
    assert d.rank > 64


def test_intern_monthly_uses_40_hour_weeks():
    job = Job(
        "LocalCo",
        "Software Engineering Intern",
        "https://x",
        RoleKind.INTERNSHIP,
        location="Boston, MA",
        salary_text="$8,000 per month",
        in_united_states=True,
    )
    d = decide(job)
    # 8000 * 12 / (40 * 52) ≈ $46.15/hr → skip
    assert not d.apply
    assert job.hourly_usd is not None
    assert job.hourly_usd < 57
    job = Job(
        "LocalCo",
        "Intern",
        "https://x",
        RoleKind.INTERNSHIP,
        location="Boston, MA",
        salary_text="$20/hr",
        in_united_states=True,
    )
    d = decide(job)
    assert not d.apply


def test_non_us_skipped():
    job = Job(
        "Shopify",
        "Software Engineer",
        "https://x",
        RoleKind.FULL_TIME,
        location="Toronto, Canada",
        salary_text="$150000 per year",
        in_united_states=False,
    )
    assert not decide(job).apply


def test_application_page_rejects_explicit_non_us_location():
    assert _page_is_explicitly_non_us("Location: Toronto, Canada")
    assert not _page_is_explicitly_non_us("Location: New York, NY, United States")


def test_parse_digest_links():
    html = """
    <html><body>
      <a href="https://boards.greenhouse.io/foo/jobs/1">Software Engineer at Foo</a>
      <p>New York, NY $140,000</p>
      <a href="https://jobs.lever.co/bar/abc">Intern at Bar</a>
    </body></html>
    """
    jobs = parse_jobs_from_html(html, "full_time")
    assert len(jobs) >= 1
    assert any("greenhouse" in j.url for j in jobs)


def test_ambiguous_location_defaults_to_us_and_extracts_keywords():
    html = """
    <a href="https://boards.greenhouse.io/foo/jobs/2">Python Machine Learning Intern</a>
    <p>$65/hr. Qualifications: Python, AWS, Docker, and SQL.</p>
    """
    jobs = parse_jobs_from_html(html, "internship")
    assert jobs[0].in_united_states is True
    assert {"Python", "AWS", "Docker", "SQL"}.issubset(jobs[0].keywords)


def test_parse_swelist_digest_stops_before_repo_footer():
    html = """
    <html><body>
      <p>Hey Utkarsh! Here is your daily update (9/1) of tech internships from <a href="https://swelist.com/">swelist</a>:</p>
      <p><strong>TeleTracking:</strong> <a href="https://simplify.jobs/p/aaa">Software Engineer 1 - Logistics Engineering</a></p>
      <p><strong>Northrop Grumman:</strong> <a href="https://simplify.jobs/p/bbb">Associate Embedded Software Engineer - Pathways Program</a></p>
      <p>See more details by visiting the repo: <a href="https://github.com/SimplifyJobs/Summer2026-Internships">Summer2026-Internships</a></p>
    </body></html>
    """
    jobs = parse_jobs_from_html(html, "internship")
    assert len(jobs) == 2
    assert all(j.company in {"TeleTracking", "Northrop Grumman"} for j in jobs)
    assert all("simplify.jobs" in j.url for j in jobs)


def test_parse_posted_pay_prefers_hourly():
    annual, hourly = parse_posted_pay("Pay: $62/hr")
    assert hourly == 62


def test_message_date_is_compared_in_est():
    later = Message()
    later["Date"] = "Tue, 19 Sep 2026 00:30:00 -0400"
    earlier = Message()
    earlier["Date"] = "Mon, 18 Sep 2026 20:30:00 -0400"

    assert _message_datetime_est(later) > _message_datetime_est(earlier)


def test_messages_before_2026_are_ignored():
    old_msg = Message()
    old_msg["Date"] = "Mon, 15 Dec 2025 10:00:00 -0500"
    new_msg = Message()
    new_msg["Date"] = "Tue, 16 Sep 2026 07:00:00 -0400"

    assert not _is_current_year_or_later(old_msg)
    assert _is_current_year_or_later(new_msg)
