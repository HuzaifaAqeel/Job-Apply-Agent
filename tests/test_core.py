"""Unit tests for the profile / mapping / logging core (no browser needed)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from job_apply_agent.profile import Profile, example_profile, validate_profile
from job_apply_agent.llm import LLMClient, answer_screening_question, build_cover_letter
from job_apply_agent.forms import FormMapper
from job_apply_agent.store import ApplicationLog


def test_profile_load_and_validate():
    p = Profile(data=example_profile())
    assert validate_profile(p) == []
    assert p.full_name() == "Alex Khan"
    assert "Python" in p.skills_flat()


def test_profile_validation_flags_missing():
    p = Profile(data={"personal": {"first_name": "A"}})
    problems = validate_profile(p)
    assert any("last_name" in x for x in problems)
    assert any("email" in x for x in problems)


def test_mock_llm_flag():
    llm = LLMClient(mock=True)
    assert llm.mock and llm.provider == "mock-template"
    out = llm.generate("sys", "write a cover letter")
    assert "MOCK-GENERATED" in out


def test_prebaked_screening_answer():
    p = Profile(data=example_profile())
    llm = LLMClient(mock=True)
    ans = answer_screening_question(llm, p, "Why do you want to work at our company?")
    assert "practical AI products" in ans


def test_factual_screening_answers():
    p = Profile(data=example_profile())
    llm = LLMClient(mock=True)
    assert "sponsorship" in answer_screening_question(
        llm, p, "Will you require visa sponsorship?").lower()
    assert "90000" in answer_screening_question(
        llm, p, "What are your salary expectations?")


def test_cover_letter_mock():
    p = Profile(data=example_profile())
    llm = LLMClient(mock=True)
    letter = build_cover_letter(llm, p, "AI Engineer", "DemoCorp", "Build LLM apps.")
    assert "MOCK-GENERATED" in letter


def test_field_plan_mapping():
    p = Profile(data=example_profile())
    llm = LLMClient(mock=True)
    mapper = FormMapper(p, llm, job_title="AI Engineer", company="DemoCorp")
    finfo = {"tag": "input", "type": "text", "label": "First name",
             "name": "first_name", "required": True}
    plan = mapper.plan_value(finfo)
    assert plan is not None and plan.value == "Alex" and plan.source == "profile"

    finfo2 = {"tag": "textarea", "type": "", "label": "Why do you want this job?",
              "name": "why", "required": False}
    plan2 = mapper.plan_value(finfo2)
    assert plan2 is not None and plan2.source == "llm" and plan2.longform


def test_application_log_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "test.db")
        log = ApplicationLog(db)
        app_id = log.record("https://example.com/apply/1", mode="dry-run",
                            status="planned", job_title="AI Engineer",
                            company="DemoCorp",
                            plan=[{"label": "Email", "filled": False}])
        rows = log.list()
        assert len(rows) == 1 and rows[0]["id"] == app_id
        full = log.get(app_id)
        assert full["job_title"] == "AI Engineer"
