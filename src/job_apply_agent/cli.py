"""CLI: job-apply-agent apply|log|profile"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .agent import JobApplyAgent
from .llm import LLMClient
from .profile import ProfileError, load_profile, validate_profile
from .store import ApplicationLog

DEFAULT_PROFILE = os.path.join(os.getcwd(), "profile.yaml")


def _build_agent(args) -> JobApplyAgent:
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    llm = LLMClient(mock=args.mock_llm)
    log = ApplicationLog(args.db)
    return JobApplyAgent(profile, llm=llm, log=log, headless=args.headless)


def cmd_apply(args) -> int:
    agent = _build_agent(args)
    print(f"Opening {args.url} ...")
    result = agent.apply(args.url, dry_run=args.dry_run,
                         confirm_submit=not args.yes)
    print(f"\nMode:   {result['mode']}")
    print(f"Status: {result['status']}")
    if result.get("job_title"):
        print(f"Role:   {result['job_title']}")
    if result["blockers"]:
        print("Blockers:")
        for b in result["blockers"]:
            print(f"  ! {b}")
    print(f"\nFill plan ({len(result['actions'])} fields):")
    for a in result["actions"]:
        tag = "DRY" if a.get("dry_run") else ("OK " if a.get("filled") else "ERR")
        print(f"  [{tag}] {a['label'][:45]:45} <- {a['value'][:60]} ({a['source']})")
    print(f"\nLogged as application #{result['log_id']}")
    if result.get("note"):
        print(f"Note: {result['note']}")
    return 0


def cmd_log(args) -> int:
    log = ApplicationLog(args.db)
    rows = log.list(limit=args.limit)
    if not rows:
        print("No applications logged yet.")
        return 0
    for r in rows:
        print(f"#{r['id']} [{r['mode']}/{r['status']}] {r['job_title'] or r['url'][:60]} "
              f"({r['fields_filled']}/{r['fields_planned']} fields) {r['created_at']}")
        if args.json:
            print(json.dumps(r, indent=2))
    return 0


def cmd_profile(args) -> int:
    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    problems = validate_profile(profile)
    if not problems:
        print(f"Profile OK: {profile.full_name()} <{profile.personal().get('email')}>")
        print(f"Skills: {', '.join(profile.skills_flat()[:12])}")
        return 0
    print("Profile has problems:")
    for p in problems:
        print(f"  - {p}")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="job-apply-agent",
        description="Profile-driven agent that fills job applications. "
                    "Always dry-run first.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--db", default=os.environ.get("LOG_DB_PATH", "applications.db"))
    parser.add_argument("--mock-llm", action="store_true",
                        help="template answers instead of calling Gemini")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")

    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="fill an application form")
    p_apply.add_argument("url")
    p_apply.add_argument("--dry-run", action="store_true", default=True,
                         help="log the fill plan without typing/submitting (default)")
    p_apply.add_argument("--live", dest="dry_run", action="store_false",
                         help="actually fill the form in the browser")
    p_apply.add_argument("--yes", action="store_true",
                         help="submit without asking (live mode)")
    p_apply.set_defaults(func=cmd_apply)

    p_log = sub.add_parser("log", help="show logged applications")
    p_log.add_argument("--limit", type=int, default=20)
    p_log.add_argument("--json", action="store_true")
    p_log.set_defaults(func=cmd_log)

    p_prof = sub.add_parser("profile", help="validate your profile file")
    p_prof.add_argument("action", choices=["check"])
    p_prof.set_defaults(func=cmd_profile)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
