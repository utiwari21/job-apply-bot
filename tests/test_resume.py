from pathlib import Path

from src.models import Job, RoleKind, ROOT
from src.resume import stems_for, _keyword_tailor, extract_latex


def test_resume_names():
    ft = Job("Co", "SWE", "https://x", RoleKind.FULL_TIME)
    intern = Job("Co", "Intern", "https://x", RoleKind.INTERNSHIP)
    assert stems_for(ft)[0] == "Utkarsh_Tiwari_Software_Engineer"
    assert stems_for(intern)[0] == "Utkarsh_Tiwari_Software_Engineering_Intern"
    assert (ROOT / f"{stems_for(ft)[0]}.base.tex").exists()
    assert (ROOT / f"{stems_for(intern)[0]}.base.tex").exists()


def test_keyword_tailor_keeps_jake_template():
    tex = (ROOT / "Utkarsh_Tiwari_Software_Engineer.base.tex").read_text(encoding="utf-8")
    out = _keyword_tailor(tex, Job("Nvidia", "New Grad SWE", "https://x", RoleKind.FULL_TIME, location="Santa Clara, CA"))
    assert r"\documentclass" in out
    assert r"\resumeItem" in out
    assert r"\end{document}" in out
    assert "Utkarsh Tiwari" in out


def test_extract_latex_strips_markdown_fences():
    raw = "Here you go:\n```latex\n\\documentclass{article}\\begin{document}x\\end{document}\n```\nThanks"
    out = extract_latex(raw)
    assert out.startswith("\\documentclass")
    assert "```" not in out
    assert "Thanks" not in out
