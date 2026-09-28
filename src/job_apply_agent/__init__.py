"""Job-Apply-Agent: profile-driven CLI agent that fills online job applications.

Given a job posting URL and an applicant profile, it navigates the
application form, fills every field it can map, generates tailored cover
letters and screening answers with an LLM, and -- in dry-run mode -- logs
exactly what it *would* fill without submitting anything.
"""

__version__ = "0.1.0"
__author__ = "Huzaifa Aqeel"

from .profile import Profile, load_profile, validate_profile
from .store import ApplicationLog
from .agent import JobApplyAgent

__all__ = ["Profile", "load_profile", "validate_profile", "ApplicationLog", "JobApplyAgent"]
