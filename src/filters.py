from __future__ import annotations

from src.models import FilterDecision, Job, RoleKind
from src.salary import fill_pay
from src.settings import load_yaml


def decide(job: Job) -> FilterDecision:
    cfg = load_yaml("config/filters.yaml")
    job = fill_pay(job)
    ft_min = float(cfg["full_time"]["min_base_usd"])
    intern_min = float(cfg["internship"]["min_hourly_usd"])

    if cfg["full_time"].get("require_united_states") and job.in_united_states is False:
        return FilterDecision(False, "not_united_states")
    if job.in_united_states is False:
        return FilterDecision(False, "not_united_states")
    # Unknown location: still require a US hint for FT; internships same rule.
    if job.in_united_states is not True:
        return FilterDecision(False, "location_not_confirmed_us")

    if job.kind == RoleKind.FULL_TIME:
        if job.annual_low_usd is None or job.annual_low_usd < ft_min:
            return FilterDecision(False, "below_110k")
        return FilterDecision(True, "ok", rank=job.annual_low_usd)

    if job.hourly_usd is None or job.hourly_usd < intern_min:
        return FilterDecision(False, "below_57_hourly")
    rank = job.hourly_usd
    if job.pays_relocation:
        rank += 10
    if job.pays_housing:
        rank += 10
    return FilterDecision(True, "ok", rank=rank)
