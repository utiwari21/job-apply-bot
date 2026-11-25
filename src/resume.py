from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path

from src.models import INTERN_RESUME_STEM, FT_RESUME_STEM, ROOT, Job, RoleKind
from src.settings import gemini_api_key, gemini_model

FENCE = re.compile(r"```(?:latex|tex)?\s*([\s\S]*?)```", re.I)


def stems_for(job: Job) -> tuple[str, Path, Path]:
    stem = INTERN_RESUME_STEM if job.kind == RoleKind.INTERNSHIP else FT_RESUME_STEM
    base = ROOT / f"{stem}.base.tex"
    dest = ROOT / f"{stem}.tex"
    return stem, base, dest


def extract_latex(raw: str) -> str:
    """Keep only a compilable LaTeX document. Drop markdown/prose."""
    text = (raw or "").strip()
    fenced = FENCE.findall(text)
    if fenced:
        text = fenced[0].strip()
    start = text.find(r"\documentclass")
    end = text.rfind(r"\end{document}")
    if start == -1 or end == -1:
        return ""
    return text[start : end + len(r"\end{document}")].strip() + "\n"


def is_complete_tex(tex: str) -> bool:
    return bool(
        tex
        and r"\documentclass" in tex
        and r"\begin{document}" in tex
        and r"\end{document}" in tex
        and r"\resumeItem" in tex
    )


def _keyword_tailor(tex: str, job: Job) -> str:
    """No API: leave Jake-template structure intact; only annotate skills with the role keywords."""
    extra = []
    title = f"{job.title} {job.company}".lower()
    if "java" in title or "spring" in title:
        extra.append("Spring Boot")
    if "python" in title or "data" in title or "ml" in title:
        extra.append("Python")
    if extra and "Technologies" in tex:
        inject = ", ".join(extra)
        tex = tex.replace(
            r"\textbf{Technologies}{: ",
            r"\textbf{Technologies}{: " + inject + ", ",
            1,
        )
    return tex


SYSTEM_LATEX_ONLY = """You are a LaTeX editor. Your entire reply MUST be a complete compilable LaTeX document.
Rules:
- Output LaTeX source only. No markdown, no code fences, no commentary before or after.
- Keep the preamble, \\usepackage lines, \\newcommand definitions, heading (name, phone, email, links), and education dates unchanged.
- Keep every employer, school, project name, and date. Do not invent jobs, metrics, or skills the source does not contain.
- You MAY reorder \\resumeItem bullets and rephrase them, and you MAY reorder the Technical Skills lists, to emphasize the target role.
- Preserve custom macros: \\resumeItem, \\resumeSubheading, \\resumeProjectHeading, \\resumeSubHeadingListStart, etc.
"""


def _llm_tailor(tex: str, job: Job) -> str:
    key = gemini_api_key()
    if not key:
        return _keyword_tailor(tex, job)
    kind = "internship" if job.kind == RoleKind.INTERNSHIP else "new-grad full-time"
    user = (
        f"Target role ({kind}): {job.title} at {job.company}"
        f" ({job.location or 'United States'}).\n\n"
        f"Keywords from the job description and qualifications: {', '.join(job.keywords) or 'none extracted'}.\n"
        "Use these only when they are supported by the source resume, and weave them naturally into existing bullets or skills.\n\n"
        "Return the full tailored .tex file now.\n\n"
        f"{tex}"
    )
    try:
        model = gemini_model()
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_LATEX_ONLY}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2},
        }
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
        parts = data["candidates"][0]["content"]["parts"]
        content = "".join(part.get("text", "") for part in parts)
        latex = extract_latex(content)
        if is_complete_tex(latex):
            return latex
        return _keyword_tailor(tex, job)
    except Exception:
        return _keyword_tailor(tex, job)


def compile_pdf(tex_path: Path) -> Path:
    pdf = tex_path.with_suffix(".pdf")
    if pdf.exists():
        pdf.unlink()
    try:
        subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=tex_path.parent,
            check=True,
            capture_output=True,
            text=True,
        )
    if not pdf.exists():
        raise RuntimeError(f"PDF was not produced for {tex_path}")
    return pdf


def tailor_and_pdf(job: Job) -> Path:
    stem, base, dest = stems_for(job)
    pdf = ROOT / f"{stem}.pdf"
    if dest.exists():
        dest.unlink()
    if pdf.exists():
        pdf.unlink()
    tex = base.read_text(encoding="utf-8")
    tailored = _llm_tailor(tex, job)
    dest.write_text(tailored, encoding="utf-8")
    return compile_pdf(dest)
