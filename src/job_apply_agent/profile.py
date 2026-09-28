"""Applicant profile loading and validation.

The profile (YAML) is the single source of truth the agent fills forms
from. Sections:

    personal:      name, email, phone, location, links
    target:        desired roles, seniority, locations, work authorization
    experience:    years, current title/company, summary
    skills:        languages, frameworks, tools
    education:     list of degree/school/year
    compensation:  desired salary, equity flag
    answers:       pre-baked screening answers (why_this_company, strengths...)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml


class ProfileError(Exception):
    """Raised when the profile file is missing or invalid."""


REQUIRED_PERSONAL = ["first_name", "last_name", "email"]


@dataclass
class Profile:
    data: Dict[str, Any] = field(default_factory=dict)

    # ---- accessors -------------------------------------------------
    def personal(self) -> Dict[str, Any]:
        return self.data.get("personal", {})

    def full_name(self) -> str:
        p = self.personal()
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()

    def get(self, *keys: str, default: Any = None) -> Any:
        """Nested lookup, e.g. profile.get('target', 'roles')."""
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def skills_flat(self) -> List[str]:
        skills = self.data.get("skills", {})
        flat: List[str] = []
        for group in ("languages", "frameworks", "tools", "other"):
            vals = skills.get(group, [])
            if isinstance(vals, list):
                flat.extend(str(v) for v in vals)
        return flat

    def resume_summary(self) -> str:
        exp = self.data.get("experience", {})
        lines = [
            f"{self.full_name()} — {exp.get('current_title', '')} "
            f"@ {exp.get('current_company', '')}",
            exp.get("summary", ""),
            "Skills: " + ", ".join(self.skills_flat()),
        ]
        edu = self.data.get("education", [])
        if edu:
            e0 = edu[0] if isinstance(edu, list) else edu
            lines.append(f"Education: {e0.get('degree', '')}, {e0.get('school', '')}")
        return "\n".join(l for l in lines if l.strip())


def load_profile(path: str) -> Profile:
    """Load a profile YAML file into a Profile object."""
    if not os.path.exists(path):
        raise ProfileError(
            f"Profile not found: {path}\n"
            "Copy profile.yaml.example to profile.yaml and fill in your details."
        )
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ProfileError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"Profile {path} must be a YAML mapping at the top level.")
    return Profile(data=data)


def validate_profile(profile: Profile) -> List[str]:
    """Return a list of human-readable problems; empty list means valid."""
    problems: List[str] = []
    personal = profile.personal()
    if not personal:
        problems.append("missing required section: 'personal'")
    else:
        for key in REQUIRED_PERSONAL:
            if not personal.get(key):
                problems.append(f"missing required personal field: '{key}'")
    if not profile.data.get("skills"):
        problems.append("missing section: 'skills' (helps the agent answer screening questions)")
    if not profile.data.get("experience"):
        problems.append("missing section: 'experience' (helps the agent write cover letters)")
    return problems


def example_profile() -> Dict[str, Any]:
    """Minimal in-memory example profile used by tests and demos."""
    return {
        "personal": {
            "first_name": "Alex",
            "last_name": "Khan",
            "email": "alex.khan@example.com",
            "phone": "+1-555-010-2030",
            "location": "Islamabad, Pakistan",
            "linkedin": "https://linkedin.com/in/alexkhan",
            "github": "https://github.com/alexkhan",
        },
        "target": {
            "roles": ["AI Engineer", "Backend Engineer"],
            "seniority": "Mid",
            "work_authorization": {"authorized": True, "sponsorship_needed": False},
            "notice_period": "2 weeks",
        },
        "experience": {
            "years_total": 4,
            "current_title": "AI Engineer",
            "current_company": "TechFlow",
            "summary": "AI engineer with 4 years building LLM-powered apps, RAG pipelines and agentic workflows in Python.",
        },
        "skills": {
            "languages": ["Python", "TypeScript"],
            "frameworks": ["FastAPI", "LangChain", "React"],
            "tools": ["PostgreSQL", "Docker", "Playwright"],
        },
        "education": [{"degree": "B.S. Computer Science", "school": "COMSATS University", "year": 2021}],
        "compensation": {"desired_salary_usd": 90000, "open_to_equity": True},
        "answers": {
            "why_this_company": "I'm drawn to teams shipping practical AI products with strong engineering culture.",
            "greatest_strength": "I turn ambiguous product goals into working systems fast.",
        },
    }
