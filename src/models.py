from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]

FT_RESUME_STEM = "Utkarsh_Tiwari_Software_Engineer"
INTERN_RESUME_STEM = "Utkarsh_Tiwari_Software_Engineering_Intern"

SUBJECT_INTERNSHIPS = r"New Internships Posted Today"
SUBJECT_JOBS = r"New Jobs Posted Today"


class RoleKind(str, Enum):
    FULL_TIME = "full_time"
    INTERNSHIP = "internship"


@dataclass
class Job:
    company: str
    title: str
    url: str
    kind: RoleKind
    location: str = ""
    salary_text: str = ""
    annual_low_usd: Optional[float] = None
    hourly_usd: Optional[float] = None
    pays_relocation: bool = False
    pays_housing: bool = False
    in_united_states: Optional[bool] = None
    estimated_pay: bool = False
    keywords: tuple[str, ...] = ()


@dataclass
class FilterDecision:
    apply: bool
    reason: str
    rank: float = 0.0


@dataclass
class ApplyResult:
    submitted: bool
    skipped: bool
    reason: str
    required_short_answers: list[str] = field(default_factory=list)
