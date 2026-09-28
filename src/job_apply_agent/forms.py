"""Playwright form discovery + field/value mapping.

Discovers interactive fields on a job-application page and maps each one
to a value from the applicant profile using label/name/placeholder
heuristics. Long-form questions (textareas, "why..." / "describe..."
prompts) are routed to the LLM answer generator instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .profile import Profile
from .llm import LLMClient, answer_screening_question


@dataclass
class FieldPlan:
    """One field the agent intends to fill."""
    kind: str            # text | email | tel | textarea | select | checkbox | file
    label: str           # best human-readable label found
    name: str            # element name/id
    value: str           # value the agent will fill
    source: str          # profile | llm | prebaked
    longform: bool = False


# Heuristic label fragments -> profile lookup path
LABEL_MAP = [
    (("first name", "given name", "fname"), ("personal", "first_name")),
    (("last name", "surname", "family name", "lname"), ("personal", "last_name")),
    (("full name", "your name"), None),  # special-cased -> full_name()
    (("email", "e-mail"), ("personal", "email")),
    (("phone", "mobile", "contact number"), ("personal", "phone")),
    (("location", "city", "address", "where are you"), ("personal", "location")),
    (("linkedin",), ("personal", "linkedin")),
    (("github", "portfolio"), ("personal", "github")),
    (("website", "personal site"), ("personal", "website")),
    (("current title", "current role", "job title"), ("experience", "current_title")),
    (("current company", "employer"), ("experience", "current_company")),
    (("years of experience", "years experience", "total experience"),
     ("experience", "years_total")),
    (("salary", "compensation", "pay expectation"), ("compensation", "desired_salary_usd")),
    (("notice period", "start date", "availability"), ("target", "notice_period")),
    (("cover letter",), None),  # special-cased -> LLM cover letter
]

# Keywords that mark a textarea as an LLM-answered screening question
SCREENING_HINTS = (
    "why", "describe", "tell us", "explain", "what interests",
    "greatest", "strength", "weakness", "motivat",
)

FILE_HINTS = ("resume", "cv", "upload")


class FormMapper:
    """Discovers fields on a page and plans values for each."""

    def __init__(self, profile: Profile, llm: LLMClient,
                 job_title: str = "", company: str = ""):
        self.profile = profile
        self.llm = llm
        self.job_title = job_title
        self.company = company

    # ---- discovery --------------------------------------------------
    @staticmethod
    def _label_of(el) -> str:
        """Best-effort human label for an element handle (sync API)."""
        try:
            txt = el.evaluate(
                """(e) => {
                    const byId = e.id ? (document.querySelector('label[for=\"' + e.id + '\"]') || {}).innerText : '';
                    const wrap = (e.closest('label') || {}).innerText || '';
                    return (byId || wrap || e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.getAttribute('name') || '').trim();
                }"""
            )
            return " ".join(str(txt).split())[:160]
        except Exception:
            return ""

    def discover(self, page) -> List[Dict[str, Any]]:
        """Return raw discovered fields from a Playwright page."""
        fields: List[Dict[str, Any]] = []
        for el in page.query_selector_all("input, textarea, select"):
            try:
                tag = el.evaluate("(e) => e.tagName.toLowerCase()")
                itype = (el.get_attribute("type") or "").lower()
            except Exception:
                continue
            if itype in ("hidden", "submit", "button", "image"):
                continue
            fields.append({
                "el": el,
                "tag": tag,
                "type": itype,
                "label": self._label_of(el),
                "name": (el.get_attribute("name") or el.get_attribute("id") or ""),
                "required": bool(el.get_attribute("required")),
            })
        return fields

    # ---- mapping ----------------------------------------------------
    def plan_value(self, field_info: Dict[str, Any]) -> Optional[FieldPlan]:
        label = field_info["label"].lower()
        name = field_info["name"].lower()
        blob = f"{label} {name}"
        tag, itype = field_info["tag"], field_info["type"]

        # File uploads (resume) are reported, not auto-uploaded.
        if itype == "file" or any(h in blob for h in FILE_HINTS):
            return FieldPlan("file", field_info["label"], field_info["name"],
                             "<attach resume manually>", "profile")

        # Cover letter -> LLM generated
        if any(h in blob for h in ("cover letter",)):
            return FieldPlan("textarea", field_info["label"], field_info["name"],
                             "<cover letter generated at apply time>", "llm",
                             longform=True)

        # Screening questions -> LLM / pre-baked answers
        if tag == "textarea" and any(h in blob for h in SCREENING_HINTS):
            return FieldPlan("textarea", field_info["label"], field_info["name"],
                             "<screening answer generated at apply time>", "llm",
                             longform=True)

        # Profile-driven mapping
        for fragments, path in LABEL_MAP:
            if any(f in blob for f in fragments):
                if path is None:
                    value = self.profile.full_name()
                else:
                    value = self.profile.get(*path)
                if value in (None, ""):
                    return None
                return FieldPlan(
                    "textarea" if tag == "textarea" else "text",
                    field_info["label"], field_info["name"], str(value), "profile",
                )
        return None

    def build_plan(self, page) -> List[FieldPlan]:
        plans: List[FieldPlan] = []
        for finfo in self.discover(page):
            plan = self.plan_value(finfo)
            if plan:
                plans.append(plan)
        return plans

    # ---- execution --------------------------------------------------
    def resolve_longform(self, plan: FieldPlan) -> str:
        """Generate the actual text for an LLM-sourced field."""
        if "cover letter" in (plan.label + " " + plan.name).lower():
            from .llm import build_cover_letter
            return build_cover_letter(self.llm, self.profile,
                                      self.job_title, self.company)
        return answer_screening_question(self.llm, self.profile, plan.label,
                                         self.job_title, self.company)

    def fill(self, page, plans: List[FieldPlan], dry_run: bool = True) -> List[Dict[str, Any]]:
        """Fill fields on the page (or just report in dry-run)."""
        actions: List[Dict[str, Any]] = []
        for plan in plans:
            value = self.resolve_longform(plan) if plan.longform else plan.value
            action = {
                "label": plan.label or plan.name,
                "kind": plan.kind,
                "value": value[:120] + ("…" if len(value) > 120 else ""),
                "source": plan.source,
                "dry_run": dry_run,
            }
            if not dry_run and plan.kind != "file":
                try:
                    locator = (page.locator(f"[name='{plan.name}']")
                               if plan.name else None)
                    if locator and locator.count():
                        locator.first.fill(value)
                    action["filled"] = True
                except Exception as exc:  # noqa: BLE001
                    action["filled"] = False
                    action["error"] = str(exc)[:200]
            actions.append(action)
        return actions
