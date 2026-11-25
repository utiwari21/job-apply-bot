"""Playwright application flow through Simplify and the employer page."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path

from src.models import ROOT, ApplyResult, Job, RoleKind
from src.settings import load_yaml

SHORT_ANSWER = re.compile(
    r"why do you want|cover letter|tell us about|describe a time|"
    r"what interests you|short answer|essay|motivation",
    re.I,
)
NON_US_PAGE = re.compile(
    r"\b(?:canada|toronto|vancouver|montreal|united kingdom|uk|london|india|"
    r"germany|ireland|netherlands|australia|singapore|remote worldwide|"
    r"anywhere in the world)\b",
    re.I,
)
US_PAGE = re.compile(
    r"\b(?:united states|usa|u\.s\.?|new york|california|texas|washington|"
    r"massachusetts|illinois|pennsylvania|virginia|colorado|georgia|ohio|"
    r"north carolina|remote\s*,?\s*us)\b",
    re.I,
)

_shared_playwright = None
_shared_context = None
_shared_browser = None
_cdp_endpoint = None


def configure_cdp(endpoint: str | None) -> None:
    global _cdp_endpoint
    _cdp_endpoint = endpoint or _discover_cdp_endpoint()


def _discover_cdp_endpoint() -> str | None:
    for port in (9222, 9223, 9224, 9515):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.5) as response:
                if response.status == 200:
                    endpoint = f"http://127.0.0.1:{port}"
                    print(f"Attaching to existing Chrome CDP session: {endpoint}")
                    return endpoint
        except (OSError, urllib.error.URLError):
            continue
    return None


def _browser_for_job(leave_open: bool, sync_playwright):
    global _shared_playwright, _shared_context, _shared_browser
    if not leave_open:
        playwright = sync_playwright().start()
        context = playwright.chromium.launch(headless=True).new_context()
        return playwright, context, True
    if _shared_context is None:
        _shared_playwright = sync_playwright().start()
        if _cdp_endpoint:
            _shared_browser = _shared_playwright.chromium.connect_over_cdp(_cdp_endpoint)
            _shared_context = _shared_browser.contexts[0]
        else:
            profile_dir = str(ROOT / ".playwright-simplify-profile")
            _shared_context = _shared_playwright.chromium.launch_persistent_context(
                profile_dir,
                headless=False,
            )
    return _shared_playwright, _shared_context, False


def wait_for_open_applications() -> None:
    global _shared_playwright, _shared_context
    if _shared_context is not None:
        input("Blocked application tabs are open. Finish them manually, then press Enter to exit. ")
        if _shared_browser is None:
            _shared_context.close()
        _shared_playwright.stop()
        _shared_context = None
        _shared_playwright = None
        _shared_browser = None


def _required_short_answers(page) -> list[str]:
    found: list[str] = []
    locators = page.locator("label, p, span, div, legend").all()[:400]
    for loc in locators:
        try:
            text = loc.inner_text(timeout=100).strip()
        except Exception:
            continue
        if not text or len(text) > 240:
            continue
        if SHORT_ANSWER.search(text) and (
            "*" in text or "required" in text.lower() or loc.get_attribute("aria-required") == "true"
        ):
            found.append(text)
    # Required textareas that are not email/phone
    for ta in page.locator("textarea[required], textarea[aria-required='true']").all()[:20]:
        try:
            found.append(ta.get_attribute("name") or "textarea")
        except Exception:
            found.append("textarea")
    # Dedup
    uniq: list[str] = []
    for item in found:
        if item not in uniq:
            uniq.append(item)
    return uniq


def _graduation_for(job: Job, profile: dict) -> str:
    if job.kind == RoleKind.INTERNSHIP:
        return profile.get("graduation_date_internship") or profile.get("graduation_date") or ""
    return profile.get("graduation_date_full_time") or profile.get("graduation_date") or ""


def _fill_profile(page, profile: dict, job: Job) -> None:
    pairs = {
        "first": profile.get("full_name", "").split(" ")[0],
        "last": profile.get("full_name", "").split(" ")[-1],
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "location": profile.get("location", ""),
        "graduat": _graduation_for(job, profile),
    }
    for key, value in pairs.items():
        if not value:
            continue
        for sel in (
            f"input[name*='{key}' i]",
            f"input[autocomplete*='{key}' i]",
            f"input[placeholder*='{key}' i]",
        ):
            box = page.locator(sel).first
            if box.count():
                try:
                    box.fill(value, timeout=800)
                except Exception:
                    pass


def _upload_resume(page, pdf: Path) -> None:
    inputs = page.locator("input[type='file']")
    n = inputs.count()
    for i in range(n):
        try:
            inputs.nth(i).set_input_files(str(pdf), timeout=2000)
        except Exception:
            continue


def _visible_button(page, pattern):
    buttons = page.get_by_role("button", name=pattern).all()
    for button in buttons:
        try:
            if button.is_visible() and button.is_enabled():
                return button
        except Exception:
            continue
    return None


def _page_requires_simplify_login(page) -> bool:
    url = (page.url or "").lower()
    if any(marker in url for marker in ("/login", "/signin", "auth.simplify")):
        return True
    text = _page_body_text(page).lower()
    return "log in to simplify" in text or "sign in to simplify" in text


def _simplify_login_blockers(page) -> list[str]:
    blockers = []
    if page.locator("iframe[src*='recaptcha'], [data-sitekey]").count():
        blockers.append("invisible reCAPTCHA")
    if page.locator("input[name='email'], input[type='email']").count() == 0:
        blockers.append("email field unavailable")
    if page.locator("input[type='password']").count() == 0:
        blockers.append("password field unavailable")
    return blockers


def _open_employer_page(page):
    apply_button = _visible_button(page, re.compile(r"^apply(?: now| for this job)?$", re.I))
    if apply_button is None:
        return None

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        with page.expect_popup(timeout=3000) as popup_info:
            apply_button.click(timeout=5000)
        employer_page = popup_info.value
        try:
            employer_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            print(f"  employer page still loading; continuing: {employer_page.url}")
        employer_page.wait_for_timeout(1000)
        return employer_page
    except PlaywrightTimeoutError:
        try:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                print(f"  employer page still loading; continuing: {page.url}")
            page.wait_for_timeout(1000)
        except Exception:
            pass
        return page
    except Exception:
        return None


def _page_is_inactive(page) -> bool:
    inactive_text = (
        "inactive",
        "job closed",
        "position closed",
        "this role is no longer accepting applications",
        "this job is no longer active",
        "application is no longer active",
        "not accepting applications",
        "expired",
    )
    try:
        text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in inactive_text)


def _page_is_explicitly_non_us(text: str) -> bool:
    return bool(NON_US_PAGE.search(text) and not US_PAGE.search(text))


def _page_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=1500)
    except Exception:
        return ""


def apply_to_job(job: Job, pdf: Path, dry_run: bool = False, leave_open: bool = False) -> ApplyResult:
    profile = load_yaml("config/profile.yaml")
    from playwright.sync_api import sync_playwright

    p, browser, owns_browser = _browser_for_job(leave_open, sync_playwright)
    page = browser.new_page()
    try:
        page.goto(job.url, wait_until="commit", timeout=15000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            print(f"  page still loading; continuing with available content: {job.url}")
        page.wait_for_timeout(500)

        if _page_is_inactive(page):
            page.close()
            return ApplyResult(False, True, "inactive")

        employer_page = _open_employer_page(page)
        if employer_page is None:
            if not leave_open:
                page.close()
            return ApplyResult(False, True, "no_apply_button")
        if _page_requires_simplify_login(employer_page):
            if not leave_open:
                employer_page.close()
                return ApplyResult(False, True, "simplify_login_required")
            blockers = _simplify_login_blockers(employer_page)
            suffix = f" ({', '.join(blockers)})" if blockers else ""
            print(f"  Simplify login required for {job.company} | {job.title}{suffix}.")
            print("  Complete the login in this tab. The bot will not click, reload, or fill this page.")
            try:
                employer_page.wait_for_url(
                    re.compile(r"^https://simplify\.jobs/(?!auth/login|auth/signin)"),
                    timeout=300000,
                )
            except Exception:
                return ApplyResult(False, True, "simplify_login_timeout")
            employer_page.wait_for_timeout(1000)
            if "simplify.jobs" in employer_page.url:
                employer_page = _open_employer_page(employer_page)
                if employer_page is None:
                    return ApplyResult(False, True, "no_apply_button_after_login")
        if employer_page is not page:
            page.close()
        page = employer_page

        if _page_is_inactive(page):
            page.close()
            return ApplyResult(False, True, "inactive")

        if _page_is_explicitly_non_us(_page_body_text(page)):
            page.close()
            return ApplyResult(False, True, "not_united_states")

        shorts = _required_short_answers(page)
        if shorts:
            _fill_profile(page, profile, job)
            _upload_resume(page, pdf)
            if not leave_open:
                page.close()
            return ApplyResult(
                submitted=False,
                skipped=True,
                reason="required_short_answer",
                required_short_answers=shorts,
            )

        _fill_profile(page, profile, job)
        _upload_resume(page, pdf)

        if dry_run:
            page.close()
            return ApplyResult(False, True, "dry_run")

        submit = _visible_button(page, re.compile(r"^(submit|submit application|send application)$", re.I))
        if submit is None:
            if not leave_open:
                page.close()
            return ApplyResult(False, True, "no_submit_button")
        try:
            submit.click(timeout=5000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            if not leave_open:
                page.close()
            return ApplyResult(False, True, f"submit_failed:{exc}")
        page.close()
        return ApplyResult(True, False, "submitted")
    except Exception as exc:
        page.close()
        return ApplyResult(False, True, f"application_failed:{exc}")
    finally:
        if owns_browser:
            browser.close()
            p.stop()
