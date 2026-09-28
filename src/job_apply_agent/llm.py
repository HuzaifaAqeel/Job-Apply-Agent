"""LLM text generation for cover letters and screening answers.

Uses Google Gemini (free tier) via its REST API. The key is read from the
GOOGLE_API_KEY environment variable -- never hardcoded. If no key is set,
a deterministic template-based generator is used instead (marked clearly
in the output), so dry-runs and demos work without any API access.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from .profile import Profile

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
    ":generateContent"
)


class LLMClient:
    """Thin Gemini client with a mock fallback."""

    def __init__(self, api_key: Optional[str] = None, mock: bool = False):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        # Explicit mock flag OR no key -> template mode
        self.mock = mock or not self.api_key

    @property
    def provider(self) -> str:
        return "mock-template" if self.mock else f"gemini/{GEMINI_MODEL}"

    def generate(self, system: str, prompt: str, max_tokens: int = 800) -> str:
        if self.mock:
            return self._template(prompt)
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
        }
        req = urllib.request.Request(
            f"{GEMINI_URL}?key={self.api_key}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
        try:
            return body["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Gemini response: {body}") from exc

    # ---- template fallback ------------------------------------------
    @staticmethod
    def _template(prompt: str) -> str:
        # Deterministic stand-in so tests/demos run without a key.
        head = prompt.strip().splitlines()[0][:120]
        return (
            f"[MOCK-GENERATED draft — set GOOGLE_API_KEY for a real one]\n"
            f"{head} ..."
        )


def build_cover_letter(llm: LLMClient, profile: Profile,
                       job_title: str, company: str,
                       job_description: str = "") -> str:
    system = (
        "You write concise, human-sounding job application cover letters. "
        "No purple prose, no buzzword stuffing, no em dashes overload. "
        "Plain, confident, specific."
    )
    prompt = (
        f"Write a cover letter (max 200 words) for {profile.full_name()} "
        f"applying to the {job_title} role at {company}.\n\n"
        f"Candidate background:\n{profile.resume_summary()}\n\n"
        f"Job description:\n{job_description[:2000]}\n"
    )
    return llm.generate(system, prompt)


def answer_screening_question(llm: LLMClient, profile: Profile,
                             question: str,
                             job_title: str = "", company: str = "") -> str:
    # 1) Prefer a pre-baked answer from the profile when it matches.
    baked = profile.data.get("answers", {})
    q = question.lower()
    for key, value in baked.items():
        key_norm = key.replace("_", " ")
        if key_norm in q or any(w in q for w in key_norm.split() if len(w) > 4):
            return str(value)

    # 2) Common factual questions are answered directly from the profile.
    if any(k in q for k in ("salary", "compensation", "pay expectation")):
        sal = profile.get("compensation", "desired_salary_usd")
        return f"My expected compensation is around ${sal}." if sal else "Open to discussing compensation."
    if "notice period" in q or "start date" in q or "when can you start" in q:
        return profile.get("target", "notice_period") or "2 weeks"
    if "sponsorship" in q or "work authorization" in q or "authorized to work" in q:
        auth = profile.get("target", "work_authorization", default={})
        if auth.get("authorized") and not auth.get("sponsorship_needed"):
            return "I am authorized to work and do not require sponsorship."
        return "I will require visa sponsorship."

    # 3) Fall back to LLM generation.
    system = (
        "Answer job-application screening questions in first person, "
        "2-4 sentences, grounded strictly in the candidate's background."
    )
    prompt = (
        f"Screening question for a {job_title or 'software'} role"
        f"{f' at {company}' if company else ''}: \"{question}\"\n\n"
        f"Candidate:\n{profile.resume_summary()}\n"
        "Answer briefly and honestly. If the background doesn't cover it, "
        "say so instead of inventing experience."
    )
    return llm.generate(system, prompt, max_tokens=300)
