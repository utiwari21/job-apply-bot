from src.apply import _graduation_for
from src.models import Job, RoleKind
from src.settings import load_yaml


def test_graduation_dates_split_intern_vs_ft():
    profile = load_yaml("config/profile.yaml")
    intern = Job("Co", "Intern", "https://x", RoleKind.INTERNSHIP)
    ft = Job("Co", "SWE", "https://x", RoleKind.FULL_TIME)
    assert _graduation_for(intern, profile) == "December 2027"
    assert _graduation_for(ft, profile) == "May 2027"
